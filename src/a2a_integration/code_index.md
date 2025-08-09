## Code Index - a2a_integration

LangGraph 그래프를 A2A 프로토콜 서버/클라이언트로 감싸고 실행/헬스/스트리밍을 지원하는 통합 모듈.

### Files

- __init__.py: `to_a2a_starlette_server`, `to_a2a_run_uvicorn`, `create_agent_card` export.
- a2a_lg_agent_executor.py: LangGraph `CompiledStateGraph`를 A2A `AgentExecutor`로 래핑(스트리밍 텍스트 추출/아티팩트 전송/취소 처리).
- a2a_lg_client_utils.py: A2A 클라이언트 생성/카드 해석/스트리밍 이벤트 텍스트 병합 유틸.
- a2a_lg_embedded_server_manager.py: 임베디드 A2A 서버 기동(헬스체크 라우트 추가)/포트 확보/정지 관리.
- a2a_lg_utils.py: `AgentCard` 생성, 요청 핸들러/인메모리 스토어 구성, Starlette 앱 빌더 및 uvicorn 실행 헬퍼.

### Related

- 상위 인덱스: ../../code_index.md

