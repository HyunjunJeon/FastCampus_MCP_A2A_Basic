"""
LangGraph 기반 Deep Research Agent (A2A Supervisor 버전)

기존 `deep_research_agent.py`의 전체 플로우를 유지하되,
Supervisor 서브그래프를 A2A 호출을 지원하는 그래프로 교체한다.

- clarify_with_user → write_research_brief → research_supervisor(A2A) → final_report_generation
"""

from langgraph.graph import START, END, StateGraph

from src.config import ResearchConfig
from .deep_research_agent import (
    AgentState,
    clarify_with_user,
    write_research_brief,
    final_report_generation,
)
from .supervisor_a2a_graph import build_supervisor_a2a_graph


# 빌더 구성: Supervisor만 A2A 버전으로 대체
deep_researcher_builder_a2a = StateGraph(state_schema=AgentState, config_schema=ResearchConfig)
deep_researcher_builder_a2a.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder_a2a.add_node("write_research_brief", write_research_brief)
deep_researcher_builder_a2a.add_node("research_supervisor", build_supervisor_a2a_graph())
deep_researcher_builder_a2a.add_node("final_report_generation", final_report_generation)
deep_researcher_builder_a2a.add_edge(START, "clarify_with_user")
deep_researcher_builder_a2a.add_edge("research_supervisor", "final_report_generation")
deep_researcher_builder_a2a.add_edge("final_report_generation", END)

deep_research_graph_a2a = deep_researcher_builder_a2a.compile()


