# MCP 와 A2A 로 개발하는 Multi Agent

FastCampus 온라인강의 "MCP 와 A2A 로 개발하는 Multi Agent"(Part2 - Chapter2. LangGraph와 MCP & A2A) 실습 저장소입니다. 본 저장소는 Step 1 → 4를 순서대로 따라가면 멀티 에이전트 시스템이 완성되도록 구성되어 있습니다.

[제 강의 전용 할인 페이지](https://fastcampus.co.kr/secret_online_jhjagent)

---

## Quick Start (개발환경 설정)

> **모든 수강생이 동일한 개발환경을 구성할 수 있도록 `setup.sh` 스크립트를 제공합니다.**

### 1단계: uv 패키지 매니저 설치

[uv](https://docs.astral.sh/uv/)는 Rust로 작성된 초고속 Python 패키지 관리자입니다.

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS (Homebrew)
brew install uv

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

설치 후 터미널을 재시작하세요.

### 2단계: 개발환경 자동 설정

```bash
./setup.sh
```

이 스크립트는 다음 3가지를 자동으로 수행합니다:

| 단계 | 설명 |
|------|------|
| **[1/3] uv 확인** | uv 설치 여부 확인, 미설치 시 안내 후 종료 |
| **[2/3] 의존성 설치** | `uv sync --frozen` 실행 → `.venv` 생성 및 패키지 설치 |
| **[3/3] VSCode 설정** | `.vscode/settings.json` 생성 → Python 인터프리터 자동 설정 |

### 3단계: API 키 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 API 키를 입력하세요:

```bash
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
SERPER_API_KEY=your_serper_api_key
```

- [OPENAI_API_KEY 발급](https://platform.openai.com/api-keys)
- [TAVILY_API_KEY 발급](https://www.tavily.com/)
- [SERPER_API_KEY 발급](https://serper.dev/)

### 4단계: Docker 환경 시작 (MCP 서버)

```bash
./docker/mcp_docker.sh build   # 이미지 빌드
./docker/mcp_docker.sh up      # 서비스 시작
./docker/mcp_docker.sh test    # 헬스체크
```

### setup.sh 개별 명령어

```bash
./setup.sh          # 전체 설정 (기본값)
./setup.sh uv       # uv 설치 확인만
./setup.sh sync     # 의존성 설치만
./setup.sh vscode   # VSCode 설정만
./setup.sh help     # 도움말
```

---

## 프로젝트 개요 및 코드 인덱스

- 전체 코드 인덱스: [code_index.md](code_index.md)
- 소스코드 인덱스 허브: [src/code_index.md](src/code_index.md)
- 하위 모듈 코드 인덱스
  - A2A 통합: [src/a2a_integration/code_index.md](src/a2a_integration/code_index.md)
  - 설정: [src/config/code_index.md](src/config/code_index.md)
  - HITL 코어: [src/hitl/code_index.md](src/hitl/code_index.md)
  - HITL 웹: [src/hitl_web/code_index.md](src/hitl_web/code_index.md)
  - LangGraph 에이전트: [src/lg_agents/code_index.md](src/lg_agents/code_index.md)
  - MCP 서버: [src/mcp_servers/code_index.md](src/mcp_servers/code_index.md)
  - 유틸리티: [src/utils/code_index.md](src/utils/code_index.md)

항상 인덱스를 최신 소스로 신뢰합니다.
불일치를 발견하면 인덱스를 먼저 갱신하고 코드를 정리하세요.

---

## 요구 사항

- Python 3.12+
- [uv 패키지 매니저](https://docs.astral.sh/uv/getting-started/installation/)
- Docker / Docker Compose (MCP 서버 및 Redis 실행용)

권장 라이브러리/버전(정확한 버전은 `pyproject.toml` 참고):

- LangGraph ≥ 1.0.0
- FastMCP ≥ 2.14.0
- LangChain MCP Adapters ≥ 0.2.0
- a2a-sdk ≥ 0.3.22

참고 문서 모음: `docs/`

- LangGraph-LLMs: [docs/langgraph-llms_0.6.2.txt](docs/langgraph-llms_0.6.2.txt), [docs/langgraph-llms-full_0.6.2.txt](docs/langgraph-llms-full_0.6.2.txt)
- FastMCP: [docs/fastmcp-llms_2.11.0.txt](docs/fastmcp-llms_2.11.0.txt), [docs/fastmcp-llms-full_2.11.0.txt](docs/fastmcp-llms-full_2.11.0.txt)
- A2A: [docs/a2a-python_0.3.0.txt](docs/a2a-python_0.3.0.txt), [docs/a2a-samples_0.3.0.txt](docs/a2a-samples_0.3.0.txt)
- 다이어그램 인덱스: [docs/diagrams/code_index.md](docs/diagrams/code_index.md)

---

## MCP 서버 포트 정보

| 서비스 | 포트 | 헬스체크 |
|--------|------|----------|
| ArXiv MCP | <http://localhost:3000> | `/health` |
| Tavily MCP | <http://localhost:3001> | `/health` |
| Serper MCP | <http://localhost:3002> | `/health` |
| Redis Commander | <http://localhost:8081> | (admin/mcp2025) |

```bash
# MCP 서버 중지/삭제
./docker/mcp_docker.sh down
```

---

## Step-by-Step 실행 가이드 (Step 1~4)

아래 명령은 루트에서 실행합니다. 예제는 모두 `examples/`에 있습니다.

### Step 1. MCP → LangGraph 에이전트 도구화

- 목표: MCP 서버 도구를 LangGraph 에이전트에서 사용
- 준비: MCP(Tavily 등) 기동, `.env`에 OPENAI/TAVILY 키 설정

```bash
python examples/step1_mcp_langgraph.py
```

출력: 도구 호출 로그, 스트리밍 응답

### Step 2. LangGraph → A2A 통합(임베디드 서버)

- 목표: LangGraph 그래프를 A2A 규격 에이전트로 래핑 후 클라이언트로 통신

```bash
python examples/step2_langgraph_a2a_client.py
```

임베디드 A2A 서버가 자동 기동(기본 0.0.0.0:8000). 필수 엔드포인트:

- Agent Card(JSON): `/.well-known/agent-card.json`
- JSON-RPC: `/`
- Health: `/health`

### Step 3. 멀티에이전트 비교 (LangGraph vs A2A)

- 목표: 동일 주제로 두 방식을 비교 실행하고 결과 저장

실행:

```bash
python examples/step3_multiagent_systems.py
```

결과 저장: `reports/comparison_results_YYYYMMDD_HHMMSS.json`

### Step 4. HITL(Human-In-The-Loop) 통합 데모

- 목표: 승인/피드백 루프가 포함된 Deep Research + 웹 대시보드 + A2A 서버

동작 요약

- Redis 자동 기동(docker)
- HITL 웹 API/대시보드: <http://localhost:8000> (WS: `ws://localhost:8000/ws`)
- Deep Research(HITL) A2A 서버: <http://localhost:8090>
  - Agent Card(JSON): `<http://localhost:8090/.well-known/agent-card.json>`
  - Health: `<http://localhost:8090/health>`

실행:

```bash
python examples/step4_hitl_demo.py
```

대시보드에서 연구 시작/승인/거부/피드백을 실시간으로 확인합니다. 취소/부분결과 저장도 지원합니다.

---

## 포트 맵(요약)

- MCP: 3000(arXiv), 3001(Tavily), 3002(Serper)
- Redis Commander: 8081
- A2A(임베디드): 8000(Step2)
- HITL Web: 8000, HITL A2A Agents: 8090(Deep), 8091(Researcher), 8092(Supervisor) (Step4)

---

## 테스트

일반 테스트:

```bash
uv run pytest -q
```

## 문서

- 단계별 가이드: [steps/code_index.md](steps/code_index.md)
- 다이어그램: [docs/diagrams/code_index.md](docs/diagrams/code_index.md)
- HITL 통합 스펙: [steps/hitl_integration_spec.md](steps/hitl_integration_spec.md)
- 레퍼런스: `docs/` 내 각 파일 참조(상단 “요구 사항” 섹션 링크)

항상 이 README의 대주제(“MCP → A2A → 멀티에이전트 → HITL”)를 잊지 말고,  
각 Step 문서의 지시를 순서대로 수행하세요.

---

## 업데이트 사항

1. a2a-samples 추가(2025-12-26)
조금 더 다양한 예제를 확인하실 수 있도록 a2a-samples 레포지토리를 내부에 포함했습니다.
아주 쉬운 레벨의 내용부터 시작해서 langgraph-a2a 연동 샘플까지 다 포함되어 있습니다.

강의 내용과 함께 보신다면 더욱 도움이 되실 것입니다.

---

## 라이선스

자세한 내용은 [LICENSE](/LICENSE) 파일을 참고하세요.
