"""
LangGraph 기반 Deep Research Agent (A2A Supervisor + HITL 승인 루프)

기존 `deep_research_agent.py`의 전체 플로우를 유지하되,
Supervisor 서브그래프를 A2A 호출을 지원하는 그래프로 교체하고,
최종 보고서 이후 Human-In-The-Loop(HITL) 승인/개정 루프를 통합한다.

- clarify_with_user → write_research_brief → research_supervisor(A2A)
  → final_report_generation → hitl_final_approval ↔ revise_final_report
"""

from langgraph.graph import START, END, StateGraph
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.config import ResearchConfig
from .deep_research_agent import (
    clarify_with_user,
    write_research_brief,
    final_report_generation,
)
from .hitl_nodes import HITLAgentState, hitl_final_approval, revise_final_report
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

async def call_supervisor_a2a(state: HITLAgentState, config: RunnableConfig) -> HITLAgentState:
    # TODO: 여기서 A2A 로 감싸진 build_supervisor_a2a_graph 를 Client 로써 호출
    from a2a_integration.a2a_lg_client_utils import A2AClientManager
    async with A2AClientManager(base_url="http://localhost:8090") as client:
        # NOTE: Supervisor 그래프에서 호출받는 로직에 맞게 데이터 구성
        result = await client.send_data_merged(
            {
                "research_brief": state.get("research_brief", ""),
                "supervisor_messages": [{
                    "role": "human",
                    "content": state.get("research_brief", "")
                }]
            },
            merge_mode="smart",
        )
        state = {**state, **result}
    return state

async def route_after_final_report(state: HITLAgentState, config: RunnableConfig) -> Command:
    """최종 보고서 이후 HITL 활성 여부에 따라 다음 경로를 결정"""
    configurable = ResearchConfig.from_runnable_config(config)
    if bool(getattr(configurable, "enable_hitl", False)):
        return Command(goto="hitl_final_approval")
    return Command(goto=END)

# 빌더 구성: Supervisor는 A2A 버전으로, 상태 스키마는 HITL 확장으로 설정
deep_researcher_builder_a2a = StateGraph(state_schema=HITLAgentState, config_schema=ResearchConfig)

# 노드
deep_researcher_builder_a2a.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder_a2a.add_node("write_research_brief", write_research_brief)
deep_researcher_builder_a2a.add_node("research_supervisor", call_supervisor_a2a)
deep_researcher_builder_a2a.add_node("final_report_generation", final_report_generation)
deep_researcher_builder_a2a.add_node("route_after_final_report", route_after_final_report)
deep_researcher_builder_a2a.add_node("hitl_final_approval", hitl_final_approval)
deep_researcher_builder_a2a.add_node("revise_final_report", revise_final_report)
# 엣지
deep_researcher_builder_a2a.add_edge(START, "clarify_with_user")
deep_researcher_builder_a2a.add_edge("research_supervisor", "final_report_generation")
deep_researcher_builder_a2a.add_edge("final_report_generation", "route_after_final_report")
deep_researcher_builder_a2a.add_edge("revise_final_report", "hitl_final_approval")
deep_researcher_builder_a2a.add_edge("hitl_final_approval", END)

deep_research_graph_a2a = deep_researcher_builder_a2a.compile()


