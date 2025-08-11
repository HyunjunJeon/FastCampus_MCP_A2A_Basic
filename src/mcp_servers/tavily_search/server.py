"""Tavily 웹 검색 MCP 서버"""

from typing import Any, Literal
from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers.base_mcp_server import BaseMCPServer
from mcp_servers.tavily_search.tavily_search_client import TavilySearchAPI

load_dotenv()


class TavilySearchServer(BaseMCPServer):
    """
    Tavily를 이용한 웹 검색 MCP 서버
    
    Tavily API를 활용하여 최신 웹 정보와 뉴스를 검색하는 MCP 서버입니다.
    실시간 웹 검색, 뉴스 검색, 도메인 필터링 등의 기능을 제공합니다.
    """

    def __init__(self):
        """
        TavilySearchServer 초기화
        
        포트 3001에서 Tavily 검색 MCP 서버를 시작합니다.
        """
        super().__init__(
            server_name="Tavily Search MCP Server",
            port=3001,
        )

    def _initialize_clients(self) -> None:
        """
        TavilySearchAPI 클라이언트 인스턴스 초기화
        
        환경변수에서 API 키를 읽어 TavilySearchAPI 클라이언트를 생성합니다.
        """
        self.tavily_api = TavilySearchAPI()

    def _register_tools(self) -> None:
        """
        MCP 도구 등록
        
        웹 검색과 뉴스 검색 도구를 MCP 서버에 등록합니다.
        각 도구는 비동기 함수로 구현되며 표준화된 응답 형식을 반환합니다.
        """

        @self.mcp.tool
        async def search_web(
            query: str,
            max_results: int = 5,
            search_depth: Literal["basic", "advanced"] = "basic",
            topic: Literal["general"] = "general",
            time_range: Literal["day", "week", "month", "year"] | None = None,
            start_date: str | None = None,
            end_date: str | None = None,
            days: int | None = None,
            include_domains: list[str] | None = None,
            exclude_domains: list[str] | None = None,
        ) -> dict[str, Any]:
            """
            웹에서 최신 정보를 검색합니다.
            
            TavilySearchAPI 를 통해 실시간 웹 검색을 수행하며,
            다양한 필터링 옵션을 제공합니다.

            Args:
                query: 검색할 키워드 또는 질문
                max_results: 반환할 최대 결과 수 (기본값: 5)
                search_depth: 검색 깊이 ("basic": 빠른 검색, "advanced": 상세 검색)
                topic: 검색 주제 필터 ("general", "news", "finance")
                time_range: 검색할 시간 범위 ("day", "week", "month", "year")
                start_date: 시작 날짜 (YYYY-MM-DD 형식)
                end_date: 종료 날짜 (YYYY-MM-DD 형식)
                days: 최근 며칠 이내의 결과만 검색
                include_domains: 포함할 도메인 리스트 (예: ["wikipedia.org"])
                exclude_domains: 제외할 도메인 리스트 (예: ["ads.com"])

            """
            try:
                self.logger.info(f"웹 검색 시작: {query}")

                # TavilySearchAPI 를 통한 검색 실행
                results = await self.tavily_api.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    topic=topic,
                    time_range=time_range,
                    start_date=start_date,
                    end_date=end_date,
                    days=days,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                )

                # 표준화된 응답 형식으로 반환
                return self.create_standard_response(
                    success=True,
                    query=query,
                    data={"results": results, "total_results": len(results)},
                    search_params={
                        "search_depth": search_depth,
                        "max_results": max_results,
                        "topic": topic,
                        "time_range": time_range,
                    },
                )

            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error("search_web", e, query=query)

        @self.mcp.tool
        async def search_news(
            query: str,
            time_range: Literal["day", "week", "month", "year"] = "week",
            max_results: int = 10,
        ) -> dict[str, Any]:
            """
            최신 뉴스를 검색합니다.
            
            뉴스 주제로 특화된 검색을 수행하여 신뢰할 수 있는
            뉴스 소스에서 최신 정보를 가져옵니다.

            Args:
                query: 검색할 뉴스 키워드
                time_range: 뉴스 검색 시간 범위 (기본값: "week")
                    - "day": 하루 이내
                    - "week": 일주일 이내  
                    - "month": 한 달 이내
                    - "year": 일년 이내
                max_results: 반환할 최대 뉴스 수 (기본값: 5)

            Returns:
                dict: 뉴스 검색 결과
                    - success: 성공 여부
                    - query: 원본 검색 쿼리
                    - data: 뉴스 결과 및 통계
                    - search_params: 사용된 검색 파라미터
            """
            try:
                self.logger.info(f"뉴스 검색 시작: {query}")

                # 뉴스 특화 검색 실행 (고급 검색 + 뉴스 토픽)
                results = await self.tavily_api.search(
                    query=query,
                    search_depth="advanced",  # 뉴스는 고급 검색 사용
                    max_results=max_results,
                    topic="news",  # 뉴스 토픽으로 필터링
                    time_range=time_range,
                )

                # 뉴스 검색 결과 반환
                return self.create_standard_response(
                    success=True,
                    query=query,
                    data={"results": results, "total_results": len(results)},
                    search_params={
                        "time_range": time_range,
                        "max_results": max_results,
                    },
                )

            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error("search_news", e, query=query)

        @self.mcp.tool
        async def search_finance(
            query: str,
            max_results: int = 10,
            topic: Literal["finance"] = "finance",
            search_depth: Literal["basic", "advanced"] = "advanced",
            time_range: Literal["day", "week", "month", "year"] | None = "week",
            start_date: str | None = None,
            end_date: str | None = None,
        ) -> dict[str, Any]:
            """
            최신 금융 정보를 검색합니다.
            
            TavilySearchAPI 를 통해 실시간 금융 검색을 수행하며,
            다양한 필터링 옵션을 제공합니다.
            
            Args:
                query: 검색할 키워드 또는 질문
                max_results: 반환할 최대 결과 수 (기본값: 10)
                topic: 검색 주제 필터 ("finance")
                search_depth: 검색 깊이 ("basic": 빠른 검색, "advanced": 상세 검색)
                time_range: 검색할 시간 범위 ("day", "week", "month", "year")
                start_date: 시작 날짜 (YYYY-MM-DD 형식)
                end_date: 종료 날짜 (YYYY-MM-DD 형식)
            """
            try:
                self.logger.info(f"금융 검색 시작: {query}")
                
                # 금융 특화 검색 실행 (고급 검색 + 금융 토픽)
                results = await self.tavily_api.search(
                    query=query,
                    search_depth=search_depth,
                    max_results=max_results,
                    topic=topic,
                    time_range=time_range,
                    start_date=start_date,
                    end_date=end_date,
                )

                return self.create_standard_response(
                    success=True,
                    query=query,
                    data={"results": results, "total_count": len(results)},
                    search_params={
                        "time_range": time_range,
                    },
                )

            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error("search_finance", e, query=query)

def create_app() -> Any:
    server = TavilySearchServer()
    return server.create_app()
