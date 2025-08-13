"""
HTTP 클라이언트 최적화 모듈

Connection Pooling과 리소스 관리를 위한 최적화된 HTTP 클라이언트를 제공합니다.

주요 기능:
- Connection Pooling으로 성능 향상
- 자동 재시도 및 백오프
- 타임아웃 관리
- 리소스 정리
"""

from typing import Optional, Dict, Any, Union
from contextlib import asynccontextmanager
import httpx
from httpx import AsyncClient, Limits, Timeout

from src.utils.logging_config import get_logger
from src.utils.error_handler import retry_on_error, ExternalAPIError

logger = get_logger(__name__)


class OptimizedHTTPClient:
    """
    최적화된 HTTP 클라이언트

    Connection Pooling과 효율적인 리소스 관리를 제공하는
    싱글톤 패턴 기반 HTTP 클라이언트입니다.
    """

    _instance: Optional["OptimizedHTTPClient"] = None
    _clients: Dict[str, AsyncClient] = {}

    def __new__(cls):
        """싱글톤 패턴 구현"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """HTTP 클라이언트 초기화"""
        if not hasattr(self, "initialized"):
            # Connection Pool 설정
            self.default_limits = Limits(
                max_keepalive_connections=10,  # Keep-alive 연결 수
                max_connections=100,  # 최대 동시 연결 수
                keepalive_expiry=30.0,  # Keep-alive 만료 시간
            )

            # 기본 타임아웃 설정
            self.default_timeout = Timeout(
                connect=5.0,  # 연결 타임아웃
                read=30.0,  # 읽기 타임아웃
                write=10.0,  # 쓰기 타임아웃
                pool=5.0,  # 연결 풀 대기 타임아웃
            )

            self.initialized = True

    def get_client(
        self,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[Timeout] = None,
        limits: Optional[Limits] = None,
        client_id: Optional[str] = None,
    ) -> AsyncClient:
        """
        HTTP 클라이언트 인스턴스 가져오기

        Args:
            base_url: 기본 URL
            headers: 기본 헤더
            timeout: 타임아웃 설정
            limits: 연결 제한 설정
            client_id: 클라이언트 식별자 (재사용을 위한)

        Returns:
            AsyncClient 인스턴스
        """
        # 클라이언트 ID 생성
        if client_id is None:
            client_id = base_url or "default"

        # 기존 클라이언트 재사용
        if client_id in self._clients:
            return self._clients[client_id]

        # 새 클라이언트 생성
        common_kwargs = dict(
            headers=headers or {},
            timeout=timeout or self.default_timeout,
            limits=limits or self.default_limits,
            follow_redirects=True,
            http2=False,
        )
        if isinstance(base_url, str) and base_url:
            client = AsyncClient(base_url=base_url, **common_kwargs)
        else:
            # base_url이 None/빈 문자열이면 전달하지 않음 (httpx가 None을 허용하지 않음)
            client = AsyncClient(**common_kwargs)

        # 클라이언트 저장
        self._clients[client_id] = client

        logger.debug(f"Created new HTTP client: {client_id}")
        return client

    @asynccontextmanager
    async def session(
        self,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """
        컨텍스트 매니저로 HTTP 세션 관리

        Usage:
            async with http_client.session("http://api.example.com") as client:
                response = await client.get("/endpoint")
        """
        client = None
        try:
            client = AsyncClient(
                base_url=base_url,
                headers=headers or {},
                timeout=self.default_timeout,
                limits=self.default_limits,
                **kwargs,
            )
            yield client
        finally:
            if client:
                await client.aclose()

    async def close_client(self, client_id: str):
        """
        특정 클라이언트 종료

        Args:
            client_id: 클라이언트 식별자
        """
        if client_id in self._clients:
            await self._clients[client_id].aclose()
            del self._clients[client_id]
            logger.debug(f"Closed HTTP client: {client_id}")

    async def close_all(self):
        """모든 클라이언트 종료"""
        for client_id in list(self._clients.keys()):
            await self.close_client(client_id)
        logger.info("Closed all HTTP clients")

    @retry_on_error(
        max_attempts=3,
        delay=1.0,
        backoff=2.0,
        exceptions=(httpx.NetworkError, httpx.TimeoutException),
    )
    async def request(
        self, method: str, url: str, client_id: Optional[str] = None, **kwargs
    ) -> httpx.Response:
        """
        HTTP 요청 실행 (자동 재시도 포함)

        Args:
            method: HTTP 메서드 (GET, POST 등)
            url: 요청 URL
            client_id: 클라이언트 식별자
            **kwargs: 추가 요청 파라미터

        Returns:
            HTTP 응답

        Raises:
            ExternalAPIError: API 호출 실패
        """
        # 동일 호스트로의 요청은 하나의 커넥션 풀을 최대한 재사용하도록 client_id를 호스트 기준으로 설정
        import urllib.parse as _up
        try:
            parsed = _up.urlparse(url)
            host_id = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else url
        except Exception:
            host_id = url

        client = self.get_client(client_id=client_id or host_id)

        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            raise ExternalAPIError(
                message=f"HTTP {e.response.status_code} error",
                api_name=url,
                status_code=e.response.status_code,
                cause=e,
            )
        except httpx.RequestError as e:
            raise ExternalAPIError(
                message=f"Request failed: {str(e)}", api_name=url, cause=e
            )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET 요청"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST 요청"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """PUT 요청"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """DELETE 요청"""
        return await self.request("DELETE", url, **kwargs)

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.close_all()


# 글로벌 HTTP 클라이언트 인스턴스
http_client = OptimizedHTTPClient()


class APIClientBase:
    """
    API 클라이언트 기본 클래스

    외부 API와 통신하는 클라이언트들의 기본 클래스입니다.
    Connection Pooling과 에러 처리를 자동으로 제공합니다.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = 30.0,
    ):
        """
        API 클라이언트 초기화

        Args:
            base_url: API 기본 URL
            api_key: API 키
            headers: 추가 헤더
            timeout: 요청 타임아웃
        """
        self.base_url = base_url
        self.api_key = api_key

        # 헤더 설정
        self.headers = headers or {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        # 타임아웃 설정
        self.timeout = Timeout(connect=5.0, read=timeout, write=10.0, pool=5.0)

        # HTTP 클라이언트 가져오기
        self.client = http_client.get_client(
            base_url=base_url,
            headers=self.headers,
            timeout=self.timeout,
            client_id=self.__class__.__name__,
        )

    async def _request(
        self, method: str, endpoint: str, **kwargs
    ) -> Union[Dict[str, Any], list]:
        """
        API 요청 실행

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            **kwargs: 추가 요청 파라미터

        Returns:
            파싱된 JSON 응답
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        try:
            response = await http_client.request(
                method=method, url=url, headers=self.headers, **kwargs
            )
            return response.json()

        except Exception as e:
            logger.error(f"API request failed: {url} - {e}")
            raise

    async def get(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], list]:
        """GET 요청"""
        return await self._request("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> Union[Dict[str, Any], list]:
        """POST 요청"""
        return await self._request("POST", endpoint, **kwargs)

    async def close(self):
        """클라이언트 종료"""
        await http_client.close_client(self.__class__.__name__)


# 리소스 정리를 위한 종료 핸들러
async def cleanup_http_clients():
    """
    애플리케이션 종료 시 HTTP 클라이언트 정리

    Usage:
        # FastAPI
        @app.on_event("shutdown")
        async def shutdown():
            await cleanup_http_clients()

        # 일반 스크립트
        try:
            asyncio.run(main())
        finally:
            asyncio.run(cleanup_http_clients())
    """
    await http_client.close_all()
    logger.info("HTTP clients cleaned up")


# 성능 모니터링
class HTTPMetrics:
    """HTTP 요청 메트릭 수집"""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.total_duration = 0.0
        self.request_durations = []

    def record_request(self, duration: float, success: bool = True):
        """요청 메트릭 기록"""
        self.request_count += 1
        self.total_duration += duration
        self.request_durations.append(duration)

        if not success:
            self.error_count += 1

        # 메모리 관리 (최근 1000개만 유지)
        if len(self.request_durations) > 1000:
            self.request_durations = self.request_durations[-1000:]

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        if not self.request_durations:
            return {
                "request_count": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_duration": 0.0,
                "min_duration": 0.0,
                "max_duration": 0.0,
            }

        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / self.request_count
            if self.request_count > 0
            else 0.0,
            "avg_duration": self.total_duration / self.request_count
            if self.request_count > 0
            else 0.0,
            "min_duration": min(self.request_durations),
            "max_duration": max(self.request_durations),
        }


# 글로벌 메트릭 인스턴스
http_metrics = HTTPMetrics()
