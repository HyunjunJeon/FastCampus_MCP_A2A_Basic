## Code Index - hitl_web

HITL 시스템의 웹 인터페이스(FastAPI). REST와 WebSocket으로 승인 요청과 연구 진행상황을 제공.

### Files

- __init__.py: 패키지 초기화.
- api.py: FastAPI 앱과 REST/WS 엔드포인트, 정적 파일 제공 및 브로드캐스트 헬퍼.
- websocket_handler.py: WebSocket 매니저(접속/해제/브로드캐스트 유틸).
- static/index.html: 대시보드 UI(승인/거부, 진행상황 표시).

### API (요약)

- GET /health — 헬스체크
- WS /ws — 실시간 알림
- GET /api/approvals/(pending|approved|rejected)
- GET /api/approvals/{id}
- POST /api/approvals/{id}/approve|reject
- POST /api/research/start (테스트/직접 시작)

### Related

- 상위: [../code_index.md](../code_index.md)
- 전체: [../../code_index.md](../../code_index.md)
