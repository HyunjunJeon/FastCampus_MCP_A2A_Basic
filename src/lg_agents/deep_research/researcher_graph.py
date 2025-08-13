"""
Researcher 서브그래프 모듈

MCP 도구를 활용해 정보 수집(ReAct)과 결과 압축을 수행하는 연구원 그래프를 정의합니다.
"""

from __future__ import annotations

from typing import Annotated
import operator
import asyncio

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
from pydantic import BaseModel
from typing_extensions import TypedDict

from src.config import ResearchConfig
from src.utils.logging_config import get_logger
from .shared import override_reducer
# Researcher 단계에서는 MCP 도구만 바인딩하므로 ResearchComplete를 가져오지 않는다
from .prompts import (
    research_system_prompt,
    compress_research_system_prompt,
    compress_research_simple_human_message,
    get_today_str,
)
from langchain_mcp_adapters.tools import load_mcp_tools
from urllib.parse import urlparse
from src.utils.http_client import http_client
from src.lg_agents.deep_research.shared import ResearchComplete


logger = get_logger(__name__)

class ResearcherInputState(TypedDict):
    """Researcher 서브그래프 입력 상태"""
    researcher_messages: Annotated[list, operator.add]
    research_topic: str

class ResearcherOutputState(TypedDict):
    """Researcher 서브그래프 출력 상태"""

    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []

class ResearcherState(ResearcherInputState, ResearcherOutputState):
    """Researcher 서브그래프 내부 상태"""
    tool_call_iterations: int


def _get_mcp_prompt_description(tools: list) -> str:
    """MCP 도구 설명 문자열을 안전하게 생성한다.

    - 일부 런타임에서 tool.name / tool.description 접근이 AttributeError를 유발할 수 있어
      예외 안전하게 추출한다.
    - dict 포맷과 클래스/함수의 __name__도 지원한다.
    """
    lines: list[str] = []
    for tool in tools:
        # 이름
        name: str | None = None
        try:
            n = getattr(tool, "name", None)
            if isinstance(n, str) and n:
                name = n
        except Exception:
            name = None
        if not name and isinstance(tool, dict):
            n = tool.get("name")
            if isinstance(n, str) and n:
                name = n
        if not name:
            try:
                n = getattr(tool, "__name__", None)
                if isinstance(n, str) and n:
                    name = n
            except Exception:
                pass
        if not isinstance(name, str) or not name:
            name = "tool"

        # 설명
        desc: str | None = None
        try:
            d = getattr(tool, "description", None)
            if isinstance(d, str) and d:
                desc = d
        except Exception:
            desc = None
        if not desc and isinstance(tool, dict):
            d = tool.get("description")
            if isinstance(d, str) and d:
                desc = d

        lines.append(f"{name}: {desc}" if desc else name)
    return "\n".join(lines)


def _tc_name(tool_call) -> str | None:
    """툴콜에서 안전하게 name을 추출 (dict / 객체 모두 지원).

    OpenAI function-style와 다양한 런타임을 고려해 function.name도 처리한다.
    """
    if isinstance(tool_call, dict):
        # 1) 일반 name
        name = tool_call.get("name")
        if isinstance(name, str) and name:
            return name
        # 2) OpenAI function 포맷
        fn = tool_call.get("function")
        if isinstance(fn, dict):
            fn_name = fn.get("name")
            if isinstance(fn_name, str) and fn_name:
                return fn_name
        # 3) 기타 호환 키
        tool_name = tool_call.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            return tool_name
        return None
    # 객체 속성 접근 (예외 안전)
    try:
        name_attr = getattr(tool_call, "name", None)
        if isinstance(name_attr, str) and name_attr:
            return name_attr
    except Exception:
        pass
    try:
        function_attr = getattr(tool_call, "function", None)
        if function_attr is not None:
            f_name = getattr(function_attr, "name", None)
            if isinstance(f_name, str) and f_name:
                return f_name
    except Exception:
        pass
    return None


def _tc_id(tool_call) -> str | None:
    """툴콜에서 안전하게 id를 추출 (dict / 객체 모두 지원)."""
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    try:
        return getattr(tool_call, "id", None)
    except Exception:
        return None


def _tc_args(tool_call) -> dict:
    """툴콜에서 안전하게 args를 dict로 추출 (dict / 객체 모두 지원).

    OpenAI function 포맷의 문자열 JSON도 지원한다.
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
                    import json as _json
                    return _json.loads(arguments)
                except Exception:
                    return {}
        arguments = tool_call.get("arguments")
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                import json as _json
                return _json.loads(arguments)
            except Exception:
                return {}
        return {}

    # 객체 속성 접근 (예외 안전)
    try:
        obj_args = getattr(tool_call, "args", None)
        if isinstance(obj_args, dict):
            return obj_args
    except Exception:
        pass
    try:
        function_attr = getattr(tool_call, "function", None)
        if function_attr is not None:
            fn_args = getattr(function_attr, "arguments", None)
            if isinstance(fn_args, dict):
                return fn_args
            if isinstance(fn_args, str):
                try:
                    import json as _json
                    return _json.loads(fn_args)
                except Exception:
                    return {}
    except Exception:
        pass
    try:
        arguments_attr = getattr(tool_call, "arguments", None)
        if isinstance(arguments_attr, dict):
            return arguments_attr
        if isinstance(arguments_attr, str):
            try:
                import json as _json
                return _json.loads(arguments_attr)
            except Exception:
                return {}
    except Exception:
        pass
    return {}


_MCP_TOOLS_CACHE: list | None = None
_MCP_TOOLS_ASYNC_LOCK: asyncio.Lock = asyncio.Lock()
_MCP_TOOLS_INIT_DONE: bool = False
# 서버별 동시 실행 제한 (소규모 동시화)
_MCP_SERVER_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
# 도구 객체 → 소속 서버명 매핑
_MCP_TOOL_TO_SERVER: dict[int, str] = {}


def _safe_tool_name_for_filter(tool_obj) -> str | None:
    try:
        n = getattr(tool_obj, "name", None)
        if isinstance(n, str) and n:
            return n
    except Exception:
        pass
    if isinstance(tool_obj, dict):
        n = tool_obj.get("name")
        if isinstance(n, str) and n:
            return n
    try:
        n = getattr(tool_obj, "__name__", None)
        if isinstance(n, str) and n:
            return n
    except Exception:
        pass
    return None


async def _load_mcp_tools_once(config: RunnableConfig) -> list:
    configurable = ResearchConfig.from_runnable_config(config)

    def _ensure_trailing_slash(u: str) -> str:
        return u if u.endswith("/") else (u + "/")

    # NOTE: MCP 서버는 StreamableHTTP를 사용할 수 있다.
    # 표준 StreamableHTTP 구현으로 교체했으므로 streamable_http로 지정한다.
    connections = {
        name: {"transport": "streamable_http", "url": _ensure_trailing_slash(url)}
        for name, url in configurable.mcp_servers.items()
    }
    # NOTE: MultiServerMCPClient는 도구 로딩 시 꼭 필요하지 않으므로 생성 생략
    # 필요 시점에 세션이 열리도록 load_mcp_tools(connection=...)만 사용한다

    async def _health_check(url: str, max_wait_s: float = 8.0, interval_s: float = 0.25) -> bool:
        """Wait until the MCP server responds 200 on /health or timeout.

        - Recomputes base 'scheme://netloc/health' from any given MCP endpoint.
        - Returns True if healthy within max_wait_s, otherwise False.
        """
        try:
            parsed = urlparse(url)
            health_url = f"{parsed.scheme}://{parsed.netloc}/health"
        except Exception:
            # Fallback: naive replacement
            health_url = url.replace("/mcp/", "/health").rstrip("/")

        deadline = asyncio.get_event_loop().time() + max_wait_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                # http_client raises on non-2xx; treat as not ready
                await http_client.get(health_url)
                return True
            except Exception:
                await asyncio.sleep(interval_s)
        return False

    # Ensure all MCP servers are healthy before attempting tool load
    try:
        health_tasks = [
            _health_check(conn_info["url"]) for conn_info in connections.values()
        ]
        health_results = await asyncio.gather(*health_tasks, return_exceptions=True)
        unhealthy = sum(
            1
            for r in health_results
            if not (isinstance(r, bool) and r is True)
        )
        if unhealthy:
            logger.warning(
                f"{unhealthy} MCP server(s) not healthy within timeout; proceeding with best effort"
            )
    except Exception as e:
        logger.warning(f"Health check scheduling failed: {type(e).__name__}: {e}")

    # Small initial delay to smooth out StreamableHTTP session startup
    await asyncio.sleep(0.5)

    # 안정적 로딩: 서버별 순차 로딩으로 초기 혼잡/교착을 방지한다.
    try:
        all_tools: list = []
        # 동시화는 해제 (세마포어 제거)
        for server_name, conn in connections.items():
            backoff_s = 0.4
            last_err: Exception | None = None
            server_tools: list = []
            for attempt in range(1, 4):
                try:
                    # 에페메럴 세션 기반 로딩 (도구는 connection을 캡처하여 호출 시 자체 세션을 엶)
                    server_tools = await load_mcp_tools(None, connection=conn)
                    last_err = None
                    break
                except Exception as inner:
                    last_err = inner
                    if attempt < 3:
                        await asyncio.sleep(backoff_s)
                        backoff_s *= 2
            if last_err is not None and not server_tools:
                logger.warning(
                    f"Failed to load tools from '{server_name}': {type(last_err).__name__}: {last_err}"
                )
            all_tools.extend(server_tools)

        filtered = []
        skipped = 0
        for t in all_tools:
            n = _safe_tool_name_for_filter(t)
            if isinstance(n, str) and n:
                filtered.append(t)
            else:
                skipped += 1
        logger.info(
            f"Loaded {len(filtered)} MCP tools" + (f" (skipped {skipped})" if skipped else "")
        )
        return filtered
    except Exception as e:
        logger.warning(f"Failed to load MCP tools: {e}")
        return []


async def get_all_tools(config: RunnableConfig):
    """모든 MCP 도구 로드 (동시 호출 안전, 1회 로드 캐시).

    병렬 연구 실행 시 동시 초기화 경쟁 조건으로 일부 도구에서
    AttributeError("name")가 발생할 수 있어 단일 로드로 캐시한다.
    """
    global _MCP_TOOLS_CACHE, _MCP_TOOLS_INIT_DONE
    # 이미 성공적으로 로드된 경우 즉시 반환
    if isinstance(_MCP_TOOLS_CACHE, list) and _MCP_TOOLS_CACHE:
        return list(_MCP_TOOLS_CACHE)

    # 첫 시도 이후에도 완전 실패(None/빈 리스트)라면 제한적 재시도를 허용한다
    if _MCP_TOOLS_INIT_DONE and (_MCP_TOOLS_CACHE is not None) and len(_MCP_TOOLS_CACHE) > 0:
        return list(_MCP_TOOLS_CACHE)

    async with _MCP_TOOLS_ASYNC_LOCK:
        # 더블 체크
        if isinstance(_MCP_TOOLS_CACHE, list) and _MCP_TOOLS_CACHE:
            return list(_MCP_TOOLS_CACHE)
        try:
            _MCP_TOOLS_CACHE = await _load_mcp_tools_once(config)
        finally:
            # 첫 시도 완료 플래그 (성공/실패 무관)
            _MCP_TOOLS_INIT_DONE = True
    return list(_MCP_TOOLS_CACHE or [])


async def _execute_tool_safely(tool, args, config):
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error executing tool: {str(e)}"


async def researcher(state: ResearcherState, config: RunnableConfig):
    """개별 연구원: MCP 도구로 연구 수행"""
    configurable = ResearchConfig.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])

    # NOTE: 주의! Researcher에서는 MCP 도구만 바인딩한다 (Supervisor의 ConductResearch/ResearchComplete와 분리)
    tools = await get_all_tools(config)
    if len(tools) == 0:
        raise ValueError("연구를 수행할 도구가 없습니다. MCP 서버를 확인하세요.")

    researcher_system_prompt = research_system_prompt.format(
        date=get_today_str(), 
        mcp_prompt=_get_mcp_prompt_description(tools),
    )

    base_model = init_chat_model(
        model_provider="openai",
        model="gpt-4.1-mini", # Rate Limit 때문에 임시로 제한이 더 넉넉한 모델로 변경
        temperature=0,
    )
    
    try:
        model = (
            base_model
            .bind_tools(tools, parallel_tool_calls=False, tool_choice=True)
            # .bind_tools(tools) # 동시에 호출하게 되면 에러 발생 가능성 높음
            .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        )
    except Exception as e:
        logger.warning(f"bind_tools failed, fallback to no-tools model: {type(e).__name__}: {e}")
        model = base_model.with_retry(stop_after_attempt=configurable.max_structured_output_retries)

    try:
        response = await model.ainvoke([SystemMessage(content=researcher_system_prompt)] + researcher_messages)
    except Exception as e:
        logger.warning(f"model.ainvoke failed, fallback to compress path: {type(e).__name__}: {e}")
        # researcher_tools로 가지 않고 바로 압축 단계로 넘어갈 수 있도록 최소 상태를 반환
        return {
            "researcher_messages": [AIMessage(content="도구 바인딩/호출 오류로 직접 압축 단계로 이동합니다.")],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1,
        }
    return Command(
        goto="researcher_tools",
        update={
            "researcher_messages": [response],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1,
        },
    )


async def researcher_tools(state: ResearcherState, config: RunnableConfig):
    """연구원 도구 실행 및 반복 제어"""
    configurable = ResearchConfig.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    most_recent_message = researcher_messages[-1]

    # 첫 응답에서 툴콜이 없을 수 있으므로, 설정값 기준 최소 N회는 researcher 루프를 더 돌도록 함
    if not most_recent_message.tool_calls:
        try:
            from src.config import ResearchConfig as _RC
            cfg = _RC.from_runnable_config(config)
            min_iters = max(0, int(getattr(cfg, "researcher_min_iterations_before_compress", 1)))
        except Exception:
            min_iters = 1
        if state.get("tool_call_iterations", 0) < min_iters:
            return Command(goto="researcher")
        return Command(goto="compress_research")

    # 주의: tool 실행 단계에서도 MCP 도구만 사용한다
    tools = await get_all_tools(config)

    # 도구 이름을 예외 없이 안전하게 추출하는 헬퍼
    def _safe_tool_name(tool_obj) -> str | None:
        # 1) 속성 name
        try:
            n = getattr(tool_obj, "name", None)
            if isinstance(n, str) and n:
                return n
        except Exception:
            pass
        # 2) 딕셔너리 포맷
        if isinstance(tool_obj, dict):
            n = tool_obj.get("name")
            if isinstance(n, str) and n:
                return n
        # 3) 클래스/함수의 __name__ (예: Pydantic BaseModel 도구 클래스)
        try:
            n = getattr(tool_obj, "__name__", None)
            if isinstance(n, str) and n:
                return n
        except Exception:
            pass
        return None

    tools_by_name: dict[str, any] = {}
    for tool in tools:
        name = _safe_tool_name(tool)
        if not isinstance(name, str) or not name:
            # 이름을 안전하게 얻지 못한 도구는 스킵 (잘못된 기본값으로 충돌 방지)
            continue
        tools_by_name[name] = tool

    tool_calls = most_recent_message.tool_calls

    # dict/객체 모두 안전하게 처리하도록 수정
    tool_outputs = []
    for tool_call in tool_calls:
        call_name = _tc_name(tool_call) or "unknown"
        call_id = _tc_id(tool_call) or "unknown"
        call_args = _tc_args(tool_call)

        # ResearchComplete 는 실제 호출 대상이 아니므로 관측만 남기고 스킵
        if call_name == "ResearchComplete":
            observation = "ResearchComplete"
        else:
            tool = tools_by_name.get(call_name)
            if tool is None:
                observation = f"Error executing tool: Unknown tool '{call_name}'"
            else:
                observation = await _execute_tool_safely(tool, call_args, config)

        tool_outputs.append(
            ToolMessage(content=observation, name=call_name, tool_call_id=call_id)
        )

    if state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls or any(
        (_tc_name(tool_call) == "ResearchComplete") for tool_call in most_recent_message.tool_calls
    ):
        return Command(goto="compress_research", update={"researcher_messages": tool_outputs})

    return Command(goto="researcher", update={"researcher_messages": tool_outputs})


async def compress_research(state: ResearcherState, config: RunnableConfig):
    """연구 결과 압축"""
    configurable = ResearchConfig.from_runnable_config(config)
    synthesizer_model = init_chat_model(
        model_provider="openai", 
        model=configurable.compression_model, 
        temperature=0,
    )

    researcher_messages = state.get("researcher_messages", [])
    compress_prompt = compress_research_system_prompt.format(
        date=get_today_str(),
    )
    researcher_messages.append(
        HumanMessage(content=compress_research_simple_human_message),
    )

    try:
        response = await synthesizer_model.ainvoke(
            [SystemMessage(content=compress_prompt)] + researcher_messages,
        )
        return {
            "compressed_research": str(response.content),
            "raw_notes": [
                "\n".join(
                    [
                        str(m.content)
                        for m in researcher_messages
                        if isinstance(m, (ToolMessage, AIMessage))
                    ]
                )
            ],
        }
    except Exception as e:
        logger.error(f"Research compression error: {e}")
        return {"compressed_research": "Error synthesizing research report", "raw_notes": []}



researcher_builder = StateGraph(
    state_schema=ResearcherState,
    input_schema=ResearcherInputState,
    output_schema=ResearcherOutputState, 
    config_schema=ResearchConfig,
)
researcher_builder.add_node("researcher", researcher)
researcher_builder.add_node("researcher_tools", researcher_tools)
researcher_builder.add_node("compress_research", compress_research)
researcher_builder.add_edge(START, "researcher")
researcher_builder.add_edge("compress_research", END)
researcher_graph = researcher_builder.compile()


