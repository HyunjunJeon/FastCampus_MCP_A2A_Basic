"""내장 A2A 서버 매니저 모듈.

LangGraph CompiledStateGraph를 A2A 프로토콜 호환 서버로 래핑하여
임베디드 모드로 실행하는 기능을 제공합니다.

주요 기능:
    - 비동기 컨텍스트 매니저로 A2A 서버 수명주기 관리
    - 자동 포트 검색 및 헬스체크
    - Uvicorn 기반 ASGI 서버 실행
    - 안전한 서버 종료 및 리소스 정리

Example:
    >>> from langgraph.graph.state import CompiledStateGraph
    >>> async with start_embedded_graph_server(
    ...     graph=my_graph,
    ...     agent_card=my_card,
    ...     port=8080
    ... ) as server_info:
    ...     print(f"Server running at {server_info['base_url']}")
"""

import asyncio
from src.utils.logging_config import get_logger
import socket
from contextlib import asynccontextmanager
from typing import Any
import uvicorn
import time

from .a2a_lg_utils import to_a2a_starlette_server
from a2a.types import AgentCard
from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class EmbeddedA2AServerManager:
    """내장 A2A 서버 수명주기 매니저.

    LangGraph 그래프를 A2A 서버로 래핑하여 실행하고,
    비동기 컨텍스트 매니저를 통해 안전하게 수명주기를 관리합니다.

    Attributes:
        servers: 실행 중인 서버 정보를 저장하는 딕셔너리.
        running_tasks: 실행 중인 asyncio 태스크를 추적하는 딕셔너리.
    """

    def __init__(self) -> None:
        """EmbeddedA2AServerManager 인스턴스를 초기화합니다."""
        self.servers: dict[str, dict[str, Any]] = {}
        self.running_tasks: dict[str, asyncio.Task[None]] = {}

    def _find_free_port(self, start_port: int = 8080) -> int:
        """사용 가능한 빈 포트를 검색합니다.

        Args:
            start_port: 검색을 시작할 포트 번호.

        Returns:
            사용 가능한 포트 번호.

        Raises:
            RuntimeError: 1000개 포트 범위 내에서 사용 가능한 포트를 찾지 못한 경우.
        """
        for port in range(start_port, start_port + 1000):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("localhost", port))
                    return port
            except OSError:
                continue
        raise RuntimeError("사용 가능한 포트를 찾을 수 없습니다")

    @asynccontextmanager
    async def start_graph_server(
        self,
        *,
        graph: CompiledStateGraph,
        agent_card: AgentCard,
        host: str = "localhost",
        port: int | None = None,
    ):
        """LangGraph 그래프를 A2A 서버로 시작합니다.

        비동기 컨텍스트 매니저로 사용하여 서버 수명주기를 자동 관리합니다.
        서버는 /health 엔드포인트와 A2A 표준 엔드포인트를 제공합니다.

        Args:
            graph: 래핑할 LangGraph CompiledStateGraph 인스턴스.
            agent_card: A2A 에이전트 메타데이터 (이름, 설명, 스킬 등).
            host: 바인딩할 호스트 주소 (기본값: "localhost").
            port: 바인딩할 포트 번호 (None이면 자동 검색).

        Yields:
            서버 정보 딕셔너리:
                - host: 바인딩된 호스트 주소
                - port: 바인딩된 포트 번호
                - base_url: 서버 기본 URL

        Raises:
            TimeoutError: 서버가 10초 내에 시작되지 않은 경우.
            Exception: 서버 시작 또는 실행 중 오류 발생 시.
        """
        if port is None:
            port = self._find_free_port()
        server_key = f"graph:{agent_card.name}:{agent_card.url}"
        started_successfully = False
        try:
            # url 정합성 보정: AgentCard.url 이 None/빈값이면 host/port 기반으로 보완
            try:
                card_url = getattr(agent_card, "url", None)
                if not isinstance(card_url, str) or not card_url.strip():
                    agent_card = AgentCard(
                        name=getattr(agent_card, "name", "A2A Agent"),
                        description=getattr(agent_card, "description", ""),
                        url=f"http://{host}:{port}",
                        version=getattr(agent_card, "version", "1.0.0"),
                        default_input_modes=getattr(agent_card, "default_input_modes", ["text"]),
                        default_output_modes=getattr(agent_card, "default_output_modes", ["text/plain"]),
                        capabilities=getattr(agent_card, "capabilities", None),
                        skills=getattr(agent_card, "skills", []),
                    )
            except Exception:
                pass

            logger.info(f"Starting A2A server for agent '{getattr(agent_card, 'name', '')}' at url='{getattr(agent_card, 'url', None)}' host={host} port={port}")
            server_app = to_a2a_starlette_server(
                graph=graph,
                agent_card=agent_card,
            )
            app = server_app.build()

            from starlette.routing import Route
            from starlette.responses import JSONResponse
            from starlette.requests import Request

            async def health_check(request: Request):
                return JSONResponse({"status": "healthy", "agent": agent_card.name})

            app.router.routes.append(Route("/health", health_check, methods=["GET"]))

            # Avoid uvicorn default dictConfig to prevent formatter conflicts when app overrides logging
            config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False, log_config=None)
            server = uvicorn.Server(config)
            logger.info(f"🚀 Graph A2A Agent 서버 시작 중... (포트: {port})")
            server_task = asyncio.create_task(server.serve())
            self.running_tasks[server_key] = server_task

            await self._wait_for_server_ready(host, port)

            self.servers[server_key] = {
                "agent_type": None,
                "host": host,
                "port": port,
                "server": server,
                "task": server_task,
            }

            logger.info(f"✅ Graph A2A Agent 서버 정상 시작됨 - http://{host}:{port}")

            started_successfully = True
            yield {"host": host, "port": port, "base_url": f"http://{host}:{port}", "agent_type": None}

        except Exception as e:
            import traceback
            detail = f"url={getattr(agent_card, 'url', None)} host={host} port={port}"
            if not started_successfully:
                logger.error(f"❌ Graph A2A Agent 서버 시작 실패: {e}\n{detail}\n{traceback.format_exc()}")
            else:
                logger.error(f"❌ Graph A2A Agent 서버 실행 중 예외 발생: {e}\n{detail}\n{traceback.format_exc()}")
            raise
        finally:
            await self._stop_server(server_key)

    async def _wait_for_server_ready(self, host: str, port: int, timeout: int = 10) -> None:
        """서버가 준비될 때까지 헬스체크를 수행합니다.

        Args:
            host: 서버 호스트 주소.
            port: 서버 포트 번호.
            timeout: 최대 대기 시간 (초).

        Raises:
            TimeoutError: 지정된 시간 내에 서버가 응답하지 않은 경우.
            asyncio.CancelledError: 대기 중 취소된 경우.
        """
        from src.utils.http_client import http_client
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # 0.0.0.0 바인드 시 로컬 헬스체크는 127.0.0.1로 접근
                probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
                response = await http_client.get(f"http://{probe_host}:{port}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except asyncio.CancelledError:
                # 취소 시 조용히 종료
                raise
            except Exception:
                await asyncio.sleep(0.5)
        raise TimeoutError("서버가 제한 시간 내에 시작되지 않았습니다")

    async def _stop_server(self, server_key: str) -> None:
        """서버를 안전하게 종료하고 리소스를 정리합니다.

        Args:
            server_key: 종료할 서버의 고유 키.
        """
        if server_key in self.servers:
            server_info = self.servers[server_key]
            logger.info("🔻 서버 중지 중...")
            if "server" in server_info:
                server_info["server"].should_exit = True
            await asyncio.sleep(0.2)
            if server_key in self.running_tasks:
                task = self.running_tasks[server_key]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        # 취소는 정상 흐름으로 간주
                        pass
                del self.running_tasks[server_key]
            del self.servers[server_key]
            logger.info("✅ A2A Agent 서버 종료 완료")


@asynccontextmanager
async def start_embedded_graph_server(
    *,
    graph: CompiledStateGraph,
    agent_card: AgentCard,
    host: str = "0.0.0.0",
    port: int = 8000,
):
    """LangGraph 그래프를 임베디드 A2A 서버로 실행하는 컨텍스트 매니저.

    일회성 서버 실행에 최적화된 편의 함수입니다.
    내부적으로 EmbeddedA2AServerManager를 생성하고 관리합니다.

    Args:
        graph: 래핑할 LangGraph CompiledStateGraph 인스턴스.
        agent_card: A2A 에이전트 메타데이터.
        host: 바인딩할 호스트 주소 (기본값: "0.0.0.0").
        port: 바인딩할 포트 번호 (기본값: 8000).

    Yields:
        서버 정보 딕셔너리 (host, port, base_url 포함).

    Example:
        >>> async with start_embedded_graph_server(
        ...     graph=compiled_graph,
        ...     agent_card=card,
        ...     port=8090
        ... ) as info:
        ...     async with A2AClientManager(info["base_url"]) as client:
        ...         result = await client.send_query("Hello")
    """
    manager = EmbeddedA2AServerManager()
    async with manager.start_graph_server(graph=graph, agent_card=agent_card, port=port, host=host) as server_info:
        yield server_info


