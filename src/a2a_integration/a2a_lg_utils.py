"""
공통 A2A 서버 빌드 유틸리티 (LangGraph 전용)

어떤 LangGraph 그래프(CompiledStateGraph)든 최소한의 코드로 A2A 서버를
구성할 수 있도록 헬퍼 함수들을 제공합니다.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

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


# TODO: "image/png", "audio/mpeg", "video/mp4"
SUPPORTED_CONTENT_MIME_TYPES = ["text/plain"]


def _build_request_handler(executor: AgentExecutor) -> DefaultRequestHandler:
    """DefaultRequestHandler 기반의 구성"""
    httpx_client = httpx.AsyncClient()
    # **DO NOT USE PRODUCTION**
    # TODO: MQ 기반 푸시 알림 구현 필요
    push_config_store = InMemoryPushNotificationConfigStore()
    push_sender = BasePushNotificationSender(
        httpx_client=httpx_client, 
        config_store=push_config_store
    )
    return DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
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

