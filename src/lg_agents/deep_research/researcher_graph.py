"""
Researcher 서브그래프 모듈

MCP 도구를 활용해 정보 수집(ReAct)과 결과 압축을 수행하는 연구원 그래프를 정의합니다.
"""

from __future__ import annotations

from typing import Annotated
import operator

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
from .shared import ResearchComplete
from .prompts import (
    research_system_prompt,
    compress_research_system_prompt,
    compress_research_simple_human_message,
    get_today_str,
)
from langchain_mcp_adapters.client import MultiServerMCPClient


logger = get_logger(__name__)


class ResearcherState(TypedDict):
    """Researcher 서브그래프 내부 상태"""

    researcher_messages: Annotated[list, operator.add]
    tool_call_iterations: int
    research_topic: str
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer]


class ResearcherOutputState(BaseModel):
    """Researcher 서브그래프 출력 상태"""

    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []


def _get_mcp_prompt_description(tools: list) -> str:
    return "\n".join([f"{tool.name}: {tool.description}" for tool in tools])


def _tc_name(tool_call) -> str | None:
    """툴콜에서 안전하게 name을 추출 (dict / 객체 모두 지원)."""
    if isinstance(tool_call, dict):
        return tool_call.get("name")
    return getattr(tool_call, "name", None)


def _tc_id(tool_call) -> str | None:
    """툴콜에서 안전하게 id를 추출 (dict / 객체 모두 지원)."""
    if isinstance(tool_call, dict):
        return tool_call.get("id")
    return getattr(tool_call, "id", None)


def _tc_args(tool_call) -> dict:
    """툴콜에서 안전하게 args를 dict로 추출 (dict / 객체 모두 지원)."""
    if isinstance(tool_call, dict):
        args = tool_call.get("args")
    else:
        args = getattr(tool_call, "args", None)
    return args if isinstance(args, dict) else {}


async def get_all_tools(config: RunnableConfig):
    """모든 MCP 도구 로드"""
    configurable = ResearchConfig.from_runnable_config(config)
    mcp_client = MultiServerMCPClient(
        {name: {"transport": "streamable_http", "url": url} for name, url in configurable.mcp_servers.items()}
    )
    tools = [ResearchComplete]
    try:
        mcp_tools = await mcp_client.get_tools()
        tools.extend(mcp_tools)
        logger.info(f"Loaded {len(mcp_tools)} MCP tools")
    except Exception as e:
        logger.warning(f"Failed to load MCP tools: {e}")
    return tools


async def _execute_tool_safely(tool, args, config):
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error executing tool: {str(e)}"


async def researcher(state: ResearcherState, config: RunnableConfig):
    """개별 연구원: MCP 도구로 연구 수행"""
    configurable = ResearchConfig.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])

    tools = await get_all_tools(config)
    if len(tools) == 0:
        raise ValueError("연구를 수행할 도구가 없습니다. MCP 서버를 확인하세요.")

    researcher_system_prompt = research_system_prompt.format(
        date=get_today_str(), 
        mcp_prompt=_get_mcp_prompt_description(tools),
    )

    model = (
        init_chat_model(
            model_provider="openai",
            model=configurable.research_model,
            temperature=0,
        )
        .bind_tools(tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    )

    response = await model.ainvoke([SystemMessage(content=researcher_system_prompt)] + researcher_messages)
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

    if not most_recent_message.tool_calls:
        return Command(goto="compress_research")

    tools = await get_all_tools(config)
    tools_by_name = {}
    for tool in tools:
        if hasattr(tool, "name"):
            name = tool.name
        elif isinstance(tool, dict) and "name" in tool:
            name = tool["name"]
        else:
            name = "web_search"
        tools_by_name[name] = tool

    tool_calls = most_recent_message.tool_calls

    # dict/객체 모두 안전하게 처리하도록 수정
    tool_outputs = []
    for tool_call in tool_calls:
        call_name = _tc_name(tool_call) or "unknown"
        call_id = _tc_id(tool_call) or "unknown"
        call_args = _tc_args(tool_call)

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


def build_researcher_subgraph() -> StateGraph:
    """Researcher 서브그래프 생성 및 컴파일 반환"""
    builder = StateGraph(
        state_schema=ResearcherState, 
        output_schema=ResearcherOutputState, 
        config_schema=ResearchConfig,
    )
    builder.add_node("researcher", researcher)
    builder.add_node("researcher_tools", researcher_tools)
    builder.add_node("compress_research", compress_research)
    builder.add_edge(START, "researcher")
    builder.add_edge("compress_research", END)
    return builder.compile()


