"""LangGraph 그래프를 A2A 서버로 변환하는 유틸리티 모듈.

LangGraph CompiledStateGraph를 A2A 프로토콜 표준 서버로 래핑하는
헬퍼 함수들을 제공합니다.

주요 기능:
    - AgentCard 생성 및 설정
    - DefaultRequestHandler 구성 (TaskStore, PushNotificationSender)
    - A2AStarletteApplication 빌더
    - 다중 전송 프로토콜 지원 (JSON-RPC, HTTP+JSON, gRPC)
    - Redis TaskStore 자동 전환
    - Push Notification 보안 (SSRF 방지, HMAC 서명)
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


def _build_request_handler(
    executor: AgentExecutor,
    queue_manager: Any | None = None,
    request_context_builder: Any | None = None,
) -> DefaultRequestHandler:
    """DefaultRequestHandler를 구성하여 반환합니다.

    AgentExecutor를 받아 TaskStore, PushNotificationSender 등을 설정하고
    DefaultRequestHandler를 생성합니다. 공용 HTTP 풀을 재사용하여
    커넥션 누수를 방지합니다.

    Args:
        executor: LangGraph를 래핑한 AgentExecutor 인스턴스.
        queue_manager: 커스텀 QueueManager. None이면 기본 InMemoryQueueManager 사용.
        request_context_builder: 커스텀 RequestContextBuilder. 
            None이면 기본 SimpleRequestContextBuilder 사용.

    Returns:
        설정이 완료된 DefaultRequestHandler 인스턴스.

    Note:
        환경변수로 Redis TaskStore 전환 가능:
            - A2A_TASK_STORE=redis
            - A2A_TASK_REDIS_URL=redis://localhost:6379/0
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

    # A2A SDK 0.3.11 새 파라미터 활용
    handler_kwargs = {
        "agent_executor": executor,
        "task_store": task_store,
        "push_config_store": push_config_store,
        "push_sender": push_sender,
    }
    
    # 선택적 파라미터 추가 (None이 아닌 경우에만)
    if queue_manager is not None:
        handler_kwargs["queue_manager"] = queue_manager
    if request_context_builder is not None:
        handler_kwargs["request_context_builder"] = request_context_builder
    
    return DefaultRequestHandler(**handler_kwargs)

def _build_a2a_application(
    agent_card: AgentCard,
    handler: DefaultRequestHandler,
    extended_agent_card: AgentCard | None = None,
    context_builder: Any | None = None,
    card_modifier: Callable[[AgentCard], AgentCard] | None = None,
    extended_card_modifier: Any | None = None,
) -> A2AStarletteApplication:
    """A2AStarletteApplication을 생성하여 반환합니다.

    Args:
        agent_card: 기본 AgentCard 설정.
        handler: DefaultRequestHandler 인스턴스.
        extended_agent_card: 인증된 사용자에게 노출할 확장 AgentCard.
        context_builder: 커스텀 CallContextBuilder.
        card_modifier: AgentCard를 동적으로 수정하는 함수.
        extended_card_modifier: 인증된 확장 카드를 동적으로 수정하는 함수.

    Returns:
        설정이 완료된 A2AStarletteApplication 인스턴스.
    """
    app_kwargs = {
        "agent_card": agent_card,
        "http_handler": handler,
    }
    
    # 선택적 파라미터 추가 (None이 아닌 경우에만)
    if extended_agent_card is not None:
        app_kwargs["extended_agent_card"] = extended_agent_card
    if context_builder is not None:
        app_kwargs["context_builder"] = context_builder
    if card_modifier is not None:
        app_kwargs["card_modifier"] = card_modifier
    if extended_card_modifier is not None:
        app_kwargs["extended_card_modifier"] = extended_card_modifier
    
    return A2AStarletteApplication(**app_kwargs)

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
    """A2A 프로토콜 표준 AgentCard를 생성합니다.

    Args:
        name: 에이전트 이름.
        description: 에이전트 설명.
        url: 에이전트 서비스 URL.
        skills: 에이전트가 제공하는 스킬 목록.
        version: 에이전트 버전 (기본: "1.0.0").
        default_input_modes: 지원하는 입력 모드 (기본: ["text"]).
        default_output_modes: 지원하는 출력 모드 (기본: text/plain, text/markdown, application/json).
        streaming: 스트리밍 지원 여부 (기본: True).
        push_notifications: Push Notification 지원 여부 (기본: True).

    Returns:
        생성된 AgentCard 인스턴스.
    """
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
    queue_manager: Any | None = None,
    request_context_builder: Any | None = None,
    extended_agent_card: AgentCard | None = None,
    context_builder: Any | None = None,
    card_modifier: Callable[[AgentCard], AgentCard] | None = None,
    extended_card_modifier: Any | None = None,
) -> A2AStarletteApplication:
    """LangGraph 그래프를 A2A 서버 애플리케이션으로 변환합니다.

    CompiledStateGraph를 AgentExecutor로 래핑하고 A2A 프로토콜 표준
    Starlette 애플리케이션을 구성하여 반환합니다.

    Args:
        graph: LangGraph CompiledStateGraph 인스턴스.
        agent_card: 기본 AgentCard 설정.
        result_extractor: 그래프 결과에서 텍스트를 추출하는 함수.
            None이면 기본 추출기 사용.
        queue_manager: 커스텀 QueueManager. None이면 기본 InMemoryQueueManager 사용.
        request_context_builder: 커스텀 RequestContextBuilder.
            None이면 기본 SimpleRequestContextBuilder 사용.
        extended_agent_card: 인증된 사용자에게 노출할 확장 AgentCard.
        context_builder: 커스텀 CallContextBuilder.
        card_modifier: AgentCard를 동적으로 수정하는 함수 (예: 사용자별 커스터마이징).
        extended_card_modifier: 인증된 확장 카드를 동적으로 수정하는 함수.

    Returns:
        설정이 완료된 A2AStarletteApplication 인스턴스.

    Examples:
        기본 사용:
            >>> app = to_a2a_starlette_server(
            ...     graph=my_graph,
            ...     agent_card=my_card,
            ... )

        동적 카드 수정:
            >>> def add_premium_skills(card):
            ...     card.skills.append(premium_skill)
            ...     return card
            >>> app = to_a2a_starlette_server(
            ...     graph=my_graph,
            ...     agent_card=basic_card,
            ...     card_modifier=add_premium_skills,
            ... )
    """
    from .a2a_lg_agent_executor import LangGraphWrappedA2AExecutor
    executor = LangGraphWrappedA2AExecutor(graph=graph, result_extractor=result_extractor)
    handler = _build_request_handler(
        executor,
        queue_manager=queue_manager,
        request_context_builder=request_context_builder,
    )
    return _build_a2a_application(
        agent_card,
        handler,
        extended_agent_card=extended_agent_card,
        context_builder=context_builder,
        card_modifier=card_modifier,
        extended_card_modifier=extended_card_modifier,
    )

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

