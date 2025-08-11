"""
HITL 웹 인터페이스 FastAPI 서버
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging
from pathlib import Path
from datetime import timezone

from hitl.manager import hitl_manager
from hitl.models import ApprovalRequest, ApprovalStatus, ApprovalType

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
        
        await manager.broadcast(
            {"type": "approval_update", "data": req_dict}
        )

    # WebSocket 연결 관리자를 HITL Manager에 설정
    hitl_manager.set_connection_manager(manager)
    
    # 승인 상태 변경 시 WebSocket 브로드캐스트 핸들러 등록
    for status in ApprovalStatus:
        hitl_manager.register_handler(status, broadcast_approval_update)
    
    # 승인 완료 시 Deep Research 자동 실행 핸들러 등록
    hitl_manager.register_handler(ApprovalStatus.APPROVED, hitl_manager.execute_deep_research_handler)
    
    logger.info("HITL Web API 시작 - Deep Research 자동 실행 핸들러 등록됨")
    
    yield  # 애플리케이션 실행
    
    # 종료 시 정리
    await hitl_manager.shutdown()
    logger.info("HITL Web API 종료")


# FastAPI 앱
app = FastAPI(title="HITL Approval System", lifespan=lifespan)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    import aiohttp

    base_url = "http://localhost:8090"
    agent = None
    healthy = False
    try:
        timeout = aiohttp.ClientTimeout(total=1.5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Agent Card 확인
            try:
                async with session.get(f"{base_url}/.well-known/agent-card.json") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        agent = {
                            "name": data.get("name"),
                            "description": data.get("description"),
                            "version": data.get("version"),
                            "url": data.get("url") or base_url,
                        }
            except Exception:
                pass

            # Health 확인
            try:
                async with session.get(f"{base_url}/health") as resp:
                    healthy = resp.status == 200
            except Exception:
                pass
    except Exception:
        pass

    return {
        "reachable": bool(agent) or healthy,
        "healthy": healthy,
        "agent": agent,
        "base_url": base_url,
        "checked_at": datetime.now().isoformat() + "Z",
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


# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 연결: {len(self.active_connections)}개 활성")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket 연결 해제: {len(self.active_connections)}개 활성")

    async def broadcast(self, message: dict):
        """모든 연결에 메시지 브로드캐스트"""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # 끊어진 연결 제거
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_research_progress(self, progress_data: dict):
        """Deep Research 진행상황 브로드캐스트"""
        from datetime import datetime
        
        # datetime 필드 처리
        if progress_data.get('timestamp'):
            if isinstance(progress_data['timestamp'], datetime):
                progress_data['timestamp'] = progress_data['timestamp'].isoformat()
        
        await self.broadcast({
            "type": "research_progress",
            "data": {
                "request_id": progress_data.get("request_id"),
                "task_id": progress_data.get("task_id"),
                "stage": progress_data.get("stage"),
                "stage_name": progress_data.get("stage_name"),
                "progress": progress_data.get("progress", 0),
                "total_stages": progress_data.get("total_stages", 3),
                "estimated_time": progress_data.get("estimated_time"),
                "current_action": progress_data.get("current_action"),
                "timestamp": progress_data.get("timestamp")
            }
        })

    async def broadcast_research_completed(self, completion_data: dict):
        """Deep Research 완료 브로드캐스트"""
        from datetime import datetime
        
        # datetime 필드 처리
        for date_field in ['started_at', 'completed_at']:
            if completion_data.get(date_field):
                if isinstance(completion_data[date_field], datetime):
                    completion_data[date_field] = completion_data[date_field].isoformat()
        
        await self.broadcast({
            "type": "research_completed",
            "data": {
                "request_id": completion_data.get("request_id"),
                "task_id": completion_data.get("task_id"),
                "success": completion_data.get("success", True),
                "total_duration": completion_data.get("total_duration"),
                "started_at": completion_data.get("started_at"),
                "completed_at": completion_data.get("completed_at"),
                "final_status": completion_data.get("final_status"),
                "summary": completion_data.get("summary")
            }
        })

    async def broadcast_research_started(self, start_data: dict):
        """Deep Research 시작 브로드캐스트"""
        from datetime import datetime
        
        if start_data.get('started_at'):
            if isinstance(start_data['started_at'], datetime):
                start_data['started_at'] = start_data['started_at'].isoformat()
        
        await self.broadcast({
            "type": "research_started", 
            "data": {
                "request_id": start_data.get("request_id"),
                "task_id": start_data.get("task_id"),
                "topic": start_data.get("topic"),
                "agent_id": start_data.get("agent_id"),
                "started_at": start_data.get("started_at"),
                "expected_duration": start_data.get("expected_duration", "알 수 없음"),
                "stages": start_data.get("stages", ["계획 승인", "데이터 검증", "최종 승인"]),
                "status": "진행 중"
            }
        })


manager = ConnectionManager()


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
        connection_manager = getattr(hitl_manager, '_connection_manager', manager)
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
    """WebSocket 연결"""
    await manager.connect(websocket)

    try:
        # 초기 데이터 전송
        approvals = await hitl_manager.get_pending_approvals(limit=50)
        # datetime을 문자열로 변환하여 JSON 직렬화 가능하게 함
        from datetime import datetime
        
        data = []
        for req in approvals:
            req_dict = req.model_dump()
            # datetime 필드를 문자열로 변환
            if req_dict.get('created_at'):
                req_dict['created_at'] = req_dict['created_at'].isoformat() if isinstance(req_dict['created_at'], datetime) else req_dict['created_at']
            if req_dict.get('expires_at'):
                req_dict['expires_at'] = req_dict['expires_at'].isoformat() if isinstance(req_dict['expires_at'], datetime) else req_dict['expires_at']
            if req_dict.get('decided_at'):
                req_dict['decided_at'] = req_dict['decided_at'].isoformat() if isinstance(req_dict['decided_at'], datetime) else req_dict['decided_at']
            data.append(req_dict)
        
        await websocket.send_json(
            {"type": "initial_data", "data": data}
        )

        # 연결 유지
        while True:
            # 클라이언트 메시지 대기
            data = await websocket.receive_text()

            # Ping/Pong 처리
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 오류: {e}")
        manager.disconnect(websocket)
