"""arXiv 논문 검색 MCP 서버 (FastMCP 기반)"""

from __future__ import annotations

from typing import Any

from mcp_servers.arxiv_search.arxiv_client import ArxivClient
from mcp_servers.base_mcp_server import BaseMCPServer


class ArxivMCPServer(BaseMCPServer):
    """FastMCP 서버 구현: arXiv 검색 도구 제공"""

    def _initialize_clients(self) -> None:
        self.arxiv_client = ArxivClient()

    def _register_tools(self) -> None:
        @self.mcp.tool()
        async def search_arxiv_papers(
            query: str,
            max_results: int = 10,
            sort_by: str = "relevance",
            category: str | None = None,
        ) -> dict:
            """arXiv 논문 검색

            - 키워드/카테고리/정렬 기준을 지정해 논문을 조회합니다.
            - 결과는 표준화된 딕셔너리로 반환됩니다.
            """
            try:
                papers = await self.arxiv_client.search_papers(
                    query=query,
                    max_results=max_results,
                    sort_by=sort_by,
                    category=category,
                )
                return self.create_standard_response(
                    success=True,
                    query=query,
                    data={"papers": papers, "total_results": len(papers)},
                    search_params={
                        "max_results": max_results,
                        "sort_by": sort_by,
                        "category": category,
                    },
                )
            except Exception as error:  # noqa: BLE001
                return await self.handle_error(
                    func_name="search_arxiv_papers", error=error, query=query
                )

        @self.mcp.tool()
        async def get_paper_details(arxiv_id: str) -> dict:
            """arXiv ID로 논문 상세 조회

            - 정확한 arXiv ID를 사용하여 특정 논문의 상세 정보를 반환합니다.
            - 결과는 표준화된 딕셔너리로 반환됩니다.
            """
            try:
                paper = await self.arxiv_client.get_paper_by_id(arxiv_id)
                if paper:
                    return self.create_standard_response(
                        success=True, query=arxiv_id, data={"paper": paper}
                    )
                return self.create_standard_response(
                    success=False, query=arxiv_id, error="Paper not found"
                )
            except Exception as error:  # noqa: BLE001
                return await self.handle_error(
                    func_name="get_paper_details", error=error, query=arxiv_id
                )


def create_app() -> Any:
    """ASGI 앱 팩토리 (uvicorn --factory)"""
    server = ArxivMCPServer(server_name="arXiv Search MCP Server")
    return server.create_app()
