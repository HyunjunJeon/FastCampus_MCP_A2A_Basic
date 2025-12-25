# Code Index - a2a_integration

LangGraph 그래프를 A2A 프로토콜 서버/클라이언트로 감싸고 실행/헬스/스트리밍을 지원하는 통합 모듈.

**A2A SDK 버전**: 0.3.22+ (최신 버전 사용 중)

## 주요 특징

- **다중 전송 프로토콜 지원**: JSON-RPC, HTTP+JSON, gRPC (0.3.11+)
- **스트리밍 응답**: Server-Sent Events (SSE) 기반 실시간 업데이트
- **HITL 지원**: Human-In-The-Loop (input-required 상태) 통합
- **영속 스토어**: Redis 기반 TaskStore 옵션
- **보안 강화**: Push Notification egress allowlist, HMAC 서명

## Files

- **__init__.py**: `to_a2a_starlette_server`, `to_a2a_run_uvicorn`, `create_agent_card` export.
  
- **a2a_lg_agent_executor.py** (951줄): LangGraph `CompiledStateGraph`를 A2A `AgentExecutor`로 래핑
  - 스트리밍 텍스트 추출 및 증분 병합
  - 대용량 아티팩트 청크 전송 (8KB 단위)
  - 취소 전파 및 HITL 인터럽트 처리
  - 하트비트 및 진행 상태 이벤트

- **a2a_lg_client_utils.py** (676줄): A2A 클라이언트 유틸리티
  - gRPC, JSON-RPC, HTTP+JSON 전송 프로토콜 지원
  - `send_query`(텍스트), `send_data`(JSON DataPart) 메서드
  - 스트리밍 이벤트 텍스트 병합 및 중복 제거
  - `send_data_merged`: DataPart 자동 병합 (smart/last/append 모드)

- **a2a_lg_embedded_server_manager.py** (165줄): 임베디드 A2A 서버 매니저
  - 자동 포트 확보 및 서버 기동
  - 헬스체크 엔드포인트 (/health)
  - 비동기 컨텍스트 매니저 패턴
  - 서버 생명주기 관리 (시작/대기/종료)

- **a2a_lg_utils.py** (331줄): A2A 서버 빌드 헬퍼
  - `create_agent_card`: AgentCard 생성 (스킬, 전송 프로토콜, 능력 설정)
  - `_build_request_handler`: DefaultRequestHandler 구성
  - Push Notification egress allowlist 및 HMAC 서명
  - Redis TaskStore 자동 전환 (A2A_TASK_STORE=redis)
  - `to_a2a_starlette_server`: Starlette 앱 빌더
  - `to_a2a_run_uvicorn`: uvicorn 실행 헬퍼

- **redis_task_store.py** (110줄): Redis 기반 TaskStore 구현
  - A2A TaskStore 인터페이스 영속화
  - TTL 설정 지원 (A2A_TASK_TTL_SECONDS)
  - 분산 환경 Task 상태 공유
  - 환경변수: A2A_TASK_STORE=redis, A2A_TASK_REDIS_URL

## 환경변수

### 스트리밍 최적화
- `A2A_STREAM_EMIT_INTERVAL_MS`: 스트리밍 청크 전송 최소 간격 (기본: 100ms)
- `A2A_STREAM_MIN_CHARS`: 스트리밍 청크 최소 문자 수 (기본: 24)
- `A2A_STREAM_MAX_LATENCY_MS`: 스트리밍 최대 지연 상한 (기본: 300ms)
- `A2A_HEARTBEAT_INTERVAL_S`: 하트비트 전송 주기 (기본: 5초, 0이면 비활성화)

### 보안 설정
- `A2A_PUSH_WEBHOOK_ALLOWLIST`: Push 웹훅 허용 호스트 (기본: "localhost,127.0.0.1")
- `A2A_PUSH_DEFAULT_TOKEN`: Push Notification 기본 토큰
- `A2A_PUSH_HMAC_SECRET`: HMAC 서명 비밀키

### TaskStore 설정
- `A2A_TASK_STORE`: TaskStore 백엔드 ("memory" | "redis", 기본: "memory")
- `A2A_TASK_REDIS_URL`: Redis 연결 URL (기본: "redis://localhost:6379/0")
- `A2A_TASK_TTL_SECONDS`: Task TTL (초, 0이면 무제한)

## 버전 히스토리

### 0.3.22 (2025-12-25)
- ✅ 하위 호환성 완전 유지
- 🆕 gRPC 전송 프로토콜 지원 강화
- 🆕 클라이언트 유틸리티 기능 확장
- 🆕 서버 빌드 헬퍼 기능 대폭 확장
- 🆕 Redis TaskStore 기능 강화
- 📚 성능 최적화 및 안정성 개선

### 0.3.11 (2025-11-11)
- ✅ 하위 호환성 완전 유지
- 🆕 gRPC 전송 프로토콜 지원 추가
- 🆕 DefaultRequestHandler에 queue_manager, request_context_builder 파라미터 추가 (선택적)
- 🆕 A2AStarletteApplication에 extended_agent_card, card_modifier 등 파라미터 추가 (선택적)
- 🆕 ClientConfig에 polling, grpc_channel_factory, use_client_preference 등 추가 (선택적)
- 📚 문서 및 주석 개선

### Related

- 상위 인덱스: ../../code_index.md
- A2A 사양: ../../docs/a2a_spec.md
- 검증 결과: ../../A2A_SDK_0.3.11_검증결과.md

