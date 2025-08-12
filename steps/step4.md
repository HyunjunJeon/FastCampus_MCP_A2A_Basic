# Step 4 — A2A 통신 과정에서 HITL(Human-In-The-Loop)로 사람 판단을 요청하기

이 단계는 Step 3까지 구현한 DeepResearch 결과물 위에 “사람 승인/피드백 루프”를 얹습니다. 최종 보고서를 사람에게 보여주고, **사용해도 되는지** 묻고, **거절(reason)** 을 받으면 그 이유를 반영해 **다시 보고서 작성(개정 루프)** 하는 흐름을 완성합니다. README의 대주제(“MCP → A2A → 멀티에이전트 → HITL”)를 유지하세요.

## 목표

- HITL 승인 지점: (1) 연구 계획 승인 → (2) 중요 데이터 검증 → (3) 최종 보고서 승인
- 웹 대시보드(WS)로 승인 요청/상태를 실시간 확인하고, 승인/거절/사유 입력 지원
- 거절 사유를 수집하여 보고서 개정 루프를 수행(설정값: `max_revision_loops`)

## 산출물(이 단계 완료 시)

- HITL Web/API: `src/hitl_web/api.py` (WS/REST, 정적 UI)
- HITL Core: `src/hitl/manager.py`, `src/hitl/storage.py`, `src/hitl/models.py`, `src/hitl/notifications.py`
- 데모 실행: `examples/step4_hitl_demo.py`

## 구축 순서(요약)

### 1) HITL Core 구성

- 승인 모델(`ApprovalRequest`, `ApprovalStatus`, `ApprovalType`)과 정책(`HITLPolicy`) 정의
- Redis 기반 저장소(`ApprovalStorage`)로 생성/조회/상태 업데이트 + Pub/Sub 이벤트
- `HITLManager`로 승인 요청 생성 → 대기 → 승인/거절 처리, 이벤트 브로드캐스트, 자동 승인/타임아웃 처리
- 설정: `src/config/research_config.py`에 `max_revision_loops`(기본 2)

### 2) Web/API + WebSocket 대시보드

- FastAPI: `/api/approvals/*`, `/api/research/*`, `/health` 제공
- WebSocket `/ws`: 대기/승인/거절 업데이트 브로드캐스트, 연구 시작/진행/완료 이벤트 표시
- 정적 UI(`src/hitl_web/static/index.html`): 승인 카드/탭/진행 표시/버튼(승인/거절)

### 3) DeepResearch + HITL 통합

- 승인 포인트 예시:
  1. 연구 계획 승인: Planner 산출물을 요약해 요청
  2. 중요 데이터 검증: Researcher 주요 근거/수치 검증 요청
  3. 최종 보고서 승인: Writer/Evaluator 결과 전달 후 승인 요청
- 거절 시: `decision_reason`을 수집 → `max_revision_loops` 범위 내에서 보고서 개정 루프 수행

### 4) 데모 실행

- `python examples/step4_hitl_demo.py`
- 대시보드: <http://localhost:8000> (WS: `ws://localhost:8000/ws`)
- A2A 임베디드 서버 포트: 8090(Deep/HITL), 8091(Researcher), 8092(Supervisor)

## 검증 기준

- 승인 요청이 UI에 카드로 표시되고 승인/거절/사유 입력이 반영됨
- 거절 시 개정 루프가 동작(최대 반복 수 준수), 승인 시 최종 보고서 확정
- API/WS Health 체크 200, Agent Card JSON 서빙 정상

## 다이어그램(필수 참고)

- 시퀀스: [docs/diagrams/step4_sequence.md](../docs/diagrams/step4_sequence.md)
- 상태 전이: [docs/diagrams/step4_state.md](../docs/diagrams/step4_state.md)
- 아키텍처: [docs/diagrams/step4_architecture.md](../docs/diagrams/step4_architecture.md)

## HITL 통합 상세(요약)

아래는 `steps/hitl_integration_spec.md`의 핵심을 현재 구현 코드 기준으로 압축한 내용입니다.

- 아키텍처/포트
  - HITL Web/API: 8000 (`src/hitl_web/api.py`, 정적 UI + REST + WebSocket)
  - A2A Agents: 8090(Deep/HITL), 8091(Researcher), 8092(Supervisor)
  - Redis: 6379 (승인 요청 저장/이벤트 Pub/Sub)

- 핵심 컴포넌트(코드 기준)
  - `src/hitl/manager.py`: `HITLManager` — 승인 생성/대기/상태 전환, 진행 브로드캐스트
  - `src/hitl/storage.py`: `ApprovalStorage` — Redis 저장/조회/인덱스/이벤트
  - `src/hitl/models.py`: `ApprovalType`, `ApprovalStatus`, `ApprovalRequest`, `HITLPolicy`
  - `src/hitl/notifications.py`: Slack/Email/WebPush 알림 채널(옵션)
  - `src/hitl_web/api.py`: FastAPI 라우트, `/ws` 브로드캐스트, 대시보드 서빙

- 데이터 모델(요약)
  - `ApprovalType`: `critical_decision`, `data_validation`, `final_report`, `budget_approval`, `safety_check`
  - `ApprovalStatus`: `pending`, `approved`, `rejected`, `timeout`, `auto_approved`
  - `ApprovalRequest` 주요 필드: `request_id`, `agent_id`, `approval_type`, `title`, `description`, `context(final_report 등)`, `status`, `priority`, `created_at/decided_at`

- API 개요(실구현)
  - 헬스/상태: `GET /health`, `GET /api/a2a/status`
  - 승인 목록: `GET /api/approvals/pending|approved|rejected?agent_id=&approval_type=&limit=`
  - 승인 단건: `GET /api/approvals/{request_id}`
  - 보고서 보기/다운로드: `GET /api/approvals/{request_id}/final-report`, `GET /api/approvals/{request_id}/final-report/download?format=md|txt|json`
  - 승인/거부: `POST /api/approvals/{request_id}/approve|reject` (body: `{request_id, decision, decided_by, reason?}`)
  - 연구 시작: `POST /api/research/start` (body: `{topic}`)
  - WebSocket: `GET /ws` (메시지 타입: `initial_data`, `approval_update`, `research_started`, `research_progress`, `research_completed`)

- 운영 모드
  - 기본: 외부 HITL(UI) — `HITLManager` 승인 요청/대기 사용
  - 인터럽트 모드: `HITL_MODE=interrupt` 설정 시 LangGraph `interrupt`를 통해 입력 요구(`input-required`) 후 재개

- 개정(Revision) 루프
  - 거절 시 피드백(`decision_reason`)을 수집 → `ResearchConfig.max_revision_loops`(기본 2) 내에서 보고서 개선 반복

자세한 설계/예제/베스트프랙티스는 [hitl_integration_spec.md](hitl_integration_spec.md)를 참고하세요.

## 트러블슈팅

- **Redis 미가동**: `docker compose -f docker/docker-compose.mcp.yml up -d redis`
- **WS 업데이트 미수신**: 브라우저 콘솔/서버 로그 확인, `/ws` 연결 상태 점검
- **개정 루프 미작동**: `max_revision_loops` 설정/거절 사유 전달 경로 확인

## 참고 문서(필독)

- HITL 사양(프로젝트 내부): `steps/hitl_integration_spec.md`
- A2A SDK: `docs/a2a-python_0.3.0.txt`
- WebSocket/REST: FastAPI/Starlette 공식 문서
