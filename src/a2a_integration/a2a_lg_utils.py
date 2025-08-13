"""
공통 A2A 서버 빌드 유틸리티 (LangGraph 전용)

어떤 LangGraph 그래프(CompiledStateGraph)든 최소한의 코드로 A2A 서버를
구성할 수 있도록 헬퍼 함수들을 제공합니다.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable
import os
import hmac
import hashlib
import time

import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from langgraph.graph.state import CompiledStateGraph
from a2a.server.agent_execution import AgentExecutor
from src.utils.http_client import http_client


# TODO: "image/png", "audio/mpeg", "video/mp4"
# A2A 권장 최소 출력 모드 확장
SUPPORTED_CONTENT_MIME_TYPES = [
    "text/plain",
    "text/markdown",
    "application/json",
]


def _build_request_handler(executor: AgentExecutor) -> DefaultRequestHandler:
    """DefaultRequestHandler 기반의 구성

    - 공용 HTTP 풀을 재사용해 커넥션 누수를 방지한다.
    """
    # 공용 httpx 풀 재사용 (종료 시 cleanup_http_clients로 일괄 정리)
    httpx_client = http_client.get_client(client_id="a2a_push_http")

    # Push Notification egress allowlist 가드 설치 (SSRF 완화)
    # A2A 권장 보안 가이드 참고: 허용된 도메인/호스트만 푸시 전송 허용
    try:
        allow_env = os.getenv("A2A_PUSH_WEBHOOK_ALLOWLIST", "localhost,127.0.0.1")
        allow_hosts = [h.strip().lower() for h in allow_env.split(",") if h.strip()]

        async def _egress_guard(request):
            try:
                host = (request.url.host or "").lower()
                if not host:
                    return
                allowed = any(
                    host == ah or (host.endswith("." + ah) if "." in host else False)
                    for ah in allow_hosts
                )
                if not allowed:
                    raise httpx.RequestError(
                        f"Blocked by A2A push egress allowlist: {host}", request=request
                    )
            except Exception:
                # 방어적: 훅에서 예외가 나도 요청을 막아 SSRF를 억제
                raise

        hooks = getattr(httpx_client, "event_hooks", None)
        if hooks is not None:
            req_hooks = hooks.get("request") or []
            if _egress_guard not in req_hooks:
                req_hooks.append(_egress_guard)
            # 인증 헤더 주입: 토큰/HMAC 서명 (선택)
            default_token = os.getenv("A2A_PUSH_DEFAULT_TOKEN")
            hmac_secret = os.getenv("A2A_PUSH_HMAC_SECRET")

            async def _auth_injector(request):
                try:
                    if default_token:
                        request.headers.setdefault("X-A2A-Notification-Token", default_token)
                    if hmac_secret:
                        ts = str(int(time.time()))
                        body = request.content or b""
                        if not isinstance(body, (bytes, bytearray)):
                            try:
                                body = bytes(body)
                            except Exception:
                                body = b""
                        mac = hmac.new(hmac_secret.encode(), body + ts.encode(), hashlib.sha256).hexdigest()
                        request.headers.setdefault("X-A2A-Timestamp", ts)
                        request.headers.setdefault("X-A2A-Signature", f"sha256={mac}")
                except Exception:
                    pass

            if _auth_injector not in req_hooks:
                req_hooks.append(_auth_injector)
            hooks["request"] = req_hooks
    except Exception:
        # 훅 설치 실패 시에도 서버 동작은 지속
        pass
    # **DO NOT USE PRODUCTION**
    # TODO: MQ 기반 푸시 알림 구현 필요
    push_config_store = InMemoryPushNotificationConfigStore()
    push_sender = BasePushNotificationSender(
        httpx_client=httpx_client, 
        config_store=push_config_store
    )
    # TaskStore 선택: 환경변수로 Redis 전환 지원
    task_store = InMemoryTaskStore()
    try:
        use_redis = os.getenv("A2A_TASK_STORE", "memory").strip().lower() == "redis"
        if use_redis:
            from .redis_task_store import RedisTaskStore
            redis_url = os.getenv("A2A_TASK_REDIS_URL", "redis://localhost:6379/0")
            ttl = int(os.getenv("A2A_TASK_TTL_SECONDS", "0") or "0")
            task_store = RedisTaskStore(redis_url=redis_url, ttl_seconds=ttl)
    except Exception:
        pass

    return DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        push_config_store=push_config_store,
        push_sender=push_sender,
    )

def _build_a2a_application(agent_card: AgentCard, handler: DefaultRequestHandler) -> A2AStarletteApplication:
    """A2AStarletteApplication 생성"""
    return A2AStarletteApplication(agent_card=agent_card, http_handler=handler)

def create_agent_card(
    *,
    name: str,
    description: str,
    url: str,
    skills: Iterable[AgentSkill],
    version: str = "1.0.0",
    default_input_modes: list[str] | None = None,
    default_output_modes: list[str] | None = None,
    streaming: bool = True,
    push_notifications: bool = True,
) -> AgentCard:
    """A2A 프로토콜 표준에 맞는 AgentCard 생성."""
    capabilities = AgentCapabilities(
        streaming=streaming,
        push_notifications=push_notifications,
    )
    return AgentCard(
        name=name,
        description=description,
        url=url,
        version=version,
        default_input_modes=default_input_modes or ["text"],
        default_output_modes=default_output_modes or SUPPORTED_CONTENT_MIME_TYPES,
        capabilities=capabilities,
        skills=list(skills),
    )

def to_a2a_starlette_server(
    *,
    graph: CompiledStateGraph,
    agent_card: AgentCard,
    result_extractor: Callable[[Any], str] | None = None,
) -> A2AStarletteApplication:
    """CompiledStateGraph를 받아 A2A 서버 애플리케이션을 구성"""
    from .a2a_lg_agent_executor import LangGraphWrappedA2AExecutor
    executor = LangGraphWrappedA2AExecutor(graph=graph, result_extractor=result_extractor)
    handler = _build_request_handler(executor)
    return _build_a2a_application(agent_card, handler)

def to_a2a_run_uvicorn(
    *,
    server_app: A2AStarletteApplication,
    host: str,
    port: int,
):
    import uvicorn
    from starlette.routing import Route
    from starlette.responses import JSONResponse    
    
    app = server_app.build()
    async def health_check(request):
        return JSONResponse({"status": "healthy", "port": port})

    app.router.routes.append(Route("/health", health_check, methods=["GET"]))

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    server.run()

