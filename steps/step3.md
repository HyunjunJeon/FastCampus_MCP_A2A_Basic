# Step 3 — MCP만으로 멀티에이전트 구현 후 A2A로 한계 극복하기 (Project: Simple DeepResearch)

이 단계는 Step 1~2의 기반 위에서 "MCP만으로 Deep Research 멀티에이전트"를 구축하고, 같은 기능을 A2A로 이전했을 때 상태(State) 복잡도와 확장성의 차이를 체감하도록 설계되었습니다. README의 대주제("MCP → A2A → 멀티에이전트 → HITL")를 유지하세요.

## 목표

- MCP 서버 3~4개(Tavily/Serper/arXiv 등)를 LangGraph의 `create_react_agent` 기반 에이전트들에 부착
- 다음 역할로 구성된 멀티에이전트 파이프라인을 LangGraph 그래프(Supervisor + Sub-graphs)로 구현
  - Supervisor(작업 전달 Router)
  - Planner(연구 계획 수립)
  - Researcher(도구로 자료 조사) - MCP 서버
  - Writer(보고서 작성)
- “MCP Only” 버전의 복잡한 공유 State(깊은 서브그래프 구조) 경험
- 동일 파이프라인을 Step 2의 A2A Wrapper로 옮겼을 때 “단일 Agent 레벨 상태관리”의 단순함/확장성 비교

## 산출물

- MCP-only DeepResearch 실행 예제: `examples/step3_multiagent_systems.py`
- 비교 결과 JSON: `reports/comparison_results_YYYYMMDD_HHMMSS.json`
- (기 존재) 임베디드 A2A 서버 유틸을 활용한 A2A 전환 실행 경로

## 구축 순서(요약)

### 1) MCP-only 멀티에이전트 그래프

- 각 역할(Planner/Researcher/Writer/Evaluator)을 `create_react_agent`로 구성
- 도구 주입: `MultiServerMCPClient.get_tools()`로 MCP 도구 로딩 후 LLM에 bind
- Supervisor가 라우팅하는 구조로 서브그래프 연결(Supervisor → Planner → Researcher → Writer → Evaluator)
- 이때 Supervisor/Researcher의 메시지/노트/중간 산출물 공유 때문에 State 객체가 깊고 넓게 확장(복잡도 상승)

### 2) 실행 및 레포트 저장

- `python examples/step3_multiagent_systems.py`
- 동일한 연구 주제로 MCP-only vs (Step2 임베디드) A2A 버전 실행
- 실행 시간, 병렬성, 상태 깊이 지표 등을 JSON으로 저장

### 3) A2A로 전환하여 단순화

- Step 2의 `to_a2a_starlette_server` + `LangGraphWrappedA2AExecutor`로 각 역할을 “독립 A2A Agent”로 노출함.
- 상태(State) 관점: A2A는 에이전트 단위 독립 상태 + 표준 메시징이므로, LangGraph 내부의 공유 State를 얕게 가져가거나 분리 가능
- 본 Step3 예제의 임베디드 A2A 서버 포트: 8092(DeepResearch), 8091(Researcher), 8090(Supervisor)

## 검증 기준

- MCP-only 실행 성공 및 도구 호출 로그 확인(각 역할별로 MCP 도구 사용)
- A2A 전환 실행 성공 및 동일/유사 품질의 결과 산출
- 비교 JSON에 시간/성능/상태복잡성(요약 지표) 기록

## 다이어그램(필수 참고)

- 시퀀스: [docs/diagrams/step3_sequence.md](../docs/diagrams/step3_sequence.md)
- 상태 전이: [docs/diagrams/step3_state.md](../docs/diagrams/step3_state.md)
- 아키텍처: [docs/diagrams/step3_architecture.md](../docs/diagrams/step3_architecture.md)

## 왜 A2A가 더 단순해지는가?

- MCP-only: Supervisor와 Sub-graph 사이에서 공유 State가 누적/확장 → 깊은 중첩/동시성에 취약
- A2A: 역할 단위의 별도 Agent + 표준 메시징(SSE/JSON-RPC) → 각 Agent가 자신의 상태만 관리
- 결과: 역할 추가/교체/확장이 쉬워지고, 운영·관찰(로그/메트릭/헬스체크)이 표준화됨

## 트러블슈팅

- **도구 로드 실패**: MCP URL의 trailing slash 및 포트 확인, `langchain-mcp-adapters` 버전 확인(README의 docs 참조)
- **서브그래프 라우팅 오류**: Supervisor에서 노드명/조건 분기 확인
- **비교 JSON 미생성**: 예제 스크립트 내 저장 경로/권한 확인

## 참고 문서(필독)

- LangGraph: [docs/langgraph-llms_0.6.2.txt](../docs/langgraph-llms_0.6.2.txt)
- MCP: [docs/fastmcp-llms_2.11.0.txt](../docs/fastmcp-llms_2.11.0.txt)
- A2A: [docs/a2a-python_0.3.0.txt](../docs/a2a-python_0.3.0.txt)

## 다음 단계로

- Step 4에서 최종 보고서에 사람의 판단을 끼워 넣는 HITL(Human-In-The-Loop) 승인/피드백 루프를 추가합니다. 보고서가 거절되면 이유를 받아 개정 루프를 돌도록 설계합니다.
