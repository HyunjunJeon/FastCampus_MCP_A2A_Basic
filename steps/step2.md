# Step 2 — LangGraph Agent를 A2A로 통합하기 (재사용 가능한 OOP Wrapper)

이 단계는 Step 1에서 만든 LangGraph Agent를 “어떤 LangGraph 그래프든 쉽게 A2A Agent로 탈바꿈”시키는 범용 래퍼/서버 구조를 설계·구현합니다. README의 대주제(“MCP 서버 만들어서 LangGraph 와 연동 → A2A Agent 로 바꿈 → A2A 기반의 멀티에이전트 → A2A 기반의 HITL”)를 유지하며, 루트 `.env` 사용을 전제합니다.

## 목표

- LangGraph 그래프(CompiledStateGraph)를 입력 받아 A2A Agent로 감싸는 OOP 기반 `AgentExecutor` 구현
- 재사용 가능한 A2A 서버 빌더(Starlette 기반)로 모든 그래프를 동일 패턴으로 서빙
- 스트리밍/아티팩트/취소 등 A2A 0.3.0 상호운용성 준수

## 산출물(이 단계 완료 시)

- `src/a2a_integration/a2a_lg_agent_executor.py`: LangGraph → A2A로 감싸는 `LangGraphWrappedA2AExecutor`
- `src/a2a_integration/a2a_lg_utils.py`: 그래프→서버 빌더(`to_a2a_starlette_server`, `create_agent_card`)
- `src/a2a_integration/a2a_lg_embedded_server_manager.py`: 임베디드 서버 컨텍스트 매니저(테스트/예제에서 공용)
- 예제: `examples/step2_langgraph_a2a_client.py` (임베디드 서버 기동 후 클라이언트로 통신 검증)

## 설계 원칙(필수)

- **OOP(객체지향설계) 재사용성**: LangGraph 의존을 최소화하고, 주입 가능한 그래프/추출기 콜백으로 범용화
- **A2A Spec 만족**: 스트리밍 업데이트는 AI 텍스트만 안전 전송, 최종 결과는 아티팩트로 수집
- **취소 가능성 확실히 구현**: `cancel()` 지원으로 장시간 작업의 사용자 주도 중단

## 구현 순서

### 1) A2A Executor 설계/구현

- 파일: `src/a2a_integration/a2a_lg_agent_executor.py`

- 핵심 포인트:
  - 입력: `CompiledStateGraph`
  - 출력: A2A `AgentExecutor`로서 `execute()`, `cancel()` 구현
  - 스트림에서 도구 JSON 노이즈를 배제하고 AI 텍스트만 누적 전송
  - 최종 결과는 Task 아티팩트로 수집하여 일관된 수신 모델 유지

참고:

- `LangGraphWrappedA2AExecutor`에서 `astream` 루프 → 변경된 텍스트만 산출, `TaskUpdater`로 상태/아티팩트 갱신

### 2) A2A 서버 빌더 유틸리티

파일: `src/a2a_integration/a2a_lg_utils.py`

- 목표: “어떤 그래프(CompiledStateGraph)든” `AgentCard`만 주면 A2A 서버(A2AStarlette)로 노출

- 함수 구성:
  - `create_agent_card(...)`: streaming/push 등 Capabilities 포함 - A2A 표준 AgentCard 생성
  - `to_a2a_starlette_server(graph, agent_card, result_extractor)`: Executor + DefaultRequestHandler + A2AStarletteApplication 조립

### 3) 임베디드 서버 컨텍스트 매니저(개발 및 테스트 / 예제용)

파일: `src/a2a_integration/a2a_lg_embedded_server_manager.py`

- 목적: 테스트/예제에서 포트 자동 관리, health 체크, 기동/정리 일괄 처리

- 사용 예: `async with start_embedded_graph_server(graph, agent_card, host, port) as info:`

### 4) 예제로 통합 검증

- 파일: `examples/step2_langgraph_a2a_client.py`

- 흐름:
  1. Step1의 단일 MCP 에이전트 그래프를 먼저 생성(`SimpleLangGraphWithMCPAgent.create`)
  2. `start_embedded_graph_server(...)`로 A2A 서버로 변환
  3. `A2AClientManager`로 Card/Stream 확인, 질의 전송, 응답 수신

## 검증 기준

- Agent Card 엔드포인트 제공: `/.well-known/agent-card.json`
- 스트리밍 응답에서 AI 텍스트만 점진 출력(도구 JSON 노이즈 없음)
- 최종 응답이 아티팩트 형태로 수신됨
- `cancel()` 호출 시 사용자 메시지와 함께 정상 종료

## 다이어그램(필수 참고)

- 시퀀스: [docs/diagrams/step2_sequence.md](../docs/diagrams/step2_sequence.md)
- 상태 전이: [docs/diagrams/step2_state.md](../docs/diagrams/step2_state.md)
- 아키텍처: [docs/diagrams/step2_architecture.md](../docs/diagrams/step2_architecture.md)

## 트러블슈팅

- **Card URL/포트 불일치**: `AgentCard.url`에 서버 실제 base URL을 반영하세요
- **헬스체크 실패**: `to_a2a_starlette_server`로 만든 앱에 `/health` 추가했는지 확인
- **텍스트 중복 전송**: 델타 누적(증분) 로직(`accumulated_text`) 점검

## 참고 문서(필독)

- A2A Spec: [docs/a2a_spec.md](../docs/a2a_spec.md)
- A2A SDK: [docs/a2a-python_0.3.0.txt](../docs/a2a-python_0.3.0.txt)
- 샘플: [docs/a2a-samples_0.3.0.txt](../docs/a2a-samples_0.3.0.txt)
- LangGraph: [docs/langgraph-llms_0.6.2.txt](../docs/langgraph-llms_0.6.2.txt)

## 다음 단계로

Step 3에서 “Simple DeepResearch 프로젝트”로 MCP만으로 멀티에이전트를 구성하고, 같은 시스템을 A2A로 전환했을 때 상태 복잡성 감소/확장성 증가를 비교합니다. README의 대주제를 잊지 마세요.
