"""
Supervisor 서브그래프 모듈

연구 작업을 계획하고 `Researcher` 서브그래프를 병렬 실행하여 결과를 수집합니다.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal  
import json

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from typing_extensions import TypedDict

from src.config import ResearchConfig
from src.utils.logging_config import get_logger
from .shared import override_reducer, get_notes_from_tool_calls, ConductResearch, ResearchComplete
from .researcher_graph import researcher_graph


logger = get_logger(__name__)

class SupervisorInputState(TypedDict):
    supervisor_messages: Annotated[list, override_reducer]
    research_brief: str
    
class SupervisorOutputState(TypedDict):
    supervisor_messages: Annotated[list, override_reducer]
    research_iterations: int
    notes: Annotated[list[str], override_reducer]
    raw_notes: Annotated[list[str], override_reducer]

class SupervisorOverallState(SupervisorInputState, SupervisorOutputState):
    """Supervisor 서브그래프 내부 상태"""


def _tc_name(tool_call: Any) -> str | None:
    """툴콜 객체/딕셔너리에서 안전하게 name을 추출.

    지원 포맷:
    - {"name": "ConductResearch", ...}
    - {"function": {"name": "ConductResearch", "arguments": "{...}"}}
    - 객체 속성으로 name/function.name 제공
    """
    if isinstance(tool_call, dict):
        fn = tool_call.get("function")
        if isinstance(fn, dict) and isinstance(fn.get("name"), str):
            return fn["name"]
        name = tool_call.get("name")
        if isinstance(name, str) and name:
            return name
        tool_name = tool_call.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            return tool_name
        return None

    name_attr = getattr(tool_call, "name", None)
    if isinstance(name_attr, str) and name_attr:
        return name_attr
    function_attr = getattr(tool_call, "function", None)
    if function_attr is not None:
        f_name = getattr(function_attr, "name", None)
        if isinstance(f_name, str) and f_name:
            return f_name
    return None


def _tc_id(tool_call: Any) -> str | None:
    """툴콜 객체/딕셔너리에서 안전하게 id를 추출."""
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    return getattr(tool_call, "id", None)


def _tc_args(tool_call: Any) -> dict:
    """툴콜 객체/딕셔너리에서 안전하게 args를 추출하여 dict로 반환.

    지원 포맷:
    - {"args": {...}}
    - {"function": {"arguments": "{...}"}}  # OpenAI function-style (문자열 JSON)
    - {"arguments": "{...}" | {...}}
    - 객체 속성 args / function.arguments
    """
    if isinstance(tool_call, dict):
        args = tool_call.get("args")
        if isinstance(args, dict):
            return args
        fn = tool_call.get("function")
        if isinstance(fn, dict):
            arguments = fn.get("arguments")
            if isinstance(arguments, dict):
                return arguments
            if isinstance(arguments, str):
                try:
                    return json.loads(arguments)
                except Exception:
                    return {}
        arguments = tool_call.get("arguments")
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except Exception:
                return {}
        return {}

    obj_args = getattr(tool_call, "args", None)
    if isinstance(obj_args, dict):
        return obj_args
    function_attr = getattr(tool_call, "function", None)
    if function_attr is not None:
        fn_args = getattr(function_attr, "arguments", None)
        if isinstance(fn_args, dict):
            return fn_args
        if isinstance(fn_args, str):
            try:
                return json.loads(fn_args)
            except Exception:
                return {}
    arguments_attr = getattr(tool_call, "arguments", None)
    if isinstance(arguments_attr, dict):
        return arguments_attr
    if isinstance(arguments_attr, str):
        try:
            return json.loads(arguments_attr)
        except Exception:
            return {}
    return {}


def _check_terminate_conditions(supervisor_messages: list, research_iterations: int, configurable: ResearchConfig):
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
    # 종료 조건 보완:
    # - 최초 1회는 ConductResearch 실행을 시도하기 위해 no_tool_calls만으로 종료하지 않음
    # - 이후에는 기존 조건 유지
    should_terminate = (
        exceeded_allowed_iterations
        or research_complete_tool_call
        # 최초 1회(no_tool_calls)에서는 종료하지 않도록 임계값을 > 1로 설정
        or (no_tool_calls and research_iterations > 1)
    )
    return should_terminate, most_recent_message


async def _execute_parallel_research(conduct_research_calls: list, config: RunnableConfig, researcher_subgraph: Runnable) -> list:
    logger.info(f"_execute_parallel_research: start n={len(conduct_research_calls)}")

    # 동시성 한도 적용 (A2A 런타임에서 일부 MCP 도구가 동시 호출 시 AttributeError: name 발생 방지)
    try:
        from src.config import ResearchConfig as _RC
        conf = _RC.from_runnable_config(config)
        max_inflight = max(1, int(getattr(conf, "max_concurrent_research_units", 3)))
    except Exception:
        max_inflight = 3

    semaphore = asyncio.Semaphore(max_inflight)

    async def _invoke_once(tc):
        args = _tc_args(tc)
        payload = {
            "researcher_messages": [HumanMessage(content=args.get("research_topic", ""))],
            "research_topic": args.get("research_topic", ""),
        }
        async with semaphore:
            try:
                return await researcher_subgraph.ainvoke(payload, config)
            except Exception as e:
                # 예외를 그대로 반환해 상위에서 처리하되, 간단한 로그로 남김
                logger.warning(f"researcher_subgraph.ainvoke failed: {type(e).__name__}: {e}")
                return e

    results = await asyncio.gather(*[_invoke_once(tc) for tc in conduct_research_calls], return_exceptions=False)

    # 결과 요약
    summaries: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            summaries.append(f"Exception:{type(r).__name__}")
        elif isinstance(r, dict):
            summaries.append("dict")
        else:
            summaries.append(type(r).__name__)
    logger.info(f"_execute_parallel_research: done {summaries}")

    # 예외는 상위에서 처리하도록 결과에 그대로 포함
    return results


def _process_research_results(tool_results: list, conduct_research_calls: list):
    from langchain_core.messages import ToolMessage

    tool_messages = []
    for observation, tool_call in zip(tool_results, conduct_research_calls):
        # 관측값에서 내용 추출: 예외/모델객체/dict 모두 안전 처리
        obs_content: str | None = None
        if isinstance(observation, Exception):
            obs_content = f"Error executing tool: {type(observation).__name__}: {str(observation)}"
        elif isinstance(observation, dict):
            obs_content = observation.get("compressed_research") or ""
        else:
            try:
                obs_content = getattr(observation, "compressed_research", "")
            except Exception:
                obs_content = ""
        if not isinstance(obs_content, str) or not obs_content:
            obs_content = "Error synthesizing research report"

        try:
            resolved_name = _tc_name(tool_call) or "ConductResearch"
            resolved_id = _tc_id(tool_call) or "unknown"
            logger.info(f"ToolCall resolved -> name='{resolved_name}', id='{resolved_id}'")
            tool_messages.append(
                ToolMessage(
                    content=obs_content,
                    name=resolved_name,
                    tool_call_id=resolved_id,
                )
            )
        except Exception as tm_ex:
            try:
                preview = list(tool_call.keys()) if isinstance(tool_call, dict) else type(tool_call).__name__
            except Exception:
                preview = "<unknown>"
            logger.exception(f"ToolMessage construction failed: {tm_ex}; tool_call_preview={preview}")

    # raw_notes 안전 추출 (예외/모델객체/dict 모두 허용)
    try:
        raw_notes_list: list[str] = []
        for obs in tool_results:
            notes = []
            if isinstance(obs, dict):
                notes = obs.get("raw_notes", []) or []
            else:
                try:
                    notes = getattr(obs, "raw_notes", []) or []
                except Exception:
                    notes = []
            if isinstance(notes, list):
                raw_notes_list.append("\n".join([str(x) for x in notes if isinstance(x, str)]))
        raw_notes_concat = "\n".join(raw_notes_list)
    except Exception:
        raw_notes_concat = ""
    return tool_messages, raw_notes_concat

async def supervisor(state: SupervisorOverallState, config: RunnableConfig) -> dict:
    configurable = ResearchConfig.from_runnable_config(config)
    # Superviser 모델에는 ConductResearch/ResearchComplete만 바인딩
    # (Researcher 단계에서 MCP 도구를 바인딩하므로 혼합 바인딩을 피함)
    model = (
        init_chat_model(model_provider="openai", model="gpt-4o-2024-11-20", temperature=0)
        .bind_tools([ConductResearch, ResearchComplete])
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    )

    # NOTE: Input State 에 넣어주었던 메시지
    supervisor_messages = state.get("supervisor_messages", [])
    response = await model.ainvoke(supervisor_messages)
    # return Command(
    #     goto="supervisor_tools",
    #     update={
    #         "supervisor_messages": [response],
    #         "research_iterations": state.get("research_iterations", 0) + 1,
    #     },
    # )
    return {
        "supervisor_messages": [response],
        "research_iterations": state.get("research_iterations", 0) + 1,
    }

async def supervisor_tools(state: SupervisorOverallState, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
        configurable = ResearchConfig.from_runnable_config(config)
        supervisor_messages = state.get("supervisor_messages", [])
        research_iterations = state.get("research_iterations", 0) + 1

        # NOTE: 종료 조건 확인
        should_terminate, most_recent_message = _check_terminate_conditions(
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
                tool_call for tool_call in (most_recent_message.tool_calls or []) 
                if _tc_name(tool_call) == "ConductResearch" # NOTE: 연구 계획 작성 후 연구 감독자 그래프로 이동
            ]
            logger.info(f"ConductResearch calls detected: {len(all_conduct_research_calls)}")

            # 첫 1~2회 반복에서 툴콜이 전혀 없으면 연구 계획(research_brief)로 최소 1회 강제 실행
            if not all_conduct_research_calls:
                brief = state.get("research_brief", "")
                until_iter = getattr(configurable, "supervisor_force_conduct_research_until_iteration", 1)
                enabled = bool(getattr(configurable, "supervisor_force_conduct_research_enabled", True))
                if (
                    enabled
                    and isinstance(brief, str)
                    and brief.strip()
                    and research_iterations <= max(0, int(until_iter))
                ):
                    logger.info("No ConductResearch tool calls; forcing one with research_brief")
                    all_conduct_research_calls = [
                        {
                            "id": "forced-1",
                            "function": {
                                "name": "ConductResearch",
                                "arguments": json.dumps({"research_topic": brief}),
                            },
                        }
                    ]

            tool_results = await _execute_parallel_research(all_conduct_research_calls, config, researcher_graph)

            # 병렬 리서치 실행 직후, 구성된 유예 시간만큼 대기하여 비동기 I/O 잔여 처리를 안정화
            try:
                grace = float(getattr(ResearchConfig.from_runnable_config(config), "supervisor_research_grace_seconds", 0.3))
                if grace > 0:
                    await asyncio.sleep(grace)
            except Exception:
                pass

            # 1) 안전하게 notes 추출 (ToolMessage 의존 최소화)
            notes_list: list[str] = []
            try:
                for obs in tool_results:
                    text_val = None
                    if isinstance(obs, dict):
                        text_val = obs.get("compressed_research") or None
                    else:
                        # Pydantic BaseModel 등
                        text_val = getattr(obs, "compressed_research", None)
                    if isinstance(text_val, str) and text_val.strip():
                        notes_list.append(text_val.strip())
            except Exception:
                notes_list = []

            # 2) 기존 메시지 루프 유지 (툴 메시지 기반 루프)
            raw_notes_concat = ""
            tool_messages = []
            tool_messages, raw_notes_concat = _process_research_results(tool_results, all_conduct_research_calls)

            update_payload: dict[str, Any] = {
                "supervisor_messages": tool_messages or [],
            }
            if raw_notes_concat:
                update_payload["raw_notes"] = [raw_notes_concat]
            if notes_list:
                # 루프 중간에도 노트를 누적시키면 조기 종료 시에도 보고서 품질을 확보
                update_payload["notes"] = notes_list

            return Command(goto="supervisor", update=update_payload)
        except Exception as e:
            # 일부 런타임에서 tool_calls 구조가 가변적(dict/객체 혼재)이라 KeyError/AttributeError가 발생할 수 있음
            # 사용자 경험을 해치지 않도록 에러 대신 경고로 기록하고, 현재까지 수집된 노트를 반환하며 안전 종료한다
            logger.warning(f"Supervisor tool handling fallback: {e}")
            safe_notes = []
            try:
                safe_notes = get_notes_from_tool_calls(supervisor_messages)
            except Exception:
                safe_notes = []

            # 소프트 리트라이: notes가 비어 있고 research_brief가 있으면 1회 ConductResearch 강제 실행
            try:
                if (not safe_notes) and isinstance(state.get("research_brief"), str) and state.get("research_brief"):
                    logger.info("Fallback soft-retry: invoking single ConductResearch with research_brief")
                    fallback_calls = [
                        {
                            "id": "fallback-1",
                            "function": {
                                "name": "ConductResearch",
                                "arguments": json.dumps({"research_topic": state.get("research_brief", "")}),
                            },
                        }
                    ]
                    tool_results = await _execute_parallel_research(fallback_calls, config, researcher_graph)
                    notes_list = []
                    for obs in tool_results:
                        text_val = obs.get("compressed_research") if isinstance(obs, dict) else getattr(obs, "compressed_research", None)
                        if isinstance(text_val, str) and text_val.strip():
                            notes_list.append(text_val.strip())
                    if notes_list:
                        return Command(goto="supervisor", update={"notes": notes_list})
            except Exception:
                pass

            return Command(
                goto=END,
                update={
                    "notes": safe_notes,
                    "research_brief": state.get("research_brief", ""),
                },
            )

def build_supervisor_subgraph():
    """Supervisor 서브그래프"""

    workflow = StateGraph(
        state_schema=SupervisorOverallState, 
        input_schema=SupervisorInputState,
        output_schema=SupervisorOutputState,
        config_schema=ResearchConfig,
    )
    # 노드
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("supervisor_tools", supervisor_tools)
    # 엣지
    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", "supervisor_tools")
    return workflow.compile()


