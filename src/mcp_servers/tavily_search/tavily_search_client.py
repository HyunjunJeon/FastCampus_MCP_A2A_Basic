"""
Tavily 검색 API 시뮬레이션 및 도구
"""

import os
import logging
from typing import List, Any, Literal, cast

# 환경 변수 검증 시스템 사용
try:
    from src.utils.env_validator import get_optional_env
except ImportError:
    # Fallback for standalone usage
    def get_optional_env(key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


logger = logging.getLogger(__name__)


class TavilySearchAPI:
    """
    Tavily 검색 API 클라이언트

    Tavily AI의 실시간 웹 검색 API를 활용하여 최신 정보를 검색하는 클라이언트입니다.
    뉴스, 일반 검색, 금융 정보 등 다양한 주제의 검색을 지원하며,
    시간 범위, 도메인 필터링 등의 고급 검색 옵션을 제공합니다.
    """

    def __init__(self, api_key: str | None = None):
        """
        TavilySearchAPI 클라이언트 초기화

        환경변수 또는 직접 전달된 API 키를 사용하여 클라이언트를 초기화합니다.
        API 키가 없으면 기본값 "INSERT_YOUR_API_KEY"를 사용합니다.

        Args:
            api_key: Tavily API 키 (None일 경우 환경변수에서 읽음)
        """
        self.api_key = api_key or get_optional_env(
            "TAVILY_API_KEY", "INSERT_YOUR_API_KEY"
        )

        # API 키 검증 경고
        if self.api_key == "INSERT_YOUR_API_KEY":
            logger.warning(
                "Tavily API key not set. Please set TAVILY_API_KEY environment variable."
            )

    async def search(
        self,
        query: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        max_results: int = 5,
        topic: Literal["general", "news", "finance"] | None = None,
        time_range: Literal["day", "week", "month", "year"] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int | None = None,
        include_domains: List[str] | None = None,
        exclude_domains: List[str] | None = None,
    ) -> dict[str, Any]:
        """
        Tavily Search API를 활용한 웹 검색

        실시간 웹 검색을 수행하여 최신 정보를 가져옵니다.
        다양한 필터링 옵션을 통해 정확하고 관련성 높은 결과를 제공합니다.

        Args:
            query: 검색할 키워드 또는 질문
            search_depth: 검색 깊이
                - "basic": 빠른 검색, 기본적인 결과
                - "advanced": 상세 검색, 더 많은 정보와 분석
            max_results: 반환할 최대 결과 수 (1-100 범위)
            topic: 검색 주제 필터
                - "general": 일반적인 웹 검색
                - "news": 뉴스 및 시사 정보
                - "finance": 금융 및 경제 정보
            time_range: 검색할 시간 범위
                - "day": 최근 하루
                - "week": 최근 일주일
                - "month": 최근 한 달
                - "year": 최근 일년
            start_date: 검색 시작 날짜 (YYYY-MM-DD 형식)
            end_date: 검색 종료 날짜 (YYYY-MM-DD 형식)
            days: 최근 며칠 이내의 결과만 검색 (정수)
            include_domains: 포함할 도메인 리스트
                예: ["wikipedia.org", "github.com"]
            exclude_domains: 제외할 도메인 리스트
                예: ["ads.com", "spam.com"]

        Returns:
            List[Dict[str, Any]]: 검색 결과 리스트
                각 결과는 다음 필드를 포함:
                - title: 페이지 제목
                - url: 페이지 URL
                - content: 페이지 내용 요약
                - score: 관련성 점수
                - published_date: 발행 날짜 (있는 경우)

        Raises:
            Exception: API 호출 실패 또는 네트워크 오류 시
        """
        from tavily import TavilyClient

        # Tavily 클라이언트 초기화
        client = TavilyClient(api_key=self.api_key)

        # 기본 검색 파라미터 구성
        search_params = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }

        search_params["topic"] = topic or "general"
        search_params["time_range"] = time_range or None
        search_params["start_date"] = start_date or None
        search_params["end_date"] = end_date or None
        search_params["days"] = days or None
        search_params["include_domains"] = include_domains or None
        search_params["exclude_domains"] = exclude_domains or None

        # Tavily API 호출 및 결과 반환
        results = client.search(**search_params)
        return cast(dict[str, Any], results)
