"""
내장 A2A 서버 매니저
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
    def __init__(self):
        self.servers: dict[str, dict[str, Any]] = {}
        self.running_tasks: dict[str, asyncio.Task] = {}

    def _find_free_port(self, start_port: int = 8080) -> int:
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

    async def _wait_for_server_ready(self, host: str, port: int, timeout: int = 10):
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

    async def _stop_server(self, server_key: str):
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
    manager = EmbeddedA2AServerManager()
    async with manager.start_graph_server(graph=graph, agent_card=agent_card, port=port, host=host) as server_info:
        yield server_info


