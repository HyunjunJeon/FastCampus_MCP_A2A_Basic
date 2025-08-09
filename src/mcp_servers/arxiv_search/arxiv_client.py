import logging
from typing import Any
import asyncio
import arxiv

logger = logging.getLogger(__name__)


class ArxivClient:
    """
    arXiv API 클라이언트 - arxiv 라이브러리 활용
    
    arXiv.org의 공식 Python 라이브러리를 활용하여 학술 논문을 검색하고
    메타데이터를 추출하는 클라이언트입니다. 동기 라이브러리를 비동기로 래핑하여
    non-blocking 방식으로 동작하도록 구현되었습니다.
    """
    
    def __init__(self):
        """
        ArxivClient 초기화
        
        arxiv 라이브러리는 동기 라이브러리이므로 별도의 초기화가 불필요합니다.
        모든 API 호출은 asyncio.to_thread를 통해 비동기로 처리됩니다.
        """
        pass
    
    async def search_papers(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
        category: str | None = None
    ) -> list[dict[str, Any]]:
        """
        arXiv에서 논문 검색
        
        키워드, 저자명, 제목 등을 기반으로 arXiv 데이터베이스를 검색하여
        관련 논문들의 메타데이터와 초록을 가져옵니다.
        
        Args:
            query: 검색할 키워드나 구문
                - 키워드 검색: "machine learning"
                - 저자 검색: "au:Yann LeCun"  
                - 제목 검색: "ti:attention mechanism"
                - 복합 검색: "machine learning AND deep learning"
            max_results: 반환할 최대 논문 수 (1-100)
            sort_by: 정렬 기준
                - "relevance": 관련성 순
                - "lastUpdatedDate": 최신 업데이트 순
                - "submittedDate": 최초 제출일 순
            category: 특정 카테고리로 필터링 (선택사항)
                - "cs.AI": 인공지능
                - "cs.LG": 기계학습
                - "cs.CV": 컴퓨터 비전
                - "cs.CL": 자연어처리
                - "stat.ML": 통계 기계학습
        
        Returns:
            list[dict]: 논문 정보 리스트, 각 논문은 다음 필드 포함:
                - title: 논문 제목
                - authors: 저자 리스트 (문자열 배열)
                - summary: 논문 초록
                - published: 발행일 (YYYY-MM-DD 형식)
                - arxiv_id: arXiv ID
                - pdf_url: PDF 다운로드 URL
                - categories: 카테고리 리스트
                - url: arXiv 페이지 URL
                - comment: 저자 코멘트 (있는 경우)
                - journal_ref: 저널 참조 (있는 경우)  
                - doi: DOI (있는 경우)
        
        Raises:
            Exception: arXiv API 호출 실패 또는 네트워크 오류
        """
        try:
            # 검색 쿼리 구성 - 카테고리 필터 적용
            search_query = query
            if category:
                search_query = f"cat:{category} AND {query}"
            
            # 정렬 기준 매핑 (문자열 -> arxiv.SortCriterion 열거형)
            sort_criterion = {
                "relevance": arxiv.SortCriterion.Relevance,
                "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
                "submittedDate": arxiv.SortCriterion.SubmittedDate
            }.get(sort_by, arxiv.SortCriterion.Relevance)
            
            # 동기 함수를 비동기로 실행 (블로킹 방지)
            papers = await asyncio.to_thread(
                self._search_papers_sync,
                search_query,
                max_results,
                sort_criterion
            )
            
            return papers
            
        except Exception as e:
            logger.error(f"arXiv 검색 오류: {e}")
            return []  # 오류 발생 시 빈 리스트 반환
    
    def _search_papers_sync(
        self,
        query: str,
        max_results: int,
        sort_criterion: arxiv.SortCriterion
    ) -> list[dict[str, Any]]:
        """
        동기적으로 arXiv 논문 검색 (내부 헬퍼 메서드)
        
        실제 arxiv 라이브러리를 사용하여 검색을 수행하고
        결과를 표준화된 딕셔너리 형태로 변환합니다.
        
        Args:
            query: 처리된 검색 쿼리 (카테고리 필터 포함)
            max_results: 최대 결과 수
            sort_criterion: arxiv.SortCriterion 열거형
        
        Returns:
            list[dict]: 표준화된 논문 정보 리스트
        """
        papers: list[dict[str, Any]] = []
        
        # arXiv 검색 객체 생성
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending  # 내림차순 정렬
        )
        
        # 검색 결과 처리
        for result in search.results():
            # 날짜 포맷팅 (datetime -> YYYY-MM-DD 문자열)
            published = result.published.strftime("%Y-%m-%d") if result.published else ""
            
            # 선택적 속성 안전하게 추출
            categories = result.categories if hasattr(result, 'categories') else []
            pdf_url = result.pdf_url if hasattr(result, 'pdf_url') else ""
            
            # arXiv ID 추출 (URL에서 ID 부분만 분리)
            arxiv_id = result.entry_id.split('/')[-1] if result.entry_id else ""
            
            # 표준화된 논문 정보 딕셔너리 생성
            papers.append({
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary,
                "published": published,
                "arxiv_id": arxiv_id,
                "pdf_url": pdf_url,
                "categories": categories,
                "url": result.entry_id,
                "comment": result.comment if hasattr(result, 'comment') else None,
                "journal_ref": result.journal_ref if hasattr(result, 'journal_ref') else None,
                "doi": result.doi if hasattr(result, 'doi') else None
            })
        
        return papers
    
    async def get_paper_by_id(self, arxiv_id: str) -> dict[str, Any] | None:
        """
        arXiv ID로 특정 논문의 상세 정보 조회
        
        정확한 arXiv ID를 사용하여 특정 논문의 전체 메타데이터를
        조회합니다. ID 기반 검색이므로 빠르고 정확합니다.
        
        Args:
            arxiv_id: arXiv 논문의 고유 식별자
                - 새 형식: "YYMM.NNNNN" (예: "2301.00001")
                - 구 형식: "subject-class/YYMMnnn" (예: "cs/0601001")
        
        Returns:
            dict | None: 논문 정보 딕셔너리 (찾을 수 없으면 None)
                반환 형식은 search_papers()와 동일:
                - title, authors, summary, published, arxiv_id
                - pdf_url, categories, url, comment, journal_ref, doi
        
        Raises:
            Exception: API 호출 실패 또는 네트워크 오류
        """
        try:
            # ID로 직접 검색 (비동기 처리)
            paper = await asyncio.to_thread(
                self._get_paper_by_id_sync,
                arxiv_id
            )
            return paper
        except Exception as e:
            logger.error(f"arXiv 논문 조회 오류 (ID: {arxiv_id}): {e}")
            return None
    
    def _get_paper_by_id_sync(self, arxiv_id: str) -> dict[str, Any] | None:
        """
        동기적으로 arXiv ID로 논문 조회 (내부 헬퍼 메서드)
        
        ID 리스트를 사용한 직접 검색으로 특정 논문의 정보를 가져옵니다.
        
        Args:
            arxiv_id: arXiv 논문 ID
        
        Returns:
            dict | None: 논문 정보 또는 None (찾을 수 없는 경우)
        """
        # ID 리스트를 사용한 직접 검색
        search = arxiv.Search(id_list=[arxiv_id])
        
        # 첫 번째 (유일한) 결과 처리
        for result in search.results():
            # 날짜 및 선택적 속성 처리
            published = result.published.strftime("%Y-%m-%d") if result.published else ""
            categories = result.categories if hasattr(result, 'categories') else []
            pdf_url = result.pdf_url if hasattr(result, 'pdf_url') else ""
            
            # 표준화된 논문 정보 반환
            return {
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary,
                "published": published,
                "arxiv_id": arxiv_id,  # 원본 ID 사용
                "pdf_url": pdf_url,
                "categories": categories,
                "url": result.entry_id,
                "comment": result.comment if hasattr(result, 'comment') else None,
                "journal_ref": result.journal_ref if hasattr(result, 'journal_ref') else None,
                "doi": result.doi if hasattr(result, 'doi') else None
            }
        
        # 검색 결과가 없는 경우
        return None
    
    async def close(self):
        """
        클라이언트 정리 (클린업)
        
        arxiv 라이브러리는 상태를 유지하지 않는 stateless 라이브러리이므로
        특별한 정리 작업이 필요하지 않습니다. 인터페이스 일관성을 위해 제공됩니다.
        """
        pass  # arxiv 라이브러리는 특별한 클린업이 불필요