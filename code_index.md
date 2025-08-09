# Code Index

프로젝트 전반 구조와 각 파일의 역할을 한눈에 파악할 수 있도록 정리했습니다. 세부 하위 모듈에는 별도의 `code_index.md`가 있으며, 아래 참조 링크로 이동할 수 있습니다.

## Code Tree

```bash
fc_mcp_a2a/
├─ Dockerfile
├─ docker-start.sh
├─ docker-start.bat
├─ Makefile
├─ pyproject.toml
├─ README.md
├─ LICENSE
├─ uv.lock
├─ fc_lecture.png
├─ docker/
│  ├─ Dockerfile.mcp
│  ├─ docker-compose.mcp.yml
│  ├─ mcp_docker.sh
│  └─ mcp_docker.ps1
├─ docs/
│  ├─ a2a_spec.md
│  ├─ a2a-python_0.3.0.txt
│  ├─ a2a-samples_0.3.0.txt
│  ├─ fastmcp-llms_2.10.6.txt
│  ├─ fastmcp-llms-full_2.10.6.txt
│  ├─ langchain-llms.txt
│  ├─ langchain-mcp-adapters.txt
│  ├─ langgraph-llms_0.6.2.txt
│  ├─ langgraph-llms-full_0.6.2.txt
│  ├─ lg-deep-research-example.txt
│  ├─ tavily_pyton_docs.md
│  └─ diagrams/
│     ├─ code_index.md
│     ├─ step1_sequence.md
│     ├─ step1_state.md
│     ├─ step1_architecture.md
│     ├─ step2_sequence.md
│     ├─ step2_state.md
│     ├─ step2_architecture.md
│     ├─ step3_sequence.md
│     ├─ step3_state.md
│     ├─ step3_architecture.md
│     ├─ step4_sequence.md
│     ├─ step4_state.md
│     └─ step4_architecture.md
├─ examples/
│  ├─ README.md
│  ├─ compare_systems.py
│  ├─ deep_research_a2a_client_comparison.py
│  ├─ step1_mcp_langgraph.py
│  ├─ step2_langgraph_a2a_client.py
│  ├─ step3_multiagent_systems.py
│  └─ step4_hitl_demo.py
├─ reports/
│  └─ comparison_results_YYYYMMDD_HHMMSS.json
├─ scripts/
│  ├─ run_step3.sh
│  └─ run_step3.ps1
├─ steps/
│  ├─ hitl_integration_spec.md
│  ├─ step1.md
│  ├─ step2.md
│  ├─ step3.md
│  └─ step4.md
├─ tests/
│  ├─ run_tests.py
│  ├─ debug_message_test.py
│  ├─ integration_test.py
│  ├─ test_a2a_integration.py
│  ├─ test_artifact_streaming.sh
│  ├─ test_comprehensive_hitl.py
│  ├─ test_e2e_final_validation.py
│  ├─ test_env_and_streaming.py
│  ├─ test_hitl_approval_flow.py
│  ├─ test_hitl_integration.py
│  ├─ test_integration_steps_1_to_4.py
│  ├─ test_mcp_tools_validation.py
│  ├─ test_quick_check.py
│  ├─ test_reports_saving.py
│  ├─ test_safeeventqueue.py
│  ├─ test_search_a2a.py
│  ├─ test_simple_a2a.py
│  ├─ test_simple_mcp_agent.py
│  ├─ test_simple_streaming.sh
│  └─ test_streaming_curl.sh
└─ src/
   ├─ __init__.py
   ├─ code_index.md
   ├─ a2a_integration/
   │  ├─ __init__.py
   │  ├─ a2a_lg_agent_executor.py
   │  ├─ a2a_lg_client_utils.py
   │  ├─ a2a_lg_embedded_server_manager.py
   │  ├─ a2a_lg_utils.py
   │  └─ code_index.md
   ├─ config/
   │  ├─ __init__.py
   │  ├─ research_config.py
   │  └─ code_index.md
   ├─ hitl/
   │  ├─ __init__.py
   │  ├─ manager.py
   │  ├─ models.py
   │  ├─ notifications.py
   │  ├─ storage.py
   │  └─ code_index.md
   ├─ hitl_web/
   │  ├─ __init__.py
   │  ├─ api.py
   │  ├─ websocket_handler.py
   │  ├─ static/
   │  │  └─ index.html
   │  └─ code_index.md
   ├─ lg_agents/
   │  ├─ __init__.py
   │  ├─ code_index.md
   │  ├─ base/
   │  │  ├─ __init__.py
   │  │  ├─ base_graph_agent.py
   │  │  ├─ base_graph_state.py
   │  │  └─ code_index.md
   │  ├─ deep_research/
   │  │  ├─ __init__.py
   │  │  ├─ deep_research_agent.py
   │  │  ├─ deep_research_agent_hitl.py
   │  │  ├─ prompts.py
   │  │  ├─ researcher_graph.py
   │  │  ├─ supervisor_graph.py
   │  │  └─ code_index.md
   │  ├─ research_agent.py
   │  └─ simple/
   │     ├─ __init__.py
   │     └─ simple_lg_agent_with_mcp.py
   ├─ mcp_servers/
   │  ├─ __init__.py
   │  ├─ base_mcp_server.py
   │  ├─ code_index.md
   │  ├─ arxiv_search/
   │  │  ├─ __init__.py
   │  │  ├─ arxiv_client.py
   │  │  └─ server.py
   │  ├─ serper_search/
   │  │  ├─ __init__.py
   │  │  ├─ serper_dev_client.py
   │  │  └─ server.py
   │  └─ tavily_search/
   │     ├─ __init__.py
   │     ├─ tavily_search_client.py
   │     └─ server.py
   └─ utils/
      ├─ __init__.py
      ├─ env_validator.py
      ├─ error_handler.py
      ├─ http_client.py
      ├─ logging_config.py
      ├─ structured_logger.py
      └─ code_index.md
```

### File Roles (≤ 2 lines each)

- README.md: 프로젝트 개요와 실행 방법, 주요 단계 안내.
- LICENSE: 라이선스 정보.
- Makefile: 자주 쓰는 실행/정리 작업 단축 명령.
- Dockerfile: 애플리케이션 컨테이너 이미지 빌드 정의.
- docker-start.sh / .bat: 도커 기반 실행 스크립트.
- pyproject.toml: Python 패키징/의존성/도구(ruff, pytest 등) 설정.
- uv.lock: uv(또는 PDM/Poetry 유사) 잠금 파일로 정밀 의존성 고정.
- fc_lecture.png: 강의 자료 이미지.

docker/

- Dockerfile.mcp: MCP 서버 컨테이너 이미지 정의.
- docker-compose.mcp.yml: MCP 서버 세트 구동용 Compose 설정.
- mcp_docker.sh / .ps1: MCP 도커 환경 스크립트.

docs/

- a2a_spec.md: A2A 프로토콜 개요 및 스펙 요약.
- a2a-python_0.3.0.txt / a2a-samples_0.3.0.txt: A2A 0.3.0 레퍼런스/샘플.
- fastmcp-llms*_2.10.6.txt: fastmcp LLM 관련 문서 버전별 사양.
- langchain-llms.txt / langchain-mcp-adapters.txt: LangChain LLM/MCP 어댑터 정리.
- langgraph-llms*_0.6.2.txt: LangGraph LLMs 관련 문서.
- lg-deep-research-example.txt: LangGraph Deep Research 예시 참고.
- tavily_pyton_docs.md: Tavily API 사용 문서(오탈자 포함 원문 기록).
- diagrams/*: Step별 시퀀스/상태/아키텍처 다이어그램 모음.

examples/

- README.md: 예제 실행 안내 및 시나리오 설명.
- compare_systems.py: LangGraph vs A2A 비교 실행 스크립트.
- deep_research_a2a_client_comparison.py: A2A 클라이언트 비교 실험.
- step1_mcp_langgraph.py: Step1 데모( LangGraph+MCP 연동 ).
- step2_langgraph_a2a_client.py: Step2 데모( A2A 클라이언트 호출 ).
- step3_multiagent_systems.py: Step3 데모( 멀티 에이전트 ).
- step4_hitl_demo.py: Step4 데모( HITL UI + Deep Research ).

reports/

- comparison_results_*.json: 비교 실행 결과 아카이브.

scripts/

- run_step3.sh / .ps1: Step3 실행 스크립트.

steps/

- step1.md / step2.md / step3.md / step4.md: 단계별 구현 가이드.
- hitl_integration_spec.md: HITL 통합 상세 설계.

tests/

- run_tests.py: 테스트 러너 진입점.
- debug_message_test.py: 디버그 메시지/로깅 확인.
- integration_test.py: 통합 시나리오 테스트.
- test_a2a_integration.py: A2A 통합 경로 검증.
- test_artifact_streaming.sh / test_simple_streaming.sh / test_streaming_curl.sh: 스트리밍 동작 쉘 테스트.
- test_comprehensive_hitl.py / test_hitl_approval_flow.py / test_hitl_integration.py: HITL 종합/흐름/연동 테스트.
- test_e2e_final_validation.py: 종단 간 최종 검증.
- test_env_and_streaming.py: 환경 변수/스트리밍 동작 확인.
- test_integration_steps_1_to_4.py: 단계 통합 회귀 테스트.
- test_mcp_tools_validation.py: MCP 도구 유효성 검증.
- test_quick_check.py: 빠른 기본 동작 점검.
- test_reports_saving.py: 보고서 저장 동작 테스트.
- test_safeeventqueue.py: 안전 큐 처리 검증.
- test_search_a2a.py / test_simple_a2a.py / test_simple_mcp_agent.py: 검색/A2A/간단 MCP 에이전트 테스트.

src/

- __init__.py: 패키지 메타데이터(버전/저자) 정의.
- code_index.md: 소스 트리 인덱스(이 파일의 하위 전용 요약판).

src/a2a_integration/ (see module index: [src/a2a_integration/code_index.md](src/a2a_integration/code_index.md))

- __init__.py: A2A 서버/런 유틸 export.
- a2a_lg_agent_executor.py: LangGraph 그래프를 A2A AgentExecutor로 래핑(스트리밍/아티팩트 처리 포함).
- a2a_lg_client_utils.py: A2A 클라이언트 생성/스트리밍 응답 병합 유틸.
- a2a_lg_embedded_server_manager.py: 임베디드 A2A 서버 기동/헬스체크/정지 관리.
- a2a_lg_utils.py: A2A Starlette 앱 구성, AgentCard 생성, uvicorn 실행 헬퍼.
- code_index.md: 모듈 세부 인덱스(추가 참고).

src/config/ (see module index: [src/config/code_index.md](src/config/code_index.md))

- __init__.py: `ResearchConfig` export.
- research_config.py: Deep Research 공통 설정(Pydantic)과 변환/엔드포인트 헬퍼.
- code_index.md: 설정 모듈 설명 및 예시.

src/hitl/ (see module index: [src/hitl/code_index.md](src/hitl/code_index.md))

- __init__.py: 패키지 초기화.
- manager.py: 승인 생명주기/알림/자동 실행 핸들러(HITL 핵심 로직).
- models.py: 승인 타입/상태/요청/정책 Pydantic 모델.
- notifications.py: Slack/Email/WebPush 등 알림 채널 통합 서비스.
- storage.py: Redis 기반 승인 저장/인덱스/이벤트 Pub/Sub.
- code_index.md: HITL 모듈 상세 인덱스.

src/hitl_web/ (see module index: [src/hitl_web/code_index.md](src/hitl_web/code_index.md))

- __init__.py: 패키지 초기화.
- api.py: FastAPI 앱, REST/WS 엔드포인트, 대시보드 정적 파일 제공.
- websocket_handler.py: WebSocket 매니저(브로드캐스트 헬퍼).
- static/index.html: HITL 대시보드 UI.
- code_index.md: 웹 모듈 인덱스/엔드포인트 요약.

src/lg_agents/ (see module index: [src/lg_agents/code_index.md](src/lg_agents/code_index.md))

- __init__.py: 패키지 초기화.
- research_agent.py: A2A 스타일 연구 에이전트(승인 단계 포함) 구현.
- code_index.md: 에이전트 전반 인덱스.

src/lg_agents/base/ (see module index: [src/lg_agents/base/code_index.md](src/lg_agents/base/code_index.md))

- __init__.py: 패키지 초기화.
- base_graph_agent.py: LangGraph 그래프 에이전트 베이스 클래스.
- base_graph_state.py: 공통 State 스키마/리듀서 정의.
- code_index.md: 베이스 계층 인덱스.

src/lg_agents/deep_research/ (see module index: [src/lg_agents/deep_research/code_index.md](src/lg_agents/deep_research/code_index.md))

- __init__.py: 패키지 초기화.
- deep_research_agent.py: Deep Research 주 그래프(명확화/계획/연구/보고서).
- deep_research_agent_hitl.py: 최종 승인/개정 루프가 포함된 HITL 확장.
- prompts.py: 프롬프트/날짜 유틸.
- researcher_graph.py: MCP 도구 기반 Researcher 서브그래프.
- supervisor_graph.py: 연구 반복/종료 조건을 관리하는 Supervisor.
- shared.py: 공용 리듀서/도구 스키마/유틸.
- code_index.md: Deep Research 모듈 인덱스.

src/lg_agents/simple/

- __init__.py: 패키지 초기화.
- simple_lg_agent_with_mcp.py: 간단 ReAct+MCP LangGraph 에이전트 예시.

src/mcp_servers/ (see module index: [src/mcp_servers/code_index.md](src/mcp_servers/code_index.md))

- __init__.py: 패키지 초기화.
- base_mcp_server.py: 표준 응답/에러/런 헬스 포함 MCP 서버 베이스.
- code_index.md: MCP 서버 모듈 인덱스.

src/mcp_servers/arxiv_search/

- __init__.py: 패키지 초기화.
- arxiv_client.py: arXiv 검색/상세 조회 클라이언트.
- server.py: Arxiv MCP 서버 도구 등록과 라우팅.

src/mcp_servers/serper_search/

- __init__.py: 패키지 초기화.
- serper_dev_client.py: Serper API 래퍼 및 표준화 모델.
- server.py: Serper MCP 서버 도구 등록.

src/mcp_servers/tavily_search/

- __init__.py: 패키지 초기화.
- tavily_search_client.py: Tavily API 래퍼.
- server.py: Tavily MCP 서버 도구 등록.

src/utils/ (see module index: [src/utils/code_index.md](src/utils/code_index.md))

- __init__.py: 패키지 초기화.
- env_validator.py: .env 로딩/검증/리포트(선호 정책 반영).
- error_handler.py: 표준 에러/복구 전략/데코레이터.
- http_client.py: 최적화 Async HTTP 클라이언트/메트릭/재시도.
- logging_config.py: 로깅 설정/서드파티 조정/퍼포먼스 데코레이터.
- structured_logger.py: 구조화 로거/컨텍스트 로깅/메트릭.
- code_index.md: 유틸 모듈 인덱스.

### Submodule Index References

- [a2a_integration](src/a2a_integration/code_index.md)
- [config](src/config/code_index.md)
- [hitl](src/hitl/code_index.md)
- [hitl_web](src/hitl_web/code_index.md)
- [lg_agents (base)](src/lg_agents/base/code_index.md)
- [lg_agents (deep_research)](src/lg_agents/deep_research/code_index.md)
- [mcp_servers](src/mcp_servers/code_index.md)
- [utils](src/utils/code_index.md)
