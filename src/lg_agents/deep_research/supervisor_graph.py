"""
Supervisor 서브그래프 모듈

연구 작업을 계획하고 `Researcher` 서브그래프를 병렬 실행하여 결과를 수집합니다.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from src.config import ResearchConfig
from src.utils.logging_config import get_logger
from .shared import override_reducer, get_notes_from_tool_calls, ConductResearch, ResearchComplete
from .researcher_graph import build_researcher_subgraph


logger = get_logger(__name__)


class DeepResearchSupervisorState(TypedDict):
    """Supervisor 서브그래프 내부 상태"""

    supervisor_messages: Annotated[list, override_reducer]
    research_brief: str
    notes: Annotated[list[str], override_reducer]
    research_iterations: int
    raw_notes: Annotated[list[str], override_reducer]


def _tc_name(tool_call: Any) -> str | None:
    """툴콜 객체/딕셔너리에서 안전하게 name을 추출."""
    if isinstance(tool_call, dict):
        return tool_call.get("name")
    return getattr(tool_call, "name", None)


def _tc_id(tool_call: Any) -> str | None:
    """툴콜 객체/딕셔너리에서 안전하게 id를 추출."""
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    return getattr(tool_call, "id", None)


def _tc_args(tool_call: Any) -> dict:
    """툴콜 객체/딕셔너리에서 안전하게 args를 추출하여 dict로 반환."""
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


async def _execute_parallel_research(conduct_research_calls: list, config: RunnableConfig, researcher_subgraph) -> list:
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


def _process_research_results(tool_results: list, conduct_research_calls: list):
    from langchain_core.messages import ToolMessage

    tool_messages = []
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
    return tool_messages, raw_notes_concat


def build_supervisor_subgraph():
    """Supervisor 서브그래프"""

    researcher_subgraph = build_researcher_subgraph()

    async def supervisor(state: DeepResearchSupervisorState, config: RunnableConfig):
        configurable = ResearchConfig.from_runnable_config(config)
        lead_researcher_tools = [ConductResearch, ResearchComplete]
        model = (
            init_chat_model(model_provider="openai", model="gpt-4o-2024-11-20", temperature=0)
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
            supervisor_messages, 
            research_iterations, 
            configurable,
        )
        if should_terminate:
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
            tool_messages, raw_notes_concat = _process_research_results(tool_results, conduct_research_calls)
            return Command(
                goto="supervisor",
                update={
                    "supervisor_messages": tool_messages,
                    "raw_notes": [raw_notes_concat],
                },
            )
        except Exception as e:
            # 일부 런타임에서 tool_calls 구조가 가변적(dict/객체 혼재)이라 KeyError/AttributeError가 발생할 수 있음
            # 사용자 경험을 해치지 않도록 에러 대신 경고로 기록하고, 현재까지 수집된 노트를 반환하며 안전 종료한다
            logger.warning(f"Supervisor tool handling fallback: {e}")
            safe_notes = []
            try:
                safe_notes = get_notes_from_tool_calls(supervisor_messages)
            except Exception:
                safe_notes = []
            return Command(
                goto=END,
                update={
                    "notes": safe_notes,
                    "research_brief": state.get("research_brief", ""),
                },
            )

    builder = StateGraph(state_schema=DeepResearchSupervisorState, config_schema=ResearchConfig)
    builder.add_node("supervisor", supervisor)
    builder.add_node("supervisor_tools", supervisor_tools)
    builder.set_entry_point("supervisor")
    return builder.compile()


