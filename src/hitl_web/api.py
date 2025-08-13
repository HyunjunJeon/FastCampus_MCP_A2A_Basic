"""
HITL 웹 인터페이스 FastAPI 서버
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging
from pathlib import Path
from datetime import timezone

from hitl.manager import hitl_manager
from src.utils.http_client import http_client, cleanup_http_clients
from hitl_web.websocket_handler import websocket_manager
from hitl.models import ApprovalRequest, ApprovalStatus, ApprovalType
from hitl.webhook_storage import webhook_storage

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시 초기화
    await hitl_manager.initialize()

    # WebSocket 브로드캐스트를 위한 핸들러 등록
    async def broadcast_approval_update(request: ApprovalRequest):
        from datetime import datetime
        req_dict = request.model_dump()
        # datetime 필드를 문자열로 변환
        if req_dict.get('created_at'):
            req_dict['created_at'] = req_dict['created_at'].isoformat() if isinstance(req_dict['created_at'], datetime) else req_dict['created_at']
        if req_dict.get('expires_at'):
            req_dict['expires_at'] = req_dict['expires_at'].isoformat() if isinstance(req_dict['expires_at'], datetime) else req_dict['expires_at']
        if req_dict.get('decided_at'):
            req_dict['decided_at'] = req_dict['decided_at'].isoformat() if isinstance(req_dict['decided_at'], datetime) else req_dict['decided_at']
        
        await websocket_manager.broadcast(
            {"type": "approval_update", "data": req_dict}
        )

    # WebSocket 연결 관리자를 HITL Manager에 설정 (단일 매니저로 통합)
    hitl_manager.set_connection_manager(websocket_manager)
    
    # 승인 상태 변경 시 WebSocket 브로드캐스트 핸들러 등록
    for status in ApprovalStatus:
        hitl_manager.register_handler(status, broadcast_approval_update)
    
    # 승인 완료 시 Deep Research 자동 실행 핸들러 등록 (중복 승인 방지: 환경변수로 on/off)
    import os as _os
    if (_os.getenv("ENABLE_HITL", "0").strip().lower() in {"1","true","yes","y"}):
        hitl_manager.register_handler(ApprovalStatus.APPROVED, hitl_manager.execute_deep_research_handler)
    
    logger.info("HITL Web API 시작 - Deep Research 자동 실행 핸들러 등록됨")
    
    yield  # 애플리케이션 실행
    
    # 종료 시 정리
    await hitl_manager.shutdown()
    # 공용 HTTP 클라이언트 풀 정리
    try:
        await cleanup_http_clients()
    except Exception:
        pass
    logger.info("HITL Web API 종료")


# FastAPI 앱
app = FastAPI(title="HITL Approval System", lifespan=lifespan)

# CORS 설정 (환경변수 기반 화이트리스트)
import os

def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "y"}

_origins_env = os.getenv("HITL_CORS_ALLOW_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_allow_credentials = _truthy(os.getenv("HITL_CORS_ALLOW_CREDENTIALS", "false"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 정적 파일 서빙 - 절대 경로 사용
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def hitl_dashboard():
    """HITL 대시보드 홈"""
    from fastapi.responses import FileResponse

    # 절대 경로로 index.html 파일 제공
    index_path = Path(__file__).parent / "static" / "index.html"
    return FileResponse(str(index_path))


@app.get("/hitl")
async def hitl_dashboard_alias():
    """/hitl 경로로도 대시보드를 제공"""
    from fastapi.responses import FileResponse

    index_path = Path(__file__).parent / "static" / "index.html"
    return FileResponse(str(index_path))


@app.get("/api/a2a/status")
async def get_a2a_status():
    """A2A(8090) 상태 점검: 에이전트 카드/헬스체크를 프록시로 확인"""
    from datetime import datetime

    base_url = "http://localhost:8090"
    agent = None
    healthy = False
    errors: list[str] = []
    try:
        # Agent Card 확인
        try:
            resp = await http_client.get(f"{base_url}/.well-known/agent-card.json", timeout=1.5)
            if resp.status_code == 200:
                data = resp.json()
                agent = {
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "version": data.get("version"),
                    "url": data.get("url") or base_url,
                }
        except Exception as e:
            errors.append(f"card:{type(e).__name__}")

        # Health 확인
        try:
            resp_h = await http_client.get(f"{base_url}/health", timeout=1.0)
            healthy = resp_h.status_code == 200
        except Exception as e:
            errors.append(f"health:{type(e).__name__}")
    except Exception as e:
        errors.append(f"root:{type(e).__name__}")

    return {
        "reachable": bool(agent) or healthy,
        "healthy": healthy,
        "agent": agent,
        "base_url": base_url,
        "checked_at": datetime.now().isoformat() + "Z",
        "errors": errors or None,
    }


# 요청/응답 모델
class ApprovalDecision(BaseModel):
    request_id: str
    decision: str
    decided_by: str
    reason: Optional[str] = None


class ApprovalFilter(BaseModel):
    agent_id: Optional[str] = None
    approval_type: Optional[str] = None
    limit: int = 50


# 로컬 ConnectionManager 제거: 전역 websocket_manager를 단일 소스로 사용


@app.get("/health")
async def health_check():
    """헬스체크"""
    return {"status": "healthy"}


@app.get("/api/approvals/pending", response_model=List[ApprovalRequest])
async def get_pending_approvals(
    agent_id: Optional[str] = None, approval_type: Optional[str] = None, limit: int = 50
):
    """대기 중인 승인 요청 목록"""
    try:
        # 타입 변환
        type_enum = None
        if approval_type:
            type_enum = ApprovalType(approval_type)

        approvals = await hitl_manager.get_pending_approvals(
            agent_id=agent_id, approval_type=type_enum, limit=limit
        )

        return approvals

    except Exception as e:
        logger.error(f"승인 목록 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/approvals/approved", response_model=List[ApprovalRequest])
async def get_approved_approvals(
    agent_id: Optional[str] = None, approval_type: Optional[str] = None, limit: int = 50
):
    """승인된 승인 요청 목록"""
    try:
        # 타입 변환
        type_enum = None
        if approval_type:
            type_enum = ApprovalType(approval_type)

        approvals = await hitl_manager.get_approved_approvals(
            agent_id=agent_id, approval_type=type_enum, limit=limit
        )

        return approvals

    except Exception as e:
        logger.error(f"승인된 목록 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/approvals/rejected", response_model=List[ApprovalRequest])
async def get_rejected_approvals(
    agent_id: Optional[str] = None, approval_type: Optional[str] = None, limit: int = 50
):
    """거부된 승인 요청 목록"""
    try:
        # 타입 변환
        type_enum = None
        if approval_type:
            type_enum = ApprovalType(approval_type)

        approvals = await hitl_manager.get_rejected_approvals(
            agent_id=agent_id, approval_type=type_enum, limit=limit
        )

        return approvals

    except Exception as e:
        logger.error(f"거부된 목록 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/approvals/{request_id}", response_model=ApprovalRequest)
async def get_approval_request(request_id: str):
    """특정 승인 요청 조회"""
    from hitl.storage import approval_storage

    request = await approval_storage.get_approval_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")

    return request


@app.get("/api/approvals/{request_id}/final-report")
async def get_approval_final_report(request_id: str):
    """승인 요청에 포함된 최종 보고서 텍스트 반환 (컨텍스트의 final_report 필드)"""
    from hitl.storage import approval_storage
    request = await approval_storage.get_approval_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")
    context = getattr(request, "context", None) or {}
    report = context.get("final_report")
    if not report:
        raise HTTPException(status_code=404, detail="최종 보고서가 컨텍스트에 없습니다")
    return {"request_id": request_id, "final_report": report}


@app.get("/api/approvals/{request_id}/final-report/download")
async def download_approval_final_report(request_id: str, format: str = "md"):
    """최종 보고서를 파일로 다운로드

    - format: md | txt | json (기본 md)
    """
    from hitl.storage import approval_storage
    import json as json_lib
    from datetime import datetime

    request = await approval_storage.get_approval_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="승인 요청을 찾을 수 없습니다")

    context = getattr(request, "context", None) or {}
    report = context.get("final_report")
    if not report:
        raise HTTPException(status_code=404, detail="최종 보고서가 컨텍스트에 없습니다")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if format == "json":
        payload = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "title": request.title,
            "final_report": report,
            "decided_by": request.decided_by,
            "decision": request.decision,
            "status": request.status.value,
            "created_at": getattr(request, "created_at", None),
            "decided_at": getattr(request, "decided_at", None),
        }
        content = json_lib.dumps(payload, ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"final_report_{request_id}_{ts}.json"
    else:
        # md/txt는 동일 컨텐츠, 확장자만 다르게
        header = f"# 최종 보고서\n\n요청 ID: {request.request_id}\n제목: {request.title}\n상태: {request.status.value}\n\n---\n\n"
        content = header + str(report)
        if format == "txt":
            media_type = "text/plain; charset=utf-8"
            filename = f"final_report_{request_id}_{ts}.txt"
        else:
            media_type = "text/markdown; charset=utf-8"
            filename = f"final_report_{request_id}_{ts}.md"

    headers = {"Content-Disposition": f"attachment; filename=\"{filename}\""}
    return Response(content=content, media_type=media_type, headers=headers)


@app.post("/api/approvals/{request_id}/approve")
async def approve_request(request_id: str, decision: ApprovalDecision):
    """승인 처리"""
    if decision.request_id != request_id:
        raise HTTPException(status_code=400, detail="요청 ID 불일치")

    success = await hitl_manager.approve(
        request_id=request_id,
        decided_by=decision.decided_by,
        decision=decision.decision,
        reason=decision.reason,
    )

    if not success:
        raise HTTPException(status_code=400, detail="승인 처리 실패")

    return {"success": True, "message": "승인 완료"}


@app.post("/api/approvals/{request_id}/reject")
async def reject_request(request_id: str, decision: ApprovalDecision):
    """거부 처리"""
    if decision.request_id != request_id:
        raise HTTPException(status_code=400, detail="요청 ID 불일치")

    if not decision.reason:
        raise HTTPException(status_code=400, detail="거부 사유를 입력해야 합니다")

    success = await hitl_manager.reject(
        request_id=request_id, decided_by=decision.decided_by, reason=decision.reason
    )

    if not success:
        raise HTTPException(status_code=400, detail="거부 처리 실패")

    return {"success": True, "message": "거부 완료"}


# A2A Push Notification Webhook Receiver (Token/HMAC 검증)
@app.post("/api/webhook/a2a")
async def a2a_webhook_receiver(request: Request):
    """A2A 서버가 보내는 푸시 알림(Webhook) 수신 엔드포인트.

    보안: 환경변수 기반 토큰/HMAC 서명 검증을 수행한다.
    - A2A_WEBHOOK_EXPECTED_TOKEN: X-A2A-Notification-Token 검증
    - A2A_WEBHOOK_HMAC_SECRET: X-A2A-Timestamp + body 에 대한 sha256 HMAC 검증
    - A2A_WEBHOOK_TOLERANCE_SECONDS: 타임스탬프 허용 오차(기본 300초)
    """
    import os
    import hmac
    import hashlib
    import time

    body = await request.body()
    headers = request.headers

    expected_token = os.getenv("A2A_WEBHOOK_EXPECTED_TOKEN")
    hmac_secret = os.getenv("A2A_WEBHOOK_HMAC_SECRET")
    tolerance_s = int(os.getenv("A2A_WEBHOOK_TOLERANCE_SECONDS", "300") or "300")

    # 1) Token 검증(옵션)
    if expected_token:
        token = headers.get("X-A2A-Notification-Token")
        if not token or not hmac.compare_digest(token, expected_token):
            raise HTTPException(status_code=401, detail="Invalid notification token")

    # 2) HMAC 검증(옵션)
    if hmac_secret:
        ts = headers.get("X-A2A-Timestamp")
        sig = headers.get("X-A2A-Signature")
        if not ts or not sig:
            raise HTTPException(status_code=401, detail="Missing signature headers")
        try:
            ts_int = int(ts)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid timestamp")
        if abs(int(time.time()) - ts_int) > tolerance_s:
            raise HTTPException(status_code=401, detail="Stale timestamp")
        mac = hmac.new(hmac_secret.encode(), body + ts.encode(), hashlib.sha256).hexdigest()
        expected_sig = f"sha256={mac}"
        if not hmac.compare_digest(sig, expected_sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # 유효한 알림으로 간주. 필요 시 내부 큐에 넣거나 브로드캐스트
    try:
        payload = await request.json()
    except Exception:
        payload = None

    logger.info("A2A Webhook received")
    if payload:
        # 간단 브로드캐스트 (선택)
        try:
            await websocket_manager.broadcast({"type": "a2a_webhook", "data": payload})
        except Exception:
            pass
        # 내부 큐/저장에 보관: task_id가 있으면 Task별 이벤트로 축적
        try:
            task_id = None
            if isinstance(payload, dict):
                # 일반적으로 result/task/status_update 등 구조 내부에 task_id가 존재
                for key in ("task_id", "taskId"):
                    if key in payload:
                        task_id = payload.get(key)
                        break
                if not task_id:
                    # 흔한 래핑: { "result": { "task": {..., "id": ...} } }
                    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
                    if result:
                        t = result.get("task") if isinstance(result.get("task"), dict) else None
                        if t and isinstance(t.get("id"), str):
                            task_id = t.get("id")
            if task_id:
                await webhook_storage.add_event(task_id, payload)
        except Exception:
            pass
    return {"ok": True}


@app.get("/api/webhook/a2a/events/{task_id}")
async def get_webhook_events(task_id: str, limit: int = 100):
    """수신된 A2A webhook 이벤트를 Task 기준으로 조회"""
    try:
        events = await webhook_storage.get_events(task_id, limit=limit)
        return {"task_id": task_id, "events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Request 모델들
class ResearchStartRequest(BaseModel):
    request_id: Optional[str] = None
    topic: Optional[str] = None

class ResearchProgressRequest(BaseModel):
    stage: int = 1
    progress: int = 33
    stage_name: Optional[str] = None
    current_action: Optional[str] = None

class ResearchCompleteRequest(BaseModel):
    success: bool = True
    summary: Optional[str] = None

# Deep Research 실제 시작 엔드포인트
@app.post("/api/research/start")
async def start_deep_research(request: ResearchStartRequest):
    """사용자가 직접 Deep Research를 시작"""
    import uuid
    import asyncio
    
    # 입력 검증
    if not request.topic or not request.topic.strip():
        return {"success": False, "error": "연구 주제를 입력해주세요."}
    
    topic = request.topic.strip()
    if len(topic) < 5:
        return {"success": False, "error": "연구 주제는 최소 5글자 이상이어야 합니다."}
    
    try:
        # 현재 진행 중인 연구가 있는지 확인 (중복 실행 방지)
        # TODO: 이 부분은 나중에 상태 관리 로직으로 개선 필요
        
        # ApprovalRequest 모의 객체 생성 (HITLManager와 일관된 인터페이스)
        mock_request = type('MockRequest', (), {
            'request_id': request.request_id or str(uuid.uuid4()),
            'task_id': f"user_research_{str(uuid.uuid4())[:8]}",
            'title': f"사용자 요청 연구: {topic}",
            'description': f"사용자가 직접 요청한 DeepResearch: {topic}",
            'agent_id': "user_direct_research_agent",
            'approval_type': "RESEARCH_REQUEST",
            'context': {"user_topic": topic, "direct_request": True}
        })()
        
        # HITLManager의 연구 실행 로직 호출
        from src.hitl.manager import hitl_manager
        
        # WebSocket 연결 관리자 설정 확인
        connection_manager = getattr(hitl_manager, '_connection_manager', websocket_manager)
        hitl_manager.set_connection_manager(connection_manager)
        
        # Deep Research 실행을 백그라운드 태스크로 수행
        asyncio.create_task(hitl_manager.execute_deep_research_handler(mock_request))

        return {
            "success": True,
            "message": "DeepResearch가 시작되었습니다! 진행상황을 확인해보세요.",
            "request_id": mock_request.request_id,
            "task_id": mock_request.task_id,
        }
        
    except Exception as e:
        logger.error(f"Deep Research 시작 중 오류: {e}")
        return {"success": False, "error": f"연구 시작 중 오류가 발생했습니다: {str(e)}"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 연결 - 단일 매니저 사용"""
    await websocket_manager.connect(websocket)
    try:
        # 초기 데이터 전송
        approvals = await hitl_manager.get_pending_approvals(limit=50)
        from datetime import datetime
        data = []
        for req in approvals:
            req_dict = req.model_dump()
            if req_dict.get('created_at'):
                req_dict['created_at'] = req_dict['created_at'].isoformat() if isinstance(req_dict['created_at'], datetime) else req_dict['created_at']
            if req_dict.get('expires_at'):
                req_dict['expires_at'] = req_dict['expires_at'].isoformat() if isinstance(req_dict['expires_at'], datetime) else req_dict['expires_at']
            if req_dict.get('decided_at'):
                req_dict['decided_at'] = req_dict['decided_at'].isoformat() if isinstance(req_dict['decided_at'], datetime) else req_dict['decided_at']
            data.append(req_dict)
        await websocket.send_json({"type": "initial_data", "data": data})

        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
        websocket_manager.disconnect(websocket)
