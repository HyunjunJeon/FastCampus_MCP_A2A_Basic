# Agentic Code Guide — Step 1 → 4 완주 안내

본 가이드는 현재 코드 기준으로 Step 1부터 Step 4까지 순서대로 실행하며 프로젝트를 완성하는 최소 실행 경로를 제공합니다. 각 단계는 루트 `.env` 사용과 도커 기반 MCP 서버 기동을 전제로 합니다.

## 공통 전제

- 루트 `.env`에 `OPENAI_API_KEY`, `TAVILY_API_KEY`(선택: `SERPER_API_KEY`) 설정
- MCP 서버(3000/3001/3002): `./docker/mcp_docker.sh up && ./docker/mcp_docker.sh test`
- 문서 인덱스: `code_index.md`와 `src/code_index.md`를 신뢰 소스로 삼습니다.

## Step 1 — MCP → LangGraph 에이전트 도구화

- 예제: `python examples/step1_mcp_langgraph.py`
- 코드 포인트: `src/lg_agents/simple/simple_lg_agent_with_mcp.py`
  - `MultiServerMCPClient.get_tools()`로 Tavily MCP(기본 3001) 도구 로딩
  - `create_react_agent`에 `bind_tools` 형태로 주입
- 기대: 콘솔에 도구 호출 로그 + AI 스트리밍 텍스트

## Step 2 — LangGraph → A2A 임베디드 서버

- 예제: `python examples/step2_langgraph_a2a_client.py`
- 핵심 유틸: `src/a2a_integration/a2a_lg_utils.py`
  - `create_agent_card(...)` → A2A 표준 AgentCard(JSON)
  - `to_a2a_starlette_server(...)` → `LangGraphWrappedA2AExecutor` + `DefaultRequestHandler` + `A2AStarletteApplication`
- 임베디드 실행: `start_embedded_graph_server(...)`가 `/health` + `/.well-known/agent-card.json` 제공
- 클라이언트: `A2AClientManager`로 텍스트(`send_query`)/JSON(`send_data`) 전송, 스트리밍/아티팩트 수신

## Step 3 — 멀티에이전트 비교(LangGraph vs A2A)

- 예제: `python examples/step3_multiagent_systems.py`
- 포트: 8090(Deep/HITL), 8091(Researcher), 8092(Supervisor)
- 흐름: A2A 에이전트 3종을 임베디드 서버로 띄운 뒤 비교 실행 → `reports/comparison_results_YYYYMMDD_HHMMSS.json` 저장

## Step 4 — HITL(Human-In-The-Loop) 통합

- 예제: `python examples/step4_hitl_demo.py`
- 웹: `http://localhost:8000` (WS: `ws://localhost:8000/ws`)
- A2A: 8090/8091/8092 임베디드 서버 자동 기동 + Agent Card/Health 노출
- 핵심 모듈: `src/hitl/*`, `src/hitl_web/*`, `src/lg_agents/deep_research/hitl_nodes.py`
- 설정: `ResearchConfig.max_revision_loops`(기본 2), `ALLOW_CLARIFICATION`(Step4는 0 권장)

## 자주 겪는 이슈와 해결

- OPENAI_API_KEY/TAVILY_API_KEY 미설정 → 루트 `.env` 확인
- MCP 연결 실패 → `./docker/mcp_docker.sh up && ./docker/mcp_docker.sh test`
- A2A Card/Health 미노출 → `start_embedded_graph_server` 사용 및 포트 충돌 여부 확인
- Redis 미가동(HITL) → `docker compose -f docker/docker-compose.mcp.yml up -d redis`

## 마무리 팁

- 모든 단계는 로그를 `logs/stepN_*.log`로 남기도록 스크립트에서 보조합니다(주로 Step3/4).
- A2A는 최종 결과를 아티팩트로 제공하므로, 스트리밍 텍스트와 별개로 JSON(DataPart) 병합 결과(`send_data_merged`)를 신뢰하세요.
