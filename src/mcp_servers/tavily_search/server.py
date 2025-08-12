"""Tavily 웹 검색 MCP 서버 (python-mcp 표준 Server + Streamable HTTP)"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp_servers.tavily_search.tavily_search_client import TavilySearchAPI

logger = logging.getLogger(__name__)


def create_app() -> Any:
    app = Server("Tavily Search MCP Server")
    tavily_api = TavilySearchAPI()

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_web",
                description="Web search via Tavily",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "number"},
                        "search_depth": {"type": "string"},
                        "topic": {"type": "string"},
                        "time_range": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                        "days": {"type": "number"},
                        "include_domains": {"type": "array", "items": {"type": "string"}},
                        "exclude_domains": {"type": "array", "items": {"type": "string"}},
                    },
                },
            ),
            types.Tool(
                name="search_news",
                description="News search via Tavily",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "time_range": {"type": "string"},
                        "max_results": {"type": "number"},
                    },
                },
            ),
            types.Tool(
                name="search_finance",
                description="Finance-focused search via Tavily",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "number"},
                        "topic": {"type": "string"},
                        "search_depth": {"type": "string"},
                        "time_range": {"type": "string"},
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[
        types.TextContent | types.ImageContent | types.EmbeddedResource
    ]:
        try:
            if name == "search_web":
                payload = await tavily_api.search(
                    query=str(arguments.get("query", "")),
                    max_results=int(arguments.get("max_results", 5)),
                    search_depth=str(arguments.get("search_depth", "basic")),
                    topic=str(arguments.get("topic", "general")),
                    time_range=arguments.get("time_range"),
                    start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"),
                    days=arguments.get("days"),
                    include_domains=arguments.get("include_domains"),
                    exclude_domains=arguments.get("exclude_domains"),
                )
                return [types.TextContent(type="text", text=json.dumps(payload))]

            if name == "search_news":
                payload = await tavily_api.search(
                    query=str(arguments.get("query", "")),
                    search_depth="advanced",
                    max_results=int(arguments.get("max_results", 10)),
                    topic="news",
                    time_range=str(arguments.get("time_range", "week")),
                )
                return [types.TextContent(type="text", text=json.dumps(payload))]

            if name == "search_finance":
                payload = await tavily_api.search(
                    query=str(arguments.get("query", "")),
                    search_depth=str(arguments.get("search_depth", "advanced")),
                    max_results=int(arguments.get("max_results", 10)),
                    topic="finance",
                    time_range=arguments.get("time_range", "week"),
                    start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"),
                )
                return [types.TextContent(type="text", text=json.dumps(payload))]

            err = {"success": False, "error": f"Unknown tool: {name}"}
            return [types.TextContent(type="text", text=json.dumps(err))]
        except Exception as e:  # noqa: BLE001
            err = {"success": False, "error": f"{type(e).__name__}: {e}"}
            logger.exception("Tavily tool error")
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
