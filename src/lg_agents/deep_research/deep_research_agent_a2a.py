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
# A2A 호출 지점 안내
# - 이 노드는 A2A 대응 Supervisor 서브그래프를 실행합니다.
# - 내부 구현(`src/lg_agents/deep_research/supervisor_a2a_graph.py`)에서 다음 로직이 수행됩니다:
#   1) `ResearchConfig.get_a2a_endpoint("researcher")`로 Researcher A2A 엔드포인트를 조회
#   2) 엔드포인트가 활성(health 체크 200)일 경우, `query_a2a_agent()`로 원격 Researcher 에이전트에 A2A 호출
#   3) 원격 호출이 불가/실패하면 로컬 `build_researcher_subgraph()`로 폴백 실행
# - 따라서 이 `research_supervisor` 노드가 A2A 경계입니다. 네트워크 호출/타임아웃/장애 격리 등 운영 특성이 이 지점에서 발생합니다.
# - 관련 코드 경로:
#   - `src/lg_agents/deep_research/supervisor_a2a_graph.py::_execute_parallel_research`
#   - `src/a2a_integration/a2a_lg_client_utils.py::query_a2a_agent`
deep_researcher_builder_a2a.add_node("research_supervisor", build_supervisor_a2a_graph())
deep_researcher_builder_a2a.add_node("final_report_generation", final_report_generation)
deep_researcher_builder_a2a.add_edge(START, "clarify_with_user")
deep_researcher_builder_a2a.add_edge("research_supervisor", "final_report_generation")
deep_researcher_builder_a2a.add_edge("final_report_generation", END)

deep_research_graph_a2a = deep_researcher_builder_a2a.compile()


