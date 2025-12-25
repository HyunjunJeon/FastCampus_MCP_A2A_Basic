"""
Webhook 이벤트 저장소 (Redis 기반)

푸시(Webhook)로 수신한 A2A 알림 이벤트를 Task별로 보관/조회하기 위한 간단한 저장소.

환경변수:
- A2A_WEBHOOK_REDIS_URL: redis://localhost:6379/0 (기본)
- A2A_WEBHOOK_EVENTS_TTL: 키 TTL(초, 기본 3600)
"""

from __future__ import annotations

import json
from typing import Optional, List, Any

import redis.asyncio as redis


class WebhookEventStorage:
    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl_seconds: int = 3600) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds if ttl_seconds and ttl_seconds > 0 else 3600
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = await redis.from_url(self.redis_url)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _key(self, task_id: str) -> str:
        return f"a2a:webhook:task:{task_id}"

    def _get_redis(self) -> redis.Redis[bytes]:
        """연결된 Redis 클라이언트를 반환합니다."""
        if self._redis is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._redis

    async def add_event(self, task_id: str, payload: Any) -> None:
        if self._redis is None:
            await self.connect()
        r = self._get_redis()
        key = self._key(task_id)
        try:
            data = json.dumps(payload, ensure_ascii=False)
        except Exception:
            data = json.dumps({"raw": str(payload)})
        await r.rpush(key, data)
        await r.expire(key, self.ttl_seconds)

    async def get_events(self, task_id: str, limit: int = 100) -> List[Any]:
        if self._redis is None:
            await self.connect()
        r = self._get_redis()
        key = self._key(task_id)
        total = await r.llen(key)
        if total is None or total == 0:
            return []
        start = max(0, int(total) - int(limit))
        rows = await r.lrange(key, start, -1)
        results: List[Any] = []
        for row in rows:
            try:
                if isinstance(row, (bytes, bytearray)):
                    results.append(json.loads(row.decode("utf-8")))
                else:
                    results.append(json.loads(str(row)))
            except Exception:
                results.append({"raw": row.decode("utf-8") if isinstance(row, (bytes, bytearray)) else str(row)})
        return results


# 싱글톤 인스턴스
webhook_storage = WebhookEventStorage()


