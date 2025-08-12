# Step 1 — MCP Server를 LangGraph Agent의 도구로 통합하기

이 단계는 “LangGraph로 만든 Agent와 MCP Server를 `langchain-mcp-adapters`로 연결”하는 것을 목표로 합니다. 핵심은 `MultiServerMCPClient.get_tools()`로 받은 도구를 `llm.bind_tools()`에 주입해 LangGraph 에이전트가 MCP 도구를 직접 호출하게 만드는 것입니다. README의 대주제를 항상 상기하세요.

## 목표

- MCP(FastMCP) 서버를 만든 뒤, 기동하고 Tool List 를 LangGraph 에이전트에서 호출
- 예제 실행으로 스트리밍 응답과 도구 사용 로그 확인

## 준비 사항(사전 점검)

- Python 3.12+, uv 설치, Docker/Docker Compose 사용 가능
- 루트 `.env` 구성: `OPENAI_API_KEY`, `TAVILY_API_KEY` (필수)

```bash
# macOS/Linux
cp env.example .env  # env.example이 없으면 수동으로 .env를 생성해 키를 채워주세요
```

- 의존성 설치(이미 설치되어있을 수 있음)

```bash
uv venv && uv sync
```

## 1) MCP 서버 제작

- Tavily MCP 서버 제작을 위해 [fastmcp docs](/docs/fastmcp-llms_2.11.0.txt) 를 참고하세요.
  더 많은 fastmcp 내용이 필요하다면 [이 문서](/docs/fastmcp-llms-full_2.11.0.txt)도 괜찮습니다. (단 이 문서는 나눠서 읽도록 하세요)
- Tavily Client 사용을 위해서는 [Tavily Docs](/docs/tavily_pyton_docs.md) 를 참고하세요.

## 2) MCP 서버 기동

- 권장 스크립트 (루트 `.env`를 자동 로드)

```bash
./docker/mcp_docker.sh up
./docker/mcp_docker.sh test
```

- 직접 Compose

```bash
docker compose -f docker/docker-compose.mcp.yml up -d tavily-mcp
curl -fsSL http://localhost:3001/health | cat
```

포트 맵: 3001(Tavily), 3000(arXiv), 3002(Serper). 모든 서비스 정의는 `docker/docker-compose.mcp.yml` 참고.
예제 코드(`src/lg_agents/simple/simple_lg_agent_with_mcp.py`)는 기본적으로 Tavily MCP(3001)를 사용합니다.

## 2) 예제 실행(에이전트가 MCP 도구 사용 — get_tools → bind_tools)

```bash
python examples/step1_mcp_langgraph.py
```

기대 결과

- 콘솔에 “[도구 사용] search_web(...), search_news(...)” 등 도구 호출 로그 출력
- 모델 응답이 스트리밍으로 출력

## 3) 검증 체크리스트

- MCP Health: `curl -fsSL http://localhost:3001/health | cat` 가 200/healthy
- 예제 로그에 도구 호출 이름과 인자 표기
- 에러 없이 응답이 끝까지 출력

## 자주 겪는 이슈 및 해결

- **OPENAI_API_KEY 미설정**: 루트 `.env` 작성 후 다시 실행
- **MCP 연결 실패**: `./docker/mcp_docker.sh up` 재기동 후 `./docker/mcp_docker.sh test`
- **경로/슬래시 오류**: FastMCP는 종종 trailing slash 요구. 직접 호출 시 `<http://localhost:3001/mcp/>` 형태 확인

## 구현 관점 핵심 요약

- `MultiServerMCPClient.get_tools()` → LangGraph LLM에 `bind_tools()`로 연결
- 단일 Agent에서도 MCP 서버 여러 개를 동시에 연결 가능(풍부한 도구 세트)
- 이 구조가 Step 3의 멀티에이전트 구성의 토대가 됩니다

## 다이어그램(필수 참고)

- 시퀀스: [docs/diagrams/step1_sequence.md](../docs/diagrams/step1_sequence.md)
- 상태 전이: [docs/diagrams/step1_state.md](../docs/diagrams/step1_state.md)
- 아키텍처: [docs/diagrams/step1_architecture.md](../docs/diagrams/step1_architecture.md)

## 참고 문서(필독)

- FastMCP: [docs/fastmcp-llms_2.11.0.txt](../docs/fastmcp-llms_2.11.0.txt), [docs/fastmcp-llms-full_2.11.0.txt](../docs/fastmcp-llms-full_2.11.0.txt)
- LangGraph ReAct Agent: [docs/langgraph-llms_0.6.2.txt](../docs/langgraph-llms_0.6.2.txt), [docs/langgraph-llms-full_0.6.2.txt](../docs/langgraph-llms-full_0.6.2.txt)
- LangChain MCP Adapters: [docs/langchain-mcp-adapters.txt](../docs/langchain-mcp-adapters.txt)

## 다음 단계로

- Step 2에서 LangGraph 그래프를 A2A 규격 에이전트로 래핑하고, 클라이언트로 통신합니다. 실행 전 README의 대주제를 다시 확인하세요.
