"""
HITL 승인 요청 저장소 (Redis 기반)

=== 주요 기능 ===
이 모듈은 HITL 시스템의 핵심 데이터 저장 및 관리 기능을 제공합니다:

1. 승인 요청 생명주기 관리
   - 승인 요청 생성 및 저장 (create_approval_request)
   - 승인 요청 조회 및 상태 확인 (get_approval_request)
   - 승인/거부 처리 (update_approval_status)
   - 만료된 요청 자동 정리 (cleanup_expired_requests)

2. Redis 기반 영속성
   - 비동기 Redis 클라이언트 사용
   - JSON 직렬화/역직렬화로 복잡한 객체 저장
   - TTL(Time-To-Live) 설정으로 자동 만료 처리
   - Connection pooling 및 리소스 관리

3. 실시간 알림 (Pub/Sub)
   - Redis Pub/Sub을 통한 상태 변경 알림
   - 웹 클라이언트와의 실시간 동기화
   - 다중 구독자 지원

4. 쿼리 및 필터링
   - 상태별 승인 요청 목록 조회
   - 에이전트별, 타입별 필터링
   - 페이징 및 정렬 지원

=== Redis 키 구조 ===
- approval:{request_id} : 개별 승인 요청 데이터
- pending_approvals : 대기 중인 승인 요청 목록 (Set)
- approved_approvals : 승인된 요청 목록 (Set)
- rejected_approvals : 거부된 요청 목록 (Set)
- approval_events : Pub/Sub 채널

=== 사용 예시 ===
```python
storage = ApprovalStorage()
await storage.connect()

# 승인 요청 생성
request = ApprovalRequest(...)
request_id = await storage.create_approval_request(request)

# 상태 업데이트
await storage.update_approval_status(request_id, "approved")

await storage.disconnect()
```
"""
import json
import logging
from typing import Optional, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from contextlib import asynccontextmanager

from .models import ApprovalRequest, ApprovalStatus, ApprovalType

logger = logging.getLogger(__name__)

class ApprovalStorage:
    """승인 요청 저장소 (Redis 기반)"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        
    async def connect(self):
        """Redis 연결"""
        # 기존 연결이 있다면 정리 후 재연결
        try:
            if self._pubsub or self._redis:
                await self.disconnect()
        except Exception:
            pass

        self._redis = await redis.from_url(self.redis_url)
        self._pubsub = self._redis.pubsub()
        logger.info("Redis 연결 완료")
    
    async def disconnect(self):
        """연결 종료"""
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
    
    @asynccontextmanager
    async def connection(self):
        """컨텍스트 매니저"""
        await self.connect()
        try:
            yield self
        finally:
            await self.disconnect()
    
    async def create_approval_request(self, request: ApprovalRequest) -> str:
        """승인 요청 생성"""
        key = f"approval:{request.request_id}"
        
        # Redis에 저장
        await self._redis.setex(
            key,
            timedelta(hours=24),  # 24시간 TTL
            request.model_dump_json()
        )
        
        # 인덱스 추가
        await self._redis.sadd("approvals:pending", request.request_id)
        await self._redis.sadd(f"approvals:agent:{request.agent_id}", request.request_id)
        await self._redis.sadd(f"approvals:type:{request.approval_type.value}", request.request_id)
        
        # 이벤트 발행
        await self._redis.publish(
            "approval:created",
            json.dumps({
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "type": request.approval_type.value,
                "priority": request.priority
            })
        )
        
        logger.info(f"승인 요청 생성: {request.request_id}")
        return request.request_id
    
    async def get_approval_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """승인 요청 조회"""
        key = f"approval:{request_id}"
        data = await self._redis.get(key)
        
        if data:
            return ApprovalRequest.model_validate_json(data)
        return None
    
    async def update_approval_status(
        self,
        request_id: str,
        status: ApprovalStatus,
        decided_by: Optional[str] = None,
        decision: Optional[str] = None,
        reason: Optional[str] = None
    ) -> bool:
        """승인 상태 업데이트"""
        request = await self.get_approval_request(request_id)
        if not request:
            return False
        
        # 상태 업데이트
        request.status = status
        request.decided_at = datetime.utcnow()
        request.decided_by = decided_by
        request.decision = decision
        request.decision_reason = reason
        
        # Redis 업데이트
        key = f"approval:{request_id}"
        await self._redis.setex(
            key,
            timedelta(hours=24),
            request.model_dump_json()
        )
        
        # 인덱스 업데이트
        await self._redis.srem("approvals:pending", request_id)
        await self._redis.sadd(f"approvals:{status.value}", request_id)
        
        # 이벤트 발행
        await self._redis.publish(
            f"approval:{status.value}",
            json.dumps({
                "request_id": request_id,
                "status": status.value,
                "decided_by": decided_by,
                "decision": decision
            })
        )
        
        logger.info(f"승인 상태 업데이트: {request_id} -> {status.value}")
        return True
    
    async def get_pending_approvals(
        self,
        agent_id: Optional[str] = None,
        approval_type: Optional[ApprovalType] = None,
        limit: int = 100
    ) -> List[ApprovalRequest]:
        """대기 중인 승인 요청 조회"""
        # 기본 대기 목록
        pending_ids = await self._redis.smembers("approvals:pending")
        
        # 필터링
        if agent_id:
            agent_ids = await self._redis.smembers(f"approvals:agent:{agent_id}")
            pending_ids = pending_ids.intersection(agent_ids)
        
        if approval_type:
            type_ids = await self._redis.smembers(f"approvals:type:{approval_type.value}")
            pending_ids = pending_ids.intersection(type_ids)
        
        # 요청 로드
        requests = []
        for request_id in list(pending_ids)[:limit]:
            request = await self.get_approval_request(request_id.decode())
            if request:
                requests.append(request)
        
        # 우선순위 정렬
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        requests.sort(key=lambda r: (priority_order.get(r.priority, 4), r.created_at))
        
        return requests

    async def get_approved_approvals(
        self,
        agent_id: Optional[str] = None,
        approval_type: Optional[ApprovalType] = None,
        limit: int = 100
    ) -> List[ApprovalRequest]:
        """승인된 승인 요청 조회"""
        # 기본 승인 목록
        approved_ids = await self._redis.smembers("approvals:approved")
        
        # 필터링
        if agent_id:
            agent_ids = await self._redis.smembers(f"approvals:agent:{agent_id}")
            approved_ids = approved_ids.intersection(agent_ids)
        
        if approval_type:
            type_ids = await self._redis.smembers(f"approvals:type:{approval_type.value}")
            approved_ids = approved_ids.intersection(type_ids)
        
        # 요청 로드
        requests = []
        for request_id in list(approved_ids)[:limit]:
            request = await self.get_approval_request(request_id.decode())
            if request:
                requests.append(request)
        
        # 결정 시간 기준 역순 정렬 (최신 승인부터)
        requests.sort(key=lambda r: r.decided_at or r.created_at, reverse=True)
        
        return requests

    async def get_rejected_approvals(
        self,
        agent_id: Optional[str] = None,
        approval_type: Optional[ApprovalType] = None,
        limit: int = 100
    ) -> List[ApprovalRequest]:
        """거부된 승인 요청 조회"""
        # 기본 거부 목록
        rejected_ids = await self._redis.smembers("approvals:rejected")
        
        # 필터링
        if agent_id:
            agent_ids = await self._redis.smembers(f"approvals:agent:{agent_id}")
            rejected_ids = rejected_ids.intersection(agent_ids)
        
        if approval_type:
            type_ids = await self._redis.smembers(f"approvals:type:{approval_type.value}")
            rejected_ids = rejected_ids.intersection(type_ids)
        
        # 요청 로드
        requests = []
        for request_id in list(rejected_ids)[:limit]:
            request = await self.get_approval_request(request_id.decode())
            if request:
                requests.append(request)
        
        # 결정 시간 기준 역순 정렬 (최신 거부부터)
        requests.sort(key=lambda r: r.decided_at or r.created_at, reverse=True)
        
        return requests
    
    async def check_expired_approvals(self) -> List[str]:
        """만료된 승인 요청 확인 및 처리"""
        expired = []
        pending_ids = await self._redis.smembers("approvals:pending")
        
        for request_id in pending_ids:
            request = await self.get_approval_request(request_id.decode())
            if request and request.expires_at:
                if datetime.utcnow() > request.expires_at:
                    # 타임아웃 처리
                    await self.update_approval_status(
                        request_id.decode(),
                        ApprovalStatus.TIMEOUT,
                        decided_by="system",
                        decision="timeout",
                        reason="승인 요청 시간 초과"
                    )
                    expired.append(request_id.decode())
        
        return expired
    
    async def subscribe_to_events(self, channels: List[str]):
        """이벤트 구독"""
        if self._pubsub is None:
            await self.connect()
        await self._pubsub.subscribe(*channels)
        logger.info(f"이벤트 구독: {channels}")
    
    async def get_event(self):
        """이벤트 수신"""
        message = await self._pubsub.get_message(ignore_subscribe_messages=True)
        if message and message['type'] == 'message':
            return {
                'channel': message['channel'].decode(),
                'data': json.loads(message['data'])
            }
        return None

# 싱글톤 인스턴스
approval_storage = ApprovalStorage()