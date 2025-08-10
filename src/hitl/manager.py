"""
HITL 매니저 - Human-In-The-Loop 매니저
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta

from .models import ApprovalRequest, ApprovalStatus, ApprovalType, HITLPolicy
from .storage import approval_storage
from .notifications import NotificationService

logger = logging.getLogger(__name__)

class HITLManager:
    """Human-In-The-Loop 매니저"""
    
    def __init__(
        self,
        policy: Optional[HITLPolicy] = None,
        notification_service: Optional[NotificationService] = None
    ):
        self.policy = policy or HITLPolicy()
        self.notification_service = notification_service or NotificationService()
        self._approval_handlers: Dict[str, List[Callable]] = {}
        self._background_tasks = set()
        
    async def initialize(self):
        """매니저 초기화"""
        await approval_storage.connect()
        await self.notification_service.initialize()
        
        # 백그라운드 태스크 시작
        self._start_background_tasks()
        
        logger.info("HITL Manager 초기화 완료")
    
    async def shutdown(self):
        """종료 처리"""
        # 백그라운드 태스크 취소
        for task in self._background_tasks:
            task.cancel()
        
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        await approval_storage.disconnect()
        await self.notification_service.shutdown()

    async def _ensure_storage_connected(self) -> None:
        """ApprovalStorage가 연결되어 있지 않다면 안전하게 연결한다.

        - A2A 임베디드 서버처럼 FastAPI lifespan을 타지 않는 실행 경로에서
          `hitl_manager.initialize()`가 호출되지 않을 수 있다.
        - 이 가드는 `request_approval`, `approve`, `reject`, 조회 계열 메서드에서
          최초 호출 시점에 연결 상태를 보장해 Redis None 접근 오류를 방지한다.
        """
        try:
            if getattr(approval_storage, "_redis", None) is None:
                await approval_storage.connect()
        except Exception as e:
            logger.error(f"ApprovalStorage 연결 보장 실패: {e}")
            raise
    
    def _start_background_tasks(self):
        """백그라운드 태스크 시작"""
        # 만료 확인 태스크
        task = asyncio.create_task(self._check_expired_approvals())
        self._background_tasks.add(task)
        
        # 이벤트 리스너
        task = asyncio.create_task(self._listen_for_events())
        self._background_tasks.add(task)

    async def execute_deep_research_handler(self, request: ApprovalRequest):
        """승인 완료 시 Deep Research 자동 실행 핸들러"""
        try:
            # Deep Research 관련 승인 요청인지 확인
            if not self._is_research_related(request):
                logger.info(f"비연구 승인 요청, Deep Research 실행 안 함: {request.title}")
                return
            
            logger.info(f"Deep Research 자동 실행 시작: {request.title}")
            
            # WebSocket 연결 관리자 가져오기 (API 서버에서 설정)
            connection_manager = getattr(self, '_connection_manager', None)
            if not connection_manager:
                logger.warning("WebSocket 연결 관리자가 없습니다. 진행상황 브로드캐스트를 건너뜁니다.")
            
            # Deep Research 시작 브로드캐스트
            start_data = {
                "request_id": request.request_id,
                "task_id": request.task_id,
                "topic": request.title,
                "agent_id": request.agent_id,
                "started_at": datetime.utcnow(),
                "expected_duration": "5-15분",
                "stages": ["계획 수립", "데이터 수집", "분석 및 보고서 작성"]
            }
            
            if connection_manager:
                await connection_manager.broadcast_research_started(start_data)
            
            # 실제 Deep Research 실행
            research_query = self._extract_research_query(request)
            await self._run_deep_research_with_progress(
                query=research_query,
                request=request,
                connection_manager=connection_manager
            )
            
        except Exception as e:
            logger.error(f"Deep Research 실행 중 오류: {e}")
            
            # 실패 브로드캐스트
            if connection_manager:
                completion_data = {
                    "request_id": request.request_id,
                    "task_id": request.task_id,
                    "success": False,
                    "started_at": datetime.utcnow(),
                    "completed_at": datetime.utcnow(),
                    "final_status": "실패",
                    "summary": f"Deep Research 실행 중 오류가 발생했습니다: {str(e)}"
                }
                await connection_manager.broadcast_research_completed(completion_data)
    
    def _is_research_related(self, request: ApprovalRequest) -> bool:
        """연구 관련 승인 요청인지 확인"""
        research_keywords = [
            "연구", "분석", "조사", "리서치", "research", "analysis", "study"
        ]
        
        text_to_check = f"{request.title} {request.description}".lower()
        return any(keyword in text_to_check for keyword in research_keywords)
    
    def _extract_research_query(self, request: ApprovalRequest) -> str:
        """승인 요청에서 연구 쿼리 추출"""
        # 제목에서 핵심 연구 주제 추출
        title_clean = request.title.replace("승인", "").replace("요청", "").replace("계획", "").strip()
        
        # 컨텍스트에서 추가 정보 추출
        context_info = ""
        if hasattr(request, 'context') and request.context:
            if 'estimated_duration' in request.context:
                context_info += f" (기간: {request.context['estimated_duration']})"
            if 'data_sources' in request.context:
                context_info += f" (데이터 소스: {request.context['data_sources']}개)"
        
        query = f"{title_clean}{context_info}에 대해 상세히 연구해주세요."
        logger.info(f"추출된 연구 쿼리: {query}")
        return query
    
    async def _run_deep_research_with_progress(
        self, 
        query: str, 
        request: ApprovalRequest, 
        connection_manager
    ):
        """진행상황을 브로드캐스트하면서 Deep Research 실행"""
        from datetime import datetime
        import asyncio
        
        started_at = datetime.utcnow()
        
        try:
            # 단계별 진행상황 시뮬레이션 (실제 Deep Research 실행과 병행)
            stages = [
                {"stage": 1, "name": "계획 수립", "progress": 20, "action": "연구 계획을 수립하고 있습니다..."},
                {"stage": 2, "name": "데이터 수집", "progress": 60, "action": "관련 데이터를 수집하고 있습니다..."},
                {"stage": 3, "name": "분석 및 보고서 작성", "progress": 90, "action": "분석 결과를 정리하고 있습니다..."}
            ]
            
            # Deep Research를 백그라운드에서 실행
            research_task = asyncio.create_task(self._execute_actual_research(query))
            
            # 진행상황 업데이트
            for stage_info in stages:
                if connection_manager:
                    progress_data = {
                        "request_id": request.request_id,
                        "task_id": request.task_id,
                        "stage": stage_info["stage"],
                        "stage_name": stage_info["name"],
                        "progress": stage_info["progress"],
                        "total_stages": 3,
                        "estimated_time": f"{4 - stage_info['stage']}분 남음",
                        "current_action": stage_info["action"],
                        "timestamp": datetime.utcnow()
                    }
                    await connection_manager.broadcast_research_progress(progress_data)
                
                # 각 단계마다 2초 대기 (실제로는 더 긴 시간이 걸릴 수 있음)
                await asyncio.sleep(2)
            
            # Deep Research 완료 대기
            research_result = await research_task

            # 결과 파일 저장 (reports/)
            saved_path = None
            try:
                import os
                os.makedirs("reports", exist_ok=True)
                from datetime import datetime as _dt
                ts = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"final_report_{request.request_id}_{ts}.md"
                header = (
                    f"# 최종 보고서\n\n"
                    f"요청 ID: {request.request_id}\n"
                    f"제목: {request.title}\n"
                    f"시작: {started_at.isoformat()}Z\n"
                    f"완료: {_dt.utcnow().isoformat()}Z\n\n---\n\n"
                )
                final_report_text = research_result.get("final_report", "")
                with open(os.path.join("reports", filename), "w", encoding="utf-8") as f:
                    f.write(header + final_report_text)
                saved_path = os.path.join("reports", filename)
            except Exception as e:
                logger.error(f"최종 보고서 파일 저장 실패: {e}")

            # 완료 브로드캐스트
            completion_data = {
                "request_id": request.request_id,
                "task_id": request.task_id,
                "success": True,
                "total_duration": f"{(datetime.utcnow() - started_at).seconds}초",
                "started_at": started_at,
                "completed_at": datetime.utcnow(),
                "final_status": "완료",
                "summary": research_result.get("summary", "Deep Research가 성공적으로 완료되었습니다."),
                "final_report": research_result.get("final_report", ""),
                "saved_path": saved_path,
            }
            
            if connection_manager:
                await connection_manager.broadcast_research_completed(completion_data)
            
            logger.info(f"Deep Research 완료: {request.title}")
            
        except Exception as e:
            logger.error(f"Deep Research 진행 중 오류: {e}")
            raise
    
    async def _execute_actual_research(self, query: str) -> dict:
        """실제 Deep Research 실행 (A2A 기반)"""
        try:
            # A2A 클라이언트를 올바른 패턴으로 사용
            from a2a.client import ClientFactory, A2ACardResolver, ClientConfig
            from a2a.client.helpers import create_text_message_object
            from a2a.types import TransportProtocol, Role
            import httpx
            
            logger.info(f"A2A Deep Research 시작: {query}")
            
            # httpx 클라이언트 생성
            http_client = httpx.AsyncClient()
            
            try:
                # A2A Card Resolver로 agent card 가져오기
                resolver = A2ACardResolver(
                    httpx_client=http_client,
                    base_url="http://localhost:8090",
                )
                agent_card = await resolver.get_agent_card()
                
                # Client 설정 및 생성
                config = ClientConfig(
                    streaming=True,
                    supported_transports=[TransportProtocol.jsonrpc, TransportProtocol.http_json],
                )
                factory = ClientFactory(config=config)
                client = factory.create(card=agent_card)
                
                # A2A 메시지 생성
                message = create_text_message_object(
                    role=Role.user,
                    content=query
                )
                
                # A2A 서버에 요청 전송 및 결과 수집
                final_report = ""
                research_metadata = {}
                
                logger.info("A2A 요청 전송 중...")
                
                async for event in client.send_message(message):
                    # A2A 이벤트는 (Task, Event) tuple 구조
                    if isinstance(event, tuple) and len(event) >= 1:
                        task = event[0]  # 첫 번째는 Task 객체
                        
                        # Task에서 최종 응답 확인
                        if hasattr(task, 'artifacts') and task.artifacts:
                            for artifact in task.artifacts:
                                if hasattr(artifact, 'parts') and artifact.parts:
                                    for part in artifact.parts:
                                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                            text_content = part.root.text
                                            if text_content not in final_report:
                                                final_report += text_content
                        
                        # Task history에서 중간 메시지들 확인
                        elif hasattr(task, 'history') and task.history:
                            # 마지막 메시지만 처리 (중복 방지)
                            last_message = task.history[-1]
                            if (hasattr(last_message, 'role') and 
                                last_message.role.value == 'agent' and
                                hasattr(last_message, 'parts') and last_message.parts):
                                
                                for part in last_message.parts:
                                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                        text_content = part.root.text
                                        # 이미 포함된 내용인지 확인
                                        if text_content not in final_report:
                                            final_report += text_content + "\n"
                
                # 결과 정리
                return {
                    "summary": f"'{query}' 주제에 대한 A2A 기반 심층 연구가 완료되었습니다.",
                    "final_report": final_report.strip(),
                    "workflow": "a2a_orchestrated",
                    "metadata": research_metadata,
                    "notes_count": research_metadata.get("compressed_notes_count", 0),
                    "messages_count": research_metadata.get("raw_notes_count", 0)
                }
            
            finally:
                # httpx 클라이언트 정리
                await http_client.aclose()
            
        except Exception as e:
            logger.error(f"A2A Deep Research 실행 오류: {e}")
            # 실패 시에도 기본 응답 반환
            return {
                "summary": f"A2A 연구 실행 중 오류가 발생했습니다: {str(e)}",
                "final_report": "",
                "workflow": "a2a_orchestrated", 
                "metadata": {},
                "notes_count": 0,
                "messages_count": 0
            }
    
    def set_connection_manager(self, connection_manager):
        """WebSocket 연결 관리자 설정 (API 서버에서 호출)"""
        self._connection_manager = connection_manager
        logger.info("WebSocket 연결 관리자가 설정되었습니다.")
    
    async def _check_expired_approvals(self):
        """만료된 승인 요청 확인 (주기적)"""
        while True:
            try:
                await asyncio.sleep(60)  # 1분마다 확인
                
                expired = await approval_storage.check_expired_approvals()
                for request_id in expired:
                    await self._handle_timeout(request_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"만료 확인 오류: {e}")
    
    async def _listen_for_events(self):
        """Redis 이벤트 리스닝"""
        await approval_storage.subscribe_to_events([
            "approval:created",
            "approval:approved",
            "approval:rejected",
            "approval:timeout"
        ])
        
        while True:
            try:
                event = await approval_storage.get_event()
                if event:
                    await self._handle_event(event)
                    
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"이벤트 처리 오류: {e}")
    
    async def request_approval(
        self,
        agent_id: str,
        approval_type: ApprovalType,
        title: str,
        description: str,
        context: Dict[str, Any],
        options: Optional[List[str]] = None,
        timeout_seconds: Optional[int] = None,
        priority: str = "medium"
    ) -> ApprovalRequest:
        """승인 요청 생성"""
        # 저장소 연결 보장 (A2A 단독 구동 등 초기화 경로 누락 대비)
        await self._ensure_storage_connected()

        # 타임아웃 설정
        timeout = timeout_seconds or self.policy.auto_approve_timeout
        expires_at = datetime.utcnow() + timedelta(seconds=timeout)
        
        # 요청 생성
        request = ApprovalRequest(
            task_id=context.get("task_id", "unknown"),
            agent_id=agent_id,
            approval_type=approval_type,
            title=title,
            description=description,
            context=context,
            options=options or ["승인", "거부"],
            expires_at=expires_at,
            priority=priority
        )
        
        # 저장
        await approval_storage.create_approval_request(request)
        
        # 알림 전송
        await self.notification_service.send_approval_notification(request)
        
        logger.info(f"승인 요청 생성: {request.request_id} ({approval_type.value})")
        
        return request
    
    async def wait_for_approval(
        self,
        request_id: str,
        auto_approve_on_timeout: bool = True
    ) -> ApprovalRequest:
        """승인 대기"""
        logger.info(f"승인 대기 시작: {request_id}")
        
        while True:
            request = await approval_storage.get_approval_request(request_id)
            
            if not request:
                raise ValueError(f"승인 요청을 찾을 수 없습니다: {request_id}")
            
            # 상태 확인
            if request.status != ApprovalStatus.PENDING:
                logger.info(f"승인 완료: {request_id} -> {request.status.value}")
                return request
            
            # 타임아웃 확인
            if request.expires_at and datetime.utcnow() > request.expires_at:
                if auto_approve_on_timeout:
                    await self._handle_auto_approval(request_id)
                else:
                    await self._handle_timeout(request_id)
                
                return await approval_storage.get_approval_request(request_id)
            
            # 대기
            await asyncio.sleep(1)
    
    async def approve(
        self,
        request_id: str,
        decided_by: str,
        decision: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """승인 처리"""
        await self._ensure_storage_connected()
        success = await approval_storage.update_approval_status(
            request_id,
            ApprovalStatus.APPROVED,
            decided_by=decided_by,
            decision=decision or "승인",
            reason=reason
        )
        
        if success:
            await self._trigger_handlers(request_id, ApprovalStatus.APPROVED)
            
        return success
    
    async def reject(
        self,
        request_id: str,
        decided_by: str,
        reason: str
    ) -> bool:
        """거부 처리"""
        await self._ensure_storage_connected()
        if self.policy.require_reason_for_rejection and not reason:
            raise ValueError("거부 사유를 입력해야 합니다")
        
        success = await approval_storage.update_approval_status(
            request_id,
            ApprovalStatus.REJECTED,
            decided_by=decided_by,
            decision="거부",
            reason=reason
        )
        
        if success:
            await self._trigger_handlers(request_id, ApprovalStatus.REJECTED)
            
        return success
    
    async def _handle_auto_approval(self, request_id: str):
        """자동 승인 처리"""
        await approval_storage.update_approval_status(
            request_id,
            ApprovalStatus.AUTO_APPROVED,
            decided_by="system",
            decision="자동 승인",
            reason="타임아웃으로 인한 자동 승인"
        )
        
        await self._trigger_handlers(request_id, ApprovalStatus.AUTO_APPROVED)
    
    async def _handle_timeout(self, request_id: str):
        """타임아웃 처리"""
        await approval_storage.update_approval_status(
            request_id,
            ApprovalStatus.TIMEOUT,
            decided_by="system",
            decision="타임아웃",
            reason="승인 요청 시간 초과"
        )
        
        await self._trigger_handlers(request_id, ApprovalStatus.TIMEOUT)
    
    async def _handle_event(self, event: Dict[str, Any]):
        """이벤트 처리"""
        channel = event['channel']
        data = event['data']
        
        logger.debug(f"이벤트 수신: {channel} - {data}")
        
        # 이벤트별 처리 로직
        if channel == "approval:created":
            # 새 승인 요청 알림
            request = await approval_storage.get_approval_request(data['request_id'])
            if request:
                await self.notification_service.send_approval_notification(request)
    
    def register_handler(self, status: ApprovalStatus, handler: Callable):
        """상태 변경 핸들러 등록"""
        if status.value not in self._approval_handlers:
            self._approval_handlers[status.value] = []
        
        self._approval_handlers[status.value].append(handler)
    
    async def _trigger_handlers(self, request_id: str, status: ApprovalStatus):
        """핸들러 실행"""
        handlers = self._approval_handlers.get(status.value, [])
        request = await approval_storage.get_approval_request(request_id)
        
        for handler in handlers:
            try:
                await handler(request)
            except Exception as e:
                logger.error(f"핸들러 실행 오류: {e}")
    
    async def get_pending_approvals(self, **kwargs) -> List[ApprovalRequest]:
        """대기 중인 승인 요청 조회"""
        await self._ensure_storage_connected()
        return await approval_storage.get_pending_approvals(**kwargs)

    
    async def get_approved_approvals(self, **kwargs) -> List[ApprovalRequest]:
        """승인된 승인 요청 조회"""
        await self._ensure_storage_connected()
        return await approval_storage.get_approved_approvals(**kwargs)
    
    async def get_rejected_approvals(self, **kwargs) -> List[ApprovalRequest]:
        """거부된 승인 요청 조회"""
        await self._ensure_storage_connected()
        return await approval_storage.get_rejected_approvals(**kwargs)

# 전역 매니저 인스턴스
hitl_manager = HITLManager()