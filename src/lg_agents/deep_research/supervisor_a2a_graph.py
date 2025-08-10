"""
Supervisor A2A Graph

LangGraph의 Supervisor 서브그래프를 A2A 시나리오에 맞게 변형한 그래프.
- ConductResearch 호출을 원격 Researcher A2A 에이전트 호출로 위임 (가능 시)
- 원격 사용 불가 시 기존 Researcher 서브그래프 로컬 실행으로 폴백
- 종료 시점에 요약 텍스트를 `messages`로 만들어 A2A 응답이 안정적으로 출력되게 함
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from src.config import ResearchConfig
from src.utils.logging_config import get_logger
from .shared import (
    override_reducer,
    get_notes_from_tool_calls,
    ConductResearch,
    ResearchComplete,
)
from .researcher_graph import build_researcher_subgraph
from src.a2a_integration.a2a_lg_client_utils import query_a2a_agent


logger = get_logger(__name__)


class DeepResearchSupervisorState(TypedDict):
    """Supervisor 서브그래프 내부 상태 (A2A용)"""

    supervisor_messages: Annotated[list, override_reducer]
    research_brief: str
    notes: Annotated[list[str], override_reducer]
    research_iterations: int
    raw_notes: Annotated[list[str], override_reducer]


def _tc_name(tool_call: Any) -> str | None:
    if isinstance(tool_call, dict):
        return tool_call.get("name")
    return getattr(tool_call, "name", None)


def _tc_id(tool_call: Any) -> str | None:
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    return getattr(tool_call, "id", None)


def _tc_args(tool_call: Any) -> dict:
    if isinstance(tool_call, dict):
        args = tool_call.get("args")
    else:
        args = getattr(tool_call, "args", None)
    return args if isinstance(args, dict) else {}


def _check_termination_conditions(supervisor_messages: list, research_iterations: int, configurable: ResearchConfig):
    if not supervisor_messages:
        return True, None
    most_recent_message = supervisor_messages[-1]
    exceeded_allowed_iterations = research_iterations >= configurable.max_researcher_iterations
    no_tool_calls = not most_recent_message.tool_calls
    research_complete_tool_call = (
        any((_tc_name(tool_call) == "ResearchComplete") for tool_call in most_recent_message.tool_calls)
        if most_recent_message.tool_calls
        else False
    )
    should_terminate = exceeded_allowed_iterations or no_tool_calls or research_complete_tool_call
    return should_terminate, most_recent_message


async def _is_a2a_server_alive(base_url: str, timeout_seconds: float = 1.5) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _execute_parallel_research(conduct_research_calls: list, config: RunnableConfig, researcher_subgraph) -> list:
    """
    A2A 호출 경계: Supervisor → Researcher
    - 연구자 호출을 원격 A2A 에이전트로 위임 가능한 경우 네트워크 경유로 병렬 실행합니다.
    - 원격 호출이 불가하거나 실패하면 로컬 `researcher_subgraph` 실행으로 폴백합니다.
    - 엔드포인트는 `ResearchConfig.get_a2a_endpoint("researcher")`로 조회하며,
      `_is_a2a_server_alive()`로 헬스체크 후 `query_a2a_agent()`를 통해 호출합니다.
    - 호출 결과는 `compressed_research`/`raw_notes` 형태로 상위 노드에 반환됩니다.
    """
    configurable = ResearchConfig.from_runnable_config(config)
    # A2A 엔드포인트 조회: Researcher 역할의 A2A 에이전트 URL
    base_url = configurable.get_a2a_endpoint("researcher")
    use_remote = False
    if isinstance(base_url, str) and base_url:
        # A2A 서버 가용성 확인(health 체크 200 응답 시 사용)
        use_remote = await _is_a2a_server_alive(base_url)

    if use_remote:
        # A2A 호출 루트: Supervisor → Researcher 원격 호출
        # - 각 ConductResearch 툴콜을 독립 요청으로 변환하여 병렬 실행합니다.
        # - 네트워크 지연/실패 상황을 고려해 try/except로 안전하게 처리합니다.
        async def _call_remote(tool_call):
            topic = _tc_args(tool_call).get("research_topic", "")
            try:
                logger.info(
                    f"A2A call: Supervisor → Researcher start | url={base_url} | topic_preview={topic[:80]!r}"
                )
                import time as _time
                _t0 = _time.time()
                text = await query_a2a_agent(topic, base_url=base_url)
                _elapsed = _time.time() - _t0
                logger.info(
                    f"A2A call: Supervisor ← Researcher done | elapsed={_elapsed:.2f}s | response_chars={len(text)}"
                )
            except Exception as e:
                logger.error(f"A2A researcher 호출 실패: {e}")
                text = "Error synthesizing research report"
            return {"compressed_research": text, "raw_notes": []}

        # 원격 요청들을 동시에 실행
        coros = [_call_remote(tool_call) for tool_call in conduct_research_calls]
        return await asyncio.gather(*coros)

    # Fallback: 로컬 서브그래프 실행
    logger.info(f"Fallback: 로컬 서브그래프 실행 | 주제: {conduct_research_calls}")
    coros = [
        researcher_subgraph.ainvoke(
            {
                "researcher_messages": [HumanMessage(content=_tc_args(tool_call).get("research_topic", ""))],
                "research_topic": _tc_args(tool_call).get("research_topic", ""),
            },
            config,
        )
        for tool_call in conduct_research_calls
    ]
    return await asyncio.gather(*coros)


def build_supervisor_a2a_graph():
    """A2A 용 Supervisor 그래프 컴파일러."""

    researcher_subgraph = build_researcher_subgraph()

    async def supervisor(state: DeepResearchSupervisorState, config: RunnableConfig):
        configurable = ResearchConfig.from_runnable_config(config)
        lead_researcher_tools = [ConductResearch, ResearchComplete]
        model = (
            init_chat_model(model_provider="openai", model=configurable.research_model, temperature=0)
            .bind_tools(lead_researcher_tools)
            .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        )

        supervisor_messages = state.get("supervisor_messages", [])
        response = await model.ainvoke(supervisor_messages)
        return Command(
            goto="supervisor_tools",
            update={
                "supervisor_messages": [response],
                "research_iterations": state.get("research_iterations", 0) + 1,
            },
        )

    async def supervisor_tools(state: DeepResearchSupervisorState, config: RunnableConfig):
        configurable = ResearchConfig.from_runnable_config(config)
        supervisor_messages = state.get("supervisor_messages", [])
        research_iterations = state.get("research_iterations", 0)

        should_terminate, most_recent_message = _check_termination_conditions(
            supervisor_messages, research_iterations, configurable
        )
        if should_terminate:
            # 종료 전 노트/브리프를 정리하고 바로 종료
            return Command(
                goto=END,
                update={
                    "notes": get_notes_from_tool_calls(supervisor_messages),
                    "research_brief": state.get("research_brief", ""),
                },
            )

        try:
            all_conduct_research_calls = [
                tool_call for tool_call in most_recent_message.tool_calls if _tc_name(tool_call) == "ConductResearch"
            ]
            conduct_research_calls = all_conduct_research_calls[: configurable.max_concurrent_research_units]
            tool_results = await _execute_parallel_research(conduct_research_calls, config, researcher_subgraph)

            # ToolMessage로 supervisor_messages에 반영하여 기존 노트 추출 로직과 호환되게 함
            tool_messages: list[ToolMessage] = []
            for observation, tool_call in zip(tool_results, conduct_research_calls):
                obs_content = observation.get("compressed_research") if isinstance(observation, dict) else None
                if not isinstance(obs_content, str) or not obs_content:
                    obs_content = "Error synthesizing research report"
                tool_messages.append(
                    ToolMessage(
                        content=obs_content,
                        name=_tc_name(tool_call) or "ConductResearch",
                        tool_call_id=_tc_id(tool_call) or "unknown",
                    )
                )

            raw_notes_concat = "\n".join(["\n".join(observation.get("raw_notes", [])) for observation in tool_results])
            return Command(
                goto="supervisor",
                update={
                    "supervisor_messages": tool_messages,
                    "raw_notes": [raw_notes_concat] if raw_notes_concat else [],
                },
            )
        except Exception as e:
            logger.error(f"Supervisor tools error: {e}")
    builder = StateGraph(
        state_schema=DeepResearchSupervisorState, 
        config_schema=ResearchConfig,
    )
    builder.add_node("supervisor", supervisor)
    builder.add_node("supervisor_tools", supervisor_tools)
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor_tools", END)
    return builder.compile()


