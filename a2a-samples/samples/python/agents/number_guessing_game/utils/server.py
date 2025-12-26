"""서버 유틸리티 모듈.

SDK 서버 스택을 사용하여 A2A 에이전트를 호스팅하는 헬퍼 유틸리티입니다.
`DefaultRequestHandler`로 Starlette 앱을 생성하고 Uvicorn을 실행하는
최소한의 헬퍼를 제공합니다.

주요 함수:
    - build_starlette_app: Starlette ASGI 앱 생성
    - run_agent_blocking: Uvicorn 서버 실행 (블로킹)
"""

from __future__ import annotations

import uvicorn  # type: ignore

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import (
    DefaultRequestHandler,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard


def build_starlette_app(
    agent_card,
    *,
    executor,
):
    """서빙 준비가 된 Starlette ASGI 애플리케이션을 생성하고 반환합니다.

    Args:
        agent_card: 에이전트를 설명하는 원시 ``dict`` 또는
            :class:`a2a.types.AgentCard` 인스턴스.
        executor: 수신 요청을 처리할 A2A ``AgentExecutor``
            인터페이스의 구체적 구현.

    Returns:
        Starlette: ``/a2a/v1``에 SDK 요청 핸들러가 마운트된
            구성된 Starlette 애플리케이션.

    Raises:
        ValueError: executor가 None인 경우.
    """
    # Pydantic AgentCard 인스턴스가 있는지 확인
    if isinstance(agent_card, dict):
        agent_card = AgentCard.model_validate(agent_card)  # type: ignore[arg-type]

    # executor 검증
    if executor is None:
        raise ValueError('executor must be supplied')

    handler = DefaultRequestHandler(executor, InMemoryTaskStore())
    return A2AStarletteApplication(
        agent_card=agent_card, http_handler=handler
    ).build(rpc_url='/a2a/v1')


def run_agent_blocking(
    name: str,
    port: int,
    agent_card,
    *,
    executor,
) -> None:
    """주어진 에이전트를 위한 Uvicorn 서버를 시작하고 현재 스레드를 블로킹합니다.

    Args:
        name: 시작 시 출력되는 사람이 읽을 수 있는 에이전트 이름.
        port: 바인딩할 TCP 포트.
        agent_card: 에이전트를 설명하는 메타데이터 (``dict`` 또는 ``AgentCard``).
        executor: 요청을 처리할 ``AgentExecutor`` 인스턴스.
    """
    app = build_starlette_app(agent_card, executor=executor)
    print(f'{name} listening on http://localhost:{port}')
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='error')
