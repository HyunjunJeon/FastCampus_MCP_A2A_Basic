## Code Index - hitl

사용자 승인과 피드백(HITL) 관리 핵심 모듈. 승인 요청 생성/저장/알림/자동 처리와 연구 실행 트리거 제공.

### Files

- __init__.py: 패키지 초기화.
- manager.py: `HITLManager` 및 `hitl_manager` 싱글톤. 승인 생명주기/타임아웃/웹소켓 브로드캐스트/Deep Research 자동 실행 핸들러.
- models.py: `ApprovalType/Status`, `ApprovalRequest`, `HITLContext`, `HITLPolicy` 데이터 모델.
- notifications.py: Slack/Email/WebPush 알림 채널과 통합 알림 서비스.
- storage.py: Redis 기반 승인 저장소, 인덱스, Pub/Sub 이벤트, 만료 처리.

### Related

- 웹 UI/API: [../hitl_web/code_index.md](../hitl_web/code_index.md)
- 상위: [../code_index.md](../code_index.md), [../../code_index.md](../../code_index.md)
