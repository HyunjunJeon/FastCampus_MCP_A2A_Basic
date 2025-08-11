"""Serper를 이용한 Google 검색 MCP 서버"""

from typing import Any

from mcp_servers.base_mcp_server import BaseMCPServer
from mcp_servers.serper_search.serper_dev_client import SerperClient
from starlette.requests import Request
from starlette.responses import JSONResponse


class SerperSearchServer(BaseMCPServer):
    """
    Serper를 이용한 Google 검색 MCP 서버
    
    Serper.dev API를 활용하여 Google 검색 결과를 가져오는 MCP 서버입니다.
    웹 검색, 뉴스 검색, 이미지 검색 등 다양한 Google 검색 기능을 제공하며,
    국가별, 언어별 검색 결과를 지원합니다.
    """
    
    def __init__(self):
        """
        SerperSearchServer 초기화
        
        환경변수에서 포트를 읽어 Serper 검색 MCP 서버를 초기화합니다.
        Docker 환경에서는 PORT 환경변수를, 로컬에서는 기본 포트 3002를 사용합니다.
        """
        import os
        port = int(os.getenv("PORT", 3002))  # Docker Compose에서 설정한 포트 사용
        super().__init__(
            server_name="Serper Google Search Server",
            port=port,
            json_response=False
        )
        
    def _initialize_clients(self) -> None:
        """
        SerperClient 인스턴스 초기화
        
        Serper.dev API와 통신하는 클라이언트 인스턴스를 생성합니다.
        이 클라이언트는 Google 검색 API 호출과 결과 파싱을 담당합니다.
        """
        self.serper_client = SerperClient()
    
    async def _on_shutdown(self) -> None:
        """
        서버 종료 시 클라이언트 정리
        
        서버 종료 시 SerperClient의 HTTP 클라이언트 연결을 안전하게 종료하고
        리소스를 해제하여 메모리 누수를 방지합니다.
        """
        await self.serper_client.close()
    
    def _register_tools(self) -> None:
        """
        MCP 도구 등록
        
        Google 검색, 뉴스 검색, 이미지 검색 도구를 MCP 서버에 등록합니다.
        각 도구는 비동기로 구현되어 동시 요청 처리가 가능합니다.
        """
        
        @self.mcp.tool
        async def search_google(
            query: str,
            num_results: int = 10,
            search_type: str = "search",
            country: str = "kr",
            language: str = "ko"
        ) -> dict[str, Any]:
            """
            Serper.dev를 통해 Google 검색을 수행합니다.
            
            Google의 실시간 검색 결과를 가져와 구조화된 형태로 반환합니다.
            일반 웹 검색, 이미지, 비디오, 뉴스 검색을 지원합니다.
            
            Args:
                query: 검색할 키워드 또는 질문
                    예: "파이썬 튜토리얼", "최신 AI 기술", "서울 날씨"
                num_results: 반환할 검색 결과 수 (기본값: 10, 최대 100)
                search_type: 검색 타입
                    - "search": 일반 웹 검색 (기본값)
                    - "images": 이미지 검색
                    - "videos": 비디오 검색  
                    - "news": 뉴스 검색
                country: 검색 대상 국가 (ISO 3166-1 alpha-2 코드)
                    - "kr": 한국 (기본값)
                    - "us": 미국
                    - "jp": 일본
                    - "cn": 중국
                language: 검색 결과 언어 (ISO 639-1 코드)
                    - "ko": 한국어 (기본값)
                    - "en": 영어
                    - "ja": 일본어
                    - "zh": 중국어
            
            Returns:
                dict: Google 검색 결과
                    - success: 검색 성공 여부
                    - query: 원본 검색 쿼리
                    - search_type: 검색 타입
                    - total_results: 총 결과 수
                    - organic_results: 일반 검색 결과 리스트
                    - news_results: 뉴스 결과 리스트 (해당되는 경우)
                    - answer_box: 답변 박스 (있는 경우)
                    - knowledge_graph: 지식 그래프 (있는 경우)
            """
            try:
                self.logger.info(f"Google 검색 시작: {query}")
                
                # SerperClient를 통한 Google 검색 실행
                result = await self.serper_client.search(
                    query=query,
                    search_type=search_type,
                    num_results=num_results,
                    country=country,
                    language=language
                )
                
                # SerperClient가 이미 표준 응답 형식을 반환하므로 그대로 사용
                return result
                
            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error(
                    "search_google",
                    e,
                    query=query
                )
        
        @self.mcp.tool
        async def search_google_news(
            query: str,
            num_results: int = 10,
            country: str = "kr",
            language: str = "ko"
        ) -> dict[str, Any]:
            """
            Google 뉴스 검색을 수행합니다.
            
            Google 뉴스에서 최신 뉴스 기사를 검색하여 제목, 요약, 
            게시일, 출처 등의 정보를 제공합니다.
            
            Args:
                query: 검색할 뉴스 키워드
                    예: "대통령", "경제 뉴스", "코로나 바이러스"
                num_results: 반환할 뉴스 기사 수 (기본값: 10)
                country: 뉴스 검색 대상 국가 (기본값: "kr")
                language: 뉴스 언어 설정 (기본값: "ko")
            
            Returns:
                dict: Google 뉴스 검색 결과
                    - success: 검색 성공 여부
                    - query: 원본 검색 쿼리
                    - data.news_results: 뉴스 기사 리스트
                        각 기사는 다음 필드 포함:
                        - title: 기사 제목
                        - link: 기사 URL
                        - snippet: 기사 요약
                        - date: 게시일
                        - source: 뉴스 출처
                        - image_url: 대표 이미지 URL (있는 경우)
                    - data.total_results: 총 뉴스 기사 수
            """
            try:
                self.logger.info(f"Google 뉴스 검색 시작: {query}")
                
                # 뉴스 타입으로 검색 실행
                result = await self.serper_client.search(
                    query=query,
                    search_type="news",  # 뉴스 검색 타입 지정
                    num_results=num_results,
                    country=country,
                    language=language
                )
                
                # 뉴스 특화 결과 처리 및 반환
                if result.get("success"):
                    news_results = result.get("news_results", [])
                    return self.create_standard_response(
                        success=True,
                        query=query,
                        data={
                            "news_results": news_results,
                            "total_results": len(news_results)
                        }
                    )
                else:
                    # 검색 실패 시 원본 결과 반환
                    return result
                    
            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error(
                    "search_google_news",
                    e,
                    query=query
                )
        
        @self.mcp.tool
        async def search_google_images(
            query: str,
            num_results: int = 10,
            country: str = "kr",
            language: str = "ko"
        ) -> dict[str, Any]:
            """
            Google 이미지 검색을 수행합니다.
            
            Google 이미지 검색을 통해 관련 이미지들의 URL, 제목,
            출처 정보 등을 가져옵니다.
            
            Args:
                query: 검색할 이미지 키워드
                    예: "고양이", "서울 풍경", "파이썬 로고"
                num_results: 반환할 이미지 수 (기본값: 10)
                country: 이미지 검색 대상 국가 (기본값: "kr")
                language: 검색 언어 설정 (기본값: "ko")
            
            Returns:
                dict: Google 이미지 검색 결과
                    - success: 검색 성공 여부
                    - query: 원본 검색 쿼리
                    - search_type: "images"
                    - total_results: 총 이미지 수
                    - organic_results: 이미지 결과 리스트
                        각 이미지는 다음 필드 포함:
                        - title: 이미지 제목/설명
                        - link: 이미지 직접 URL
                        - snippet: 이미지 설명
                        - source: 이미지 출처 사이트
                        - thumbnail: 썸네일 URL
            """
            try:
                self.logger.info(f"Google 이미지 검색 시작: {query}")
                
                # 이미지 타입으로 검색 실행
                result = await self.serper_client.search(
                    query=query,
                    search_type="images",  # 이미지 검색 타입 지정
                    num_results=num_results,
                    country=country,
                    language=language
                )
                
                # 이미지 검색 결과 반환
                return result
                
            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error(
                    "search_google_images",
                    e,
                    query=query
                )

def create_app() -> Any:
    server = SerperSearchServer()
    return server.create_app()
