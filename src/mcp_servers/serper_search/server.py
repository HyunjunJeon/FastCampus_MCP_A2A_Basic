"""Serper Google 검색 MCP 서버 (python-mcp 표준 Server + Streamable HTTP)"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp_servers.serper_search.serper_dev_client import SerperClient

logger = logging.getLogger(__name__)


def create_app() -> Any:
    app = Server("Serper Google Search MCP Server")
    serper_client = SerperClient()

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_google",
                description="Google search via Serper.dev",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "number"},
                        "search_type": {"type": "string"},
                        "country": {"type": "string"},
                        "language": {"type": "string"},
                    },
                },
            ),
            types.Tool(
                name="search_google_news",
                description="Google News search via Serper.dev",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "number"},
                        "country": {"type": "string"},
                        "language": {"type": "string"},
                    },
                },
            ),
            types.Tool(
                name="search_google_images",
                description="Google Images search via Serper.dev",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "number"},
                        "country": {"type": "string"},
                        "language": {"type": "string"},
                    },
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[
        types.TextContent | types.ImageContent | types.EmbeddedResource
    ]:
        try:
            if name == "search_google":
                result = await serper_client.search(
                    query=str(arguments.get("query", "")),
                    search_type=str(arguments.get("search_type", "search")),
                    num_results=int(arguments.get("num_results", 10)),
                    country=str(arguments.get("country", "kr")),
                    language=str(arguments.get("language", "ko")),
                )
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "search_google_news":
                result = await serper_client.search(
                    query=str(arguments.get("query", "")),
                    search_type="news",
                    num_results=int(arguments.get("num_results", 10)),
                    country=str(arguments.get("country", "kr")),
                    language=str(arguments.get("language", "ko")),
                )
                return [types.TextContent(type="text", text=json.dumps(result))]

            if name == "search_google_images":
                result = await serper_client.search(
                    query=str(arguments.get("query", "")),
                    search_type="images",
                    num_results=int(arguments.get("num_results", 10)),
                    country=str(arguments.get("country", "kr")),
                    language=str(arguments.get("language", "ko")),
                )
                return [types.TextContent(type="text", text=json.dumps(result))]

            err = {"success": False, "error": f"Unknown tool: {name}"}
            return [types.TextContent(type="text", text=json.dumps(err))]
        except Exception as e:  # noqa: BLE001
            err = {"success": False, "error": f"{type(e).__name__}: {e}"}
            logger.exception("Serper tool error")
            return [types.TextContent(type="text", text=json.dumps(err))]

    session_manager = StreamableHTTPSessionManager(
        app=app,
        event_store=None,
        json_response=False,
        stateless=True,
    )

    async def handle_streamable_http(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    async def health(_):
        return JSONResponse({"success": True, "data": "OK", "query": "health"})

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        debug=False,
        routes=[
            Route("/health", endpoint=health, methods=["GET"]), 
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    return starlette_app
