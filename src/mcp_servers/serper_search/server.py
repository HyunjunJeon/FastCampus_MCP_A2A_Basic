"""Serper Google 검색 MCP 서버 (FastMCP 기반)"""

from __future__ import annotations

from typing import Any

from mcp_servers.serper_search.serper_dev_client import SerperClient
from mcp_servers.base_mcp_server import BaseMCPServer


class SerperMCPServer(BaseMCPServer):
    """FastMCP 서버 구현: Serper.dev를 이용한 Google 검색 도구 제공"""

    def _initialize_clients(self) -> None:
        self.serper_client = SerperClient()

    def _register_tools(self) -> None:
        @self.mcp.tool()
        async def search_google(
            query: str,
            search_type: str = "search",
            num_results: int = 10,
            country: str = "kr",
            language: str = "ko",
        ) -> dict:
            """Google 검색 수행 (Serper.dev)

            - 다양한 검색 타입 지원: 일반 검색, 뉴스, 이미지 등.
            - 결과는 표준화된 딕셔너리 형태로 반환됩니다.

            Args:
                query: 검색 쿼리 텍스트
                search_type: 검색 타입 ("search" | "news" | "images" 등)
                num_results: 반환할 최대 결과 수
                country: 지역 코드 (ISO 3166-1 alpha-2)
                language: 언어 코드 (ISO 639-1)
            Returns:
                표준화된 검색 결과 딕셔너리
            """
            try:
                return await self.serper_client.search(
                    query=query,
                    search_type=search_type,
                    num_results=num_results,
                    country=country,
                    language=language,
                )
            except Exception as error:  # noqa: BLE001
                return await self.handle_error(
                    func_name="search_google",
                    error=error,
                    query=query,
                    search_type=search_type,
                )

        @self.mcp.tool()
        async def search_google_news(
            query: str,
            num_results: int = 10,
            country: str = "kr",
            language: str = "ko",
        ) -> dict:
            """Google 뉴스 검색 (Serper.dev)

            - 최근 뉴스 기사 중심으로 결과를 수집합니다.
            - 결과는 표준화된 딕셔너리 형태로 반환됩니다.
            """
            try:
                return await self.serper_client.search(
                    query=query,
                    search_type="news",
                    num_results=num_results,
                    country=country,
                    language=language,
                )
            except Exception as error:  # noqa: BLE001
                return await self.handle_error(
                    func_name="search_google_news",
                    error=error,
                    query=query,
                )

        @self.mcp.tool()
        async def search_google_images(
            query: str,
            num_results: int = 10,
            country: str = "kr",
            language: str = "ko",
        ) -> dict:
            """Google 이미지 검색 (Serper.dev)

            - 이미지 중심의 검색 결과를 반환합니다.
            - 결과는 표준화된 딕셔너리 형태로 반환됩니다.
            """
            try:
                return await self.serper_client.search(
                    query=query,
                    search_type="images",
                    num_results=num_results,
                    country=country,
                    language=language,
                )
            except Exception as error:  # noqa: BLE001
                return await self.handle_error(
                    func_name="search_google_images",
                    error=error,
                    query=query,
                )


def create_app() -> Any:
    """ASGI 앱 팩토리 (uvicorn --factory)

    FastMCP의 `http_app()`을 반환하며, MCP 엔드포인트는 `/mcp/`,
    헬스 체크는 `/health`에 노출됩니다.
    """
    server = SerperMCPServer(
        server_name="Serper Google Search MCP Server",
    )
    return server.create_app()
