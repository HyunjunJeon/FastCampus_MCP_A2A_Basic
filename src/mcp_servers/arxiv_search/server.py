"""arXiv 논문 검색 MCP 서버 (python-mcp 표준 Server + Streamable HTTP)"""

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

from mcp_servers.arxiv_search.arxiv_client import ArxivClient


logger = logging.getLogger(__name__)


def create_app() -> Any:
    """Starlette 앱 팩토리 (uvicorn --factory)"""
    app = Server("arXiv Search MCP Server")
    arxiv_client = ArxivClient()

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_arxiv_papers",
                description="Search arXiv papers by query/filters",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "number"},
                        "sort_by": {"type": "string"},
                        "category": {"type": "string"},
                    },
                },
            ),
            types.Tool(
                name="get_paper_details",
                description="Get details for a paper by arXiv ID",
                inputSchema={
                    "type": "object",
                    "required": ["arxiv_id"],
                    "properties": {
                        "arxiv_id": {"type": "string"},
                    },
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[
        types.TextContent | types.ImageContent | types.EmbeddedResource
    ]:
        try:
            if name == "search_arxiv_papers":
                query = str(arguments.get("query", ""))
                max_results = int(arguments.get("max_results", 10))
                sort_by = str(arguments.get("sort_by", "relevance"))
                category = arguments.get("category")

                papers = await arxiv_client.search_papers(
                    query=query,
                    max_results=max_results,
                    sort_by=sort_by,
                    category=category,
                )
                payload = {
                    "success": True,
                    "query": query,
                    "data": {"papers": papers, "total_results": len(papers)},
                    "search_params": {
                        "max_results": max_results,
                        "sort_by": sort_by,
                        "category": category,
                    },
                }
                return [types.TextContent(type="text", text=json.dumps(payload))]

            if name == "get_paper_details":
                arxiv_id = str(arguments.get("arxiv_id", ""))
                paper = await arxiv_client.get_paper_by_id(arxiv_id)
                if paper:
                    payload = {
                        "success": True,
                        "query": arxiv_id,
                        "data": {"paper": paper},
                    }
                else:
                    payload = {
                        "success": False,
                        "query": arxiv_id,
                        "error": "Paper not found",
                    }
                return [types.TextContent(type="text", text=json.dumps(payload))]

            # Unknown tool
            err = {"success": False, "error": f"Unknown tool: {name}"}
            return [types.TextContent(type="text", text=json.dumps(err))]
        except Exception as e:  # noqa: BLE001
            err = {"success": False, "error": f"{type(e).__name__}: {e}"}
            logger.exception("arXiv tool error")
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
    async def lifespan(_starlette_app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            try:
                yield
            finally:
                try:
                    await arxiv_client.close()
                except Exception:  # noqa: BLE001
                    pass

    starlette_app = Starlette(
        debug=False,
        routes=[
            Route("/health", endpoint=health, methods=["GET"]),
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    return starlette_app
