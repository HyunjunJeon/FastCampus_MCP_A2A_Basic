import logging
import os
from typing import Any
from pydantic import BaseModel, Field

# 환경 변수 검증 시스템 사용
try:
    from src.utils.env_validator import get_optional_env
except ImportError:
    # Fallback for standalone usage
    def get_optional_env(key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    """
    개별 검색 결과 모델
    
    Google 검색의 각 개별 결과를 나타내는 Pydantic 모델입니다.
    일반적인 웹 검색 결과의 제목, 링크, 요약 등을 포함합니다.
    """
    title: str | None = None  # 검색 결과 제목
    link: str | None = None   # 검색 결과 URL
    snippet: str | None = None  # 검색 결과 요약/설명
    displayed_link: str | None = Field(None, alias="displayedLink")  # 표시용 링크
    position: int | None = None  # 검색 결과 순위
    source: str = "Google"  # 검색 소스 (기본값: Google)


class NewsResult(BaseModel):
    """
    뉴스 검색 결과 모델
    
    Google 뉴스 검색 결과를 나타내는 Pydantic 모델입니다.
    뉴스 기사의 제목, 링크, 발행일, 출처 등의 정보를 포함합니다.
    """
    title: str | None = None  # 뉴스 기사 제목
    link: str | None = None   # 뉴스 기사 URL
    snippet: str | None = None  # 뉴스 기사 요약
    date: str | None = None   # 뉴스 발행일
    source: str | None = None  # 뉴스 출처 (언론사명)
    image_url: str | None = Field(None, alias="imageUrl")  # 뉴스 대표 이미지 URL


class AnswerBox(BaseModel):
    """
    답변 박스 모델
    
    Google 검색에서 제공하는 직접 답변 박스를 나타내는 모델입니다.
    특정 질문에 대한 간단한 답변이나 정의를 포함합니다.
    """
    title: str | None = None  # 답변 제목
    snippet: str | None = None  # 답변 내용
    link: str | None = None   # 답변 출처 링크
    displayed_link: str | None = Field(None, alias="displayedLink")  # 표시용 링크


class KnowledgeGraph(BaseModel):
    """
    지식 그래프 모델
    
    Google 검색에서 제공하는 지식 그래프 정보를 나타내는 모델입니다.
    인물, 기업, 장소 등에 대한 구조화된 정보를 포함합니다.
    """
    title: str | None = None  # 항목 제목 (인물명, 기업명 등)
    type: str | None = None   # 항목 유형 (Person, Organization 등)
    description: str | None = None  # 항목 설명
    website: str | None = None  # 공식 웹사이트 URL
    image_url: str | None = Field(None, alias="imageUrl")  # 대표 이미지 URL


class SearchInformation(BaseModel):
    """
    검색 정보 모델
    
    Google 검색의 메타 정보를 나타내는 모델입니다.
    검색 결과의 총 개수와 검색 소요 시간을 포함합니다.
    """
    total_results: int = Field(0, alias="totalResults")  # 총 검색 결과 수
    search_time: float = Field(0.0, alias="searchTime")  # 검색 소요 시간 (초)


class FormattedSearchResults(BaseModel):
    """
    포맷된 검색 결과 전체 모델
    
    Serper API로부터 받은 Google 검색 결과를 표준화된 형태로 변환한 
    전체 결과를 나타내는 모델입니다. 모든 검색 유형의 통합 응답 형식을 제공합니다.
    """
    success: bool = True  # 검색 성공 여부
    query: str  # 원본 검색 쿼리
    search_type: str  # 검색 타입 (search, news, images 등)
    total_results: int = 0  # 총 검색 결과 수
    search_time: float = 0.0  # 검색 소요 시간
    organic_results: list[SearchResult] = Field(default_factory=list)  # 일반 검색 결과 리스트
    news_results: list[NewsResult] = Field(default_factory=list)  # 뉴스 검색 결과 리스트
    answer_box: AnswerBox | None = None  # 답변 박스 (있는 경우)
    knowledge_graph: KnowledgeGraph | None = None  # 지식 그래프 (있는 경우)
    error: str | None = None  # 에러 메시지 (실패 시)


class SerperClient:
    """
    Serper.dev Google 검색 API 클라이언트
    
    Serper.dev 서비스를 통해 Google 검색 결과를 가져오는 HTTP 클라이언트입니다.
    API 키가 없는 경우 데모 모드로 동작하며, 실제 API 호출 시에는
    결과를 표준화된 형태로 파싱하여 반환합니다.
    """
    
    def __init__(self):
        """
        SerperClient 초기화
        
        환경변수에서 SERPER_API_KEY를 읽어 클라이언트를 초기화합니다.
        API 키가 없으면 데모 모드로 설정되어 시뮬레이션 결과를 반환합니다.
        """
        # 환경변수에서 API 키 읽기 (검증 시스템 사용)
        self.api_key = get_optional_env("SERPER_API_KEY")
        if not self.api_key:
            logger.warning("SERPER_API_KEY not found. Using demo mode.")
            self.api_key = "demo-key"  # 데모 모드 식별자
        
        # Serper.dev API 기본 URL
        self.base_url = "https://google.serper.dev"
        
        # 비동기 HTTP 클라이언트 초기화 (공통 클라이언트 풀 사용)
        from src.utils.http_client import http_client as _hc
        self.client = _hc.get_client(
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
            client_id="serper_http",
        )
    
    async def search(
        self,
        query: str,
        search_type: str = "search",
        num_results: int = 10,
        country: str = "kr",
        language: str = "ko"
    ) -> dict[str, Any]:
        """
        Google 검색 수행
        
        Serper.dev API를 통해 Google 검색을 실행하고 결과를 표준화된 형태로 반환합니다.
        API 키가 없는 경우 데모 결과를 생성하여 반환합니다.
        
        Args:
            query: 검색할 키워드 또는 질문
            search_type: 검색 타입
                - "search": 일반 웹 검색
                - "news": 뉴스 검색  
                - "images": 이미지 검색
                - "videos": 비디오 검색
            num_results: 반환할 결과 수 (1-100)
            country: 검색 대상 국가 코드 (ISO 3166-1 alpha-2)
            language: 검색 결과 언어 코드 (ISO 639-1)
        
        Returns:
            dict: 표준화된 검색 결과
                - success: 검색 성공 여부
                - query: 원본 검색 쿼리  
                - search_type: 검색 타입
                - total_results: 총 결과 수
                - organic_results: 일반 검색 결과 리스트
                - news_results: 뉴스 결과 리스트
                - answer_box: 답변 박스 (있는 경우)
                - knowledge_graph: 지식 그래프 (있는 경우)
                - error: 에러 메시지 (실패 시)
        """
        
        # 데모 모드 확인 - API 키가 없는 경우
        if self.api_key == "demo-key":
            # 데모 모드: 시뮬레이션 결과 반환
            return self._get_demo_results(query, search_type, num_results)
        
        try:
            # Serper API 엔드포인트 URL 구성
            url = f"{self.base_url}/{search_type}"
            
            # API 요청 페이로드 구성
            payload = {
                "q": query,  # 검색 쿼리
                "num": num_results,  # 결과 수
                "gl": country,  # 지역 설정
                "hl": language   # 언어 설정
            }
            
            # HTTP POST 요청 전송
            response = await self.client.post(url, json=payload)
            response.raise_for_status()  # HTTP 에러 확인
            
            # JSON 응답 파싱
            data = response.json()
            return self._format_results(data, query, search_type)
            
        except Exception as e:
            # 에러 발생 시 표준화된 에러 응답 반환
            logger.error(f"Serper 검색 오류: {e}")
            error_result = FormattedSearchResults(
                success=False,
                query=query,
                search_type=search_type,
                error=str(e)
            )
            return error_result.model_dump(by_alias=True)
    
    def _get_demo_results(
        self, 
        query: str, 
        search_type: str, 
        num_results: int
    ) -> dict[str, Any]:
        """
        데모 모드용 시뮬레이션 결과 생성
        
        API 키가 없을 때 사용되는 데모 결과를 Pydantic 모델을 사용하여 생성합니다.
        실제 검색 결과와 동일한 형태의 구조를 가진 더미 데이터를 반환합니다.
        
        Args:
            query: 검색 쿼리
            search_type: 검색 타입
            num_results: 생성할 결과 수
        
        Returns:
            dict: 데모용 검색 결과
        """
        
        # 데모 검색 결과 생성 (최대 5개까지 제한)
        organic_results = []
        for i in range(min(num_results, 5)):
            demo_result = SearchResult(
                title=f"[Demo] Result {i+1} for: {query}",
                link=f"https://example.com/result{i+1}",
                snippet=f"This is a demo search result about {query}. " * 2,
                displayed_link=f"example.com/result{i+1}",
                position=i + 1,
                source="Demo"
            )
            organic_results.append(demo_result)
        
        # 전체 데모 결과 구성
        demo_results = FormattedSearchResults(
            success=True,
            query=query,
            search_type=search_type,
            total_results=len(organic_results),
            search_time=0.1,  # 데모 검색 시간
            organic_results=organic_results,
            news_results=[],  # 빈 뉴스 결과
            answer_box=None,
            knowledge_graph=None
        )
        
        return demo_results.model_dump(by_alias=True)
    
    def _format_results(
        self, 
        data: dict[str, Any], 
        query: str, 
        search_type: str
    ) -> dict[str, Any]:
        """
        검색 결과 포맷팅
        
        Serper API로부터 받은 원시 JSON 데이터를 표준화된 형태로 변환합니다.
        Pydantic 모델을 사용하여 타입 안전성을 보장하고 일관된 구조를 제공합니다.
        
        Args:
            data: Serper API 원시 응답 데이터
            query: 원본 검색 쿼리
            search_type: 검색 타입
        
        Returns:
            dict: 표준화된 검색 결과
        """
        
        try:
            # 검색 메타 정보 추출
            search_info = data.get("searchInformation", {})
            
            # 일반 검색 결과 파싱
            organic_results = []
            for item in data.get("organic", []):
                search_result = SearchResult.model_validate(item)
                organic_results.append(search_result)
            
            # 뉴스 결과 파싱
            news_results = []
            for item in data.get("news", []):
                news_result = NewsResult.model_validate(item)
                news_results.append(news_result)
            
            # 답변 박스 파싱 (있는 경우)
            answer_box = None
            if data.get("answerBox"):
                answer_box = AnswerBox.model_validate(data["answerBox"])
            
            # 지식 그래프 파싱 (있는 경우)
            knowledge_graph = None
            if data.get("knowledgeGraph"):
                knowledge_graph = KnowledgeGraph.model_validate(data["knowledgeGraph"])
            
            # 전체 결과 구성
            formatted_results = FormattedSearchResults(
                success=True,
                query=query,
                search_type=search_type,
                total_results=search_info.get("totalResults", 0),
                search_time=search_info.get("searchTime", 0.0),
                organic_results=organic_results,
                news_results=news_results,
                answer_box=answer_box,
                knowledge_graph=knowledge_graph
            )
            
            return formatted_results.model_dump(by_alias=True)
            
        except Exception as e:
            # 결과 포맷팅 중 오류 발생 시
            logger.error(f"결과 포맷팅 중 오류 발생: {e}")
            # 오류 발생 시 기본 구조 반환
            error_result = FormattedSearchResults(
                success=False,
                query=query,
                search_type=search_type,
                error=str(e)
            )
            return error_result.model_dump(by_alias=True)
    
    async def close(self):
        """
        HTTP 클라이언트 종료
        
        비동기 HTTP 클라이언트의 연결을 안전하게 종료하고
        관련 리소스를 해제합니다. 서버 종료 시 반드시 호출되어야 합니다.
        """
        try:
            # 공통 풀에서 만든 클라이언트는 전역 정리 루틴으로 닫힌다.
            # 여기서는 안전하게 무시하거나 필요 시 개별 종료를 시도한다.
            await self.client.aclose()
        except Exception:
            pass