"""
LangGraph 기반 Deep Research Agent (A2A Supervisor + HITL 승인 루프)

기존 `deep_research_agent.py`의 전체 플로우를 유지하되,
Supervisor 서브그래프를 A2A 호출을 지원하는 그래프로 교체하고,
최종 보고서 이후 Human-In-The-Loop(HITL) 승인/개정 루프를 통합한다.

- clarify_with_user → write_research_brief → research_supervisor(A2A)
  → final_report_generation → hitl_final_approval ↔ revise_final_report
"""

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
import os
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
    # A2A로 감싼 Supervisor 그래프 호출
    from src.a2a_integration.a2a_lg_client_utils import A2AClientManager
    # 우선순위: 환경변수 SUPERVISOR_A2A_URL → ResearchConfig.analysis → 기본 8092
    try:
        cfg = ResearchConfig.from_runnable_config(config)
        cfg_url = getattr(cfg, "a2a_agent_endpoints", {}).get("analysis")
    except Exception:
        cfg_url = None
    supervisor_url = (
        os.getenv("SUPERVISOR_A2A_URL")
        or cfg_url
        or "http://localhost:8092"
    )
    async with A2AClientManager(base_url=supervisor_url) as client:
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
    """최종 보고서 생성 직후에만 승인 루프로 진입하도록 보장

    - clarify → write_research_brief → research_supervisor → final_report_generation
      단계가 끝난 이후에만 HITL 승인을 허용한다.
    - 이 노드는 final_report_generation 다음에만 호출된다.
    - 단, 설정상 HITL이 비활성화된 경우는 바로 종료한다.
    """
    # 1) runnable config에서 직접 확인 (ResearchConfig 모델 외 키도 허용)
    enable_hitl_cfg = False
    try:
        cfg = config.get("configurable", {}) if isinstance(config, dict) else getattr(config, "configurable", {}) or {}
        enable_hitl_cfg = bool(cfg.get("enable_hitl", False))
    except Exception:
        enable_hitl_cfg = False

    # 2) 환경변수 확인
    def _truthy(env_val: str | None) -> bool:
        if not env_val:
            return False
        return env_val.strip().lower() in {"1", "true", "yes", "y"}

    enable_hitl_env = _truthy(os.getenv("ENABLE_HITL")) or (os.getenv("HITL_MODE", "").strip().lower() == "interrupt")

    # final_report 가 존재하는지 최소 체크 (빈 문자열도 허용하되 키는 있어야 함)
    has_final = "final_report" in state
    if (enable_hitl_cfg or enable_hitl_env) and has_final:
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

# Durable execution for HIL: provide a checkpointer so interrupts can pause/resume
deep_research_graph_a2a = deep_researcher_builder_a2a.compile(checkpointer=InMemorySaver())


