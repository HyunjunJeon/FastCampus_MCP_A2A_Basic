"""
Redis 기반 A2A TaskStore 구현

A2A SDK 0.3.11 TaskStore 인터페이스를 Redis로 영속화하여
재구독/백필 품질을 강화합니다.

목표:
- A2A `TaskStore` 인터페이스를 Redis로 영속화하여 재구독/백필 품질을 강화
- InMemoryTaskStore의 휘발성 한계를 보완
- 분산 환경에서 Task 상태 공유 지원

환경변수:
- A2A_TASK_STORE: "redis" 설정 시 Redis TaskStore 활성화 (기본값: "memory")
- A2A_TASK_REDIS_URL: redis://localhost:6379/0 (기본값)
- A2A_TASK_TTL_SECONDS: Task 저장 TTL(초). 0 또는 미설정 시 TTL 미사용

사용 방법:
  export A2A_TASK_STORE=redis
  export A2A_TASK_REDIS_URL=redis://localhost:6379/0
  export A2A_TASK_TTL_SECONDS=3600
"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as redis

from a2a.types import Task
from a2a.server.tasks.task_store import TaskStore


class RedisTaskStore(TaskStore):
    """Redis 기반 TaskStore 구현체.

    저장 전략:
    - 키: a2a:task:{task_id}
    - 값: Task.model_dump_json() (UTF-8)
    - TTL: 환경변수 설정 시 적용
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl_seconds: int = 0) -> None:
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds if isinstance(ttl_seconds, int) and ttl_seconds > 0 else 0
        self._redis: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await redis.from_url(self._redis_url)
        return self._redis

    def _key(self, task_id: str) -> str:
        return f"a2a:task:{task_id}"

    async def save(self, task: Task) -> None:  # type: ignore[override]
        client = await self._get_client()
        data = task.model_dump_json()
        key = self._key(task.id)
        if self._ttl_seconds > 0:
            await client.setex(key, self._ttl_seconds, data)
        else:
            await client.set(key, data)

    async def get(self, task_id: str) -> Task | None:  # type: ignore[override]
        client = await self._get_client()
        raw = await client.get(self._key(task_id))
        if not raw:
            return None
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw_str = raw.decode("utf-8")
            else:
                raw_str = str(raw)
            return Task.model_validate_json(raw_str)
        except Exception:
            return None

    async def delete(self, task_id: str) -> None:  # type: ignore[override]
        client = await self._get_client()
        await client.delete(self._key(task_id))


