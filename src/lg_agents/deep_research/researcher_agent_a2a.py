"""
Researcher A2A Agent Graph

`researcher_graph.py`의 서브그래프를 A2A로 단독 실행할 수 있도록 래핑.
입력 텍스트(사용자 질의)를 `researcher_messages`/`research_topic`으로 변환하고,
서브그래프 완료 후 `messages`에 AIMessage를 기록해 A2A 응답으로 제공한다.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph import START, END, StateGraph
from langchain_core.messages import HumanMessage, AIMessage
from typing_extensions import TypedDict

from src.config import ResearchConfig
from .researcher_graph import build_researcher_subgraph


class ResearcherA2AState(TypedDict):
    messages: Annotated[list, list.__add__]
    researcher_messages: Annotated[list, list.__add__]
    research_topic: str
    compressed_research: str
    raw_notes: Annotated[list[str], list.__add__]


def build_researcher_a2a_graph():
    researcher_subgraph = build_researcher_subgraph()

    async def prepare(state: ResearcherA2AState, config):
        messages = state.get("messages", [])
        if messages:
            user_text = getattr(messages[-1], "content", "")
        else:
            user_text = ""
        return {
            "researcher_messages": [HumanMessage(content=user_text)],
            "research_topic": user_text,
        }

    async def finalize(state: ResearcherA2AState, config):
        text = state.get("compressed_research", "") or "No research synthesized."
        return {
            "messages": [AIMessage(content=text)],
        }

    builder = StateGraph(state_schema=ResearcherA2AState, config_schema=ResearchConfig)
    builder.add_node("prepare", prepare)
    builder.add_node("researcher_subgraph", researcher_subgraph)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "prepare")
    builder.add_edge("researcher_subgraph", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


