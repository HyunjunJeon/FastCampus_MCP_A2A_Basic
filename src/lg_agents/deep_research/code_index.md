## Code Index - lg_agents/deep_research

Deep Research 그래프 구성요소와 HITL 통합 노드.

### Files

- __init__.py: 패키지 초기화.
- deep_research_agent.py: 전체 연구 플로우(명확화→브리프→수퍼바이저→최종 보고서) 메인 그래프.
- hitl_nodes.py: 최종 승인 요청 및 개정 루프(HITL) 공용 노드/상태.
- prompts.py: 프롬프트 상수/유틸.
- researcher_graph.py: MCP 도구 리서처 서브그래프(도구 실행/압축).
- supervisor_graph.py: 연구 반복 제어/종료 조건/병렬 실행 조정.
- shared.py: 공용 리듀서/도구 스키마/메시지→노트 추출 유틸.
 - supervisor_a2a_graph.py: Supervisor를 A2A 원격 리서처 호출로 확장(실패 시 로컬 서브그래프 폴백).
 - deep_research_agent_a2a.py: 메인 그래프에서 Supervisor만 A2A 버전으로 교체한 그래프 진입점.
 - researcher_agent_a2a.py: 리서처 서브그래프를 단독 A2A 에이전트로 래핑.

### Related

- 상위: [../code_index.md](../code_index.md)
- 베이스: [../base/code_index.md](../base/code_index.md)
- 전체: [../../code_index.md](../../code_index.md)