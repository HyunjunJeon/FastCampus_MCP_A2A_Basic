"""arXiv 논문 검색 MCP 서버"""

from typing import Any

from mcp_servers.base_mcp_server import BaseMCPServer
from mcp_servers.arxiv_search.arxiv_client import ArxivClient


class ArxivSearchServer(BaseMCPServer):
    """
    arXiv 논문 검색 MCP 서버
    
    arXiv.org에서 학술 논문을 검색하고 상세 정보를 제공하는 MCP 서버입니다.
    컴퓨터 과학, 물리학, 수학 등 다양한 분야의 최신 연구 논문을 검색할 수 있습니다.
    """
    
    def __init__(self):
        """
        ArxivSearchServer 초기화
        
        환경변수에서 포트를 읽어 arXiv 검색 MCP 서버를 초기화합니다.
        Docker 환경에서는 PORT 환경변수를, 로컬에서는 기본 포트 3000을 사용합니다.
        """
        import os
        port = int(os.getenv("PORT", 3000))  # Docker Compose에서 설정한 포트 사용
        super().__init__(
            server_name="arXiv Paper Search Server",
            port=port,
            json_response=False
        )
        
    def _initialize_clients(self) -> None:
        """
        ArxivClient 인스턴스 초기화
        
        arXiv API와 통신하는 클라이언트 인스턴스를 생성합니다.
        이 클라이언트는 논문 검색과 상세 정보 조회에 사용됩니다.
        """
        self.arxiv_client = ArxivClient()
    
    async def _on_shutdown(self) -> None:
        """
        서버 종료 시 클라이언트 정리
        
        서버가 종료될 때 ArxivClient 인스턴스를 안전하게 정리합니다.
        열린 연결이나 리소스를 해제하여 메모리 누수를 방지합니다.
        """
        await self.arxiv_client.close()
    
    def _register_tools(self) -> None:
        """
        MCP 도구 등록
        
        arXiv 논문 검색과 상세 정보 조회 도구를 MCP 서버에 등록합니다.
        각 도구는 비동기 함수로 구현되어 non-blocking 방식으로 동작합니다.
        """
        
        @self.mcp.tool
        async def search_arxiv_papers(
            query: str,
            max_results: int = 10,
            sort_by: str = "relevance",
            category: str | None = None
        ) -> dict[str, Any]:
            """
            arXiv에서 논문을 검색합니다.
            
            키워드, 저자명, 제목 등을 기반으로 arXiv 데이터베이스에서
            관련 논문을 검색하고 메타데이터와 요약을 제공합니다.
            
            Args:
                query: 검색할 키워드, 저자명, 또는 제목
                    예: "machine learning", "Yann LeCun", "attention mechanism"
                max_results: 반환할 최대 논문 수 (기본값: 10, 최대 100)
                sort_by: 정렬 방식
                    - "relevance": 관련성 순 (기본값)
                    - "lastUpdatedDate": 최신 업데이트 순
                    - "submittedDate": 최초 제출일 순
                category: arXiv 카테고리 필터 (선택사항)
                    - "cs.AI": 인공지능
                    - "cs.LG": 기계학습
                    - "cs.CV": 컴퓨터 비전
                    - "cs.NI": 자연어처리
                    - "math.ST": 통계학
                    - "physics.data-an": 데이터 분석
            
            Returns:
                dict: 표준화된 검색 결과
                    - success: 검색 성공 여부
                    - query: 원본 검색 쿼리
                    - data: 논문 리스트와 총 개수
                    - search_params: 사용된 검색 파라미터
            """
            try:
                self.logger.info(f"arXiv 논문 검색 시작: {query}")
                
                # ArxivClient를 통한 논문 검색 실행
                papers = await self.arxiv_client.search_papers(
                    query=query,
                    max_results=max_results,
                    sort_by=sort_by,
                    category=category
                )
                
                # 표준화된 응답 형식으로 반환
                return self.create_standard_response(
                    success=True,
                    query=query,
                    data={
                        "papers": papers,
                        "total_results": len(papers)
                    },
                    search_params={
                        "max_results": max_results,
                        "sort_by": sort_by,
                        "category": category
                    }
                )
                
            except Exception as e:
                # 에러 발생 시 표준화된 에러 응답 반환
                return await self.handle_error(
                    "search_arxiv_papers",
                    e,
                    query=query
                )
        
        @self.mcp.tool
        async def get_paper_details(arxiv_id: str) -> dict[str, Any]:
            """
            특정 arXiv 논문의 상세 정보를 가져옵니다.
            
            arXiv ID를 사용하여 특정 논문의 전체 메타데이터,
            초록, 저자 정보, PDF 링크 등을 조회합니다.
            
            Args:
                arxiv_id: arXiv 논문 고유 식별자
                    형식: "YYMM.NNNNN" (예: "2301.00001")
                    또는 "subject-class/YYMMnnn" (구버전 형식)
            
            Returns:
                dict: 논문 상세 정보
                    성공 시:
                    - success: True
                    - query: arXiv ID
                    - data.paper: 논문 상세 정보 딕셔너리
                        - title: 논문 제목
                        - authors: 저자 리스트
                        - summary: 논문 초록
                        - published: 발행일
                        - arxiv_id: arXiv ID
                        - pdf_url: PDF 다운로드 링크
                        - categories: 논문 카테고리 리스트
                        - url: arXiv 페이지 URL
                        - comment: 저자 코멘트 (있는 경우)
                        - journal_ref: 저널 참조 (있는 경우)
                        - doi: DOI (있는 경우)
                    
                    실패 시:
                    - success: False
                    - error: "Paper not found" 또는 기타 오류 메시지
            """
            try:
                self.logger.info(f"arXiv 논문 상세 정보 조회: {arxiv_id}")
                
                # ArxivClient를 통한 논문 상세 정보 조회
                paper = await self.arxiv_client.get_paper_by_id(arxiv_id)
                
                if paper:
                    # 논문을 찾은 경우
                    return self.create_standard_response(
                        success=True,
                        query=arxiv_id,
                        data={"paper": paper}
                    )
                else:
                    # 논문을 찾지 못한 경우
                    return self.create_standard_response(
                        success=False,
                        query=arxiv_id,
                        error="Paper not found"
                    )
                    
            except Exception as e:
                # 예외 발생 시 표준화된 에러 응답 반환
                return await self.handle_error(
                    "get_paper_details",
                    e,
                    arxiv_id=arxiv_id
                )


# 서버 인스턴스 생성 및 실행
if __name__ == "__main__":
    server = ArxivSearchServer()
    server.run()
