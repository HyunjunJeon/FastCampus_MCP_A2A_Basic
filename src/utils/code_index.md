## Code Index - utils

공통 유틸리티와 로깅/HTTP/환경변수 검증 모듈.

### Files

- __init__.py: 패키지 초기화.
- env_validator.py: .env 로드/검증/보고 및 선택/필수 변수 관리.
- error_handler.py: 표준 에러/응답 모델과 복구 전략, 데코레이터.
- http_client.py: 최적화 Async HTTP 클라이언트(풀/재시도/메트릭)와 API 베이스.
- logging_config.py: 루트/서드파티 로깅 설정, 편의 로거 유틸.
- structured_logger.py: 구조화 로거/컨텍스트 로깅/성능 데코레이터/통계.

### Related

- 상위: [../code_index.md](../code_index.md)
- 전체: [../../code_index.md](../../code_index.md)
