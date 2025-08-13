"""
**DO NOT UPDATE THIS FILE. ONLY HUMAN CAN UPDATE THIS FILE.**
MCP 서버들의 공통 베이스 클래스.
이 모듈은 모든 MCP 서버가 상속받아 사용할 수 있는 기본 클래스를 제공합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from fastmcp.server.http import StarletteWithLifespan
from pydantic import BaseModel, Field, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse
import time
import os
from redis import asyncio as aioredis
from fastmcp.server.middleware import Middleware, MiddlewareContext


class StandardResponse(BaseModel):
    """표준화된 MCP Server 응답 모델"""

    model_config = ConfigDict(extra="allow")  # 추가 필드 허용

    success: bool = Field(..., description="성공 여부")
    query: str = Field(..., description="원본 쿼리")
    data: Any | None = Field(None, description="응답 데이터 (성공 시)")
    error: str | None = Field(None, description="에러 메시지 (실패 시)")


class ErrorResponse(BaseModel):
    """표준 에러 MCP Server 응답 모델"""

    model_config = ConfigDict(extra="allow")

    success: bool = Field(False, description="성공 여부 (항상 False)")
    query: str = Field(..., description="원본 쿼리")
    error: str = Field(..., description="에러 메시지")
    func_name: str | None = Field(None, description="에러가 발생한 함수명")


class BaseMCPServer(ABC):
    """MCP 서버의 베이스 클래스"""

    MCP_PATH = "/mcp/"

    def __init__(
        self,
        server_name: str,
        debug: bool = False,
        transport: Literal["streamable-http", "stdio"] = "streamable-http",
        server_instructions: str = "",
        json_response: bool = False,
    ):
        """
        MCP 서버 초기화

        Args:
            server_name: 서버 이름
            port: 서버 포트
            host: 호스트 주소 (기본값: "0.0.0.0")
            debug: 디버그 모드 (기본값: False)
            transport: MCP 전송 방식 (기본값: "streamable-http")
            server_instructions: 서버 설명 (기본값: "")
            json_response: JSON 응답 검증 여부 (기본값: False)
        """
        from fastmcp import FastMCP

        self.debug = debug
        self.transport = transport
        self.server_instructions = server_instructions
        self.json_response = json_response

        # FastMCP 인스턴스 생성
        self.mcp = FastMCP(name=server_name, instructions=server_instructions)

        # 로거 설정
        self.logger = logging.getLogger(self.__class__.__name__)

        # 클라이언트 초기화
        self._initialize_clients()

        # 도구 등록
        self._register_tools()

        # 필수 미들웨어 기본 추가
        self._install_core_middlewares()

    @abstractmethod
    def _initialize_clients(self) -> None:
        """클라이언트 인스턴스를 초기화합니다. 하위 클래스에서 구현해야 합니다."""
        pass

    @abstractmethod
    def _register_tools(self) -> None:
        """MCP 도구들을 등록합니다. 하위 클래스에서 구현해야 합니다."""
        pass

    def create_standard_response(
        self,
        success: bool,
        query: str,
        data: Any = None,
        error: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        표준화된 응답 형식을 생성합니다.

        Args:
            success: 성공 여부
            query: 원본 쿼리
            data: 응답 데이터
            error: 에러 메시지 (실패 시)
            **kwargs: 추가 필드

        Returns:
            표준화된 응답 딕셔너리 (JSON 직렬화 가능)
        """

        response_model = StandardResponse(
            success=success, query=query, data=data, error=error, **kwargs
        )

        return response_model.model_dump(exclude_none=True)

    async def handle_error(
        self, func_name: str, error: Exception, **context
    ) -> dict[str, Any]:
        """
        표준화된 에러 처리

        Args:
            func_name: 함수 이름
            error: 발생한 예외
            **context: 에러 컨텍스트 정보

        Returns:
            에러 응답 딕셔너리
        """
        self.logger.error(f"{func_name} error: {error}", exc_info=True)

        # 에러 응답 데이터 구성
        error_model = ErrorResponse(
            success=False,
            query=context.get("query", ""),
            error=str(error),
            func_name=func_name,
            **{k: v for k, v in context.items() if k != "query"},
        )

        return error_model.model_dump(exclude_none=True)

    def create_app(self) -> StarletteWithLifespan:
        """
        ASGI 앱을 생성합니다.
        - /health 라우트를 1회만 등록합니다.
        - FastMCP의 http_app을 반환합니다.
        """
        if not getattr(self, "_health_route_registered", False):
            @self.mcp.custom_route(path="/health", methods=["GET"], include_in_schema=True)
            async def health_check(request: Request) -> JSONResponse:
                response_data = self.create_standard_response(
                    success=True,
                    query="MCP Server Health check",
                    data="OK",
                )
                return JSONResponse(content=response_data)
            setattr(self, "_health_route_registered", True)

        return self.mcp.http_app(
            path=self.MCP_PATH,
            json_response=self.json_response,
        )

    # -------------------------
    # Core Middlewares
    # -------------------------
    def _install_core_middlewares(self) -> None:
        """필수 코어 미들웨어 설치 (에러 처리, 로깅, 타이밍, 레이트리밋)."""
        self.mcp.add_middleware(self.ErrorHandlingMiddleware())
        self.mcp.add_middleware(self.RateLimitingMiddleware.from_env())
        self.mcp.add_middleware(self.TimingMiddleware())
        self.mcp.add_middleware(self.LoggingMiddleware())

    class ErrorHandlingMiddleware(Middleware):
        async def on_call_tool(self, context: MiddlewareContext, call_next):
            try:
                return await call_next()
            except Exception as error:  # noqa: BLE001
                # 표준화된 에러 응답 형태로 변환을 시도
                try:
                    server = context.fastmcp_context.fastmcp
                    logger = getattr(server, "logger", None)
                    if logger:
                        logger.error(f"Tool error: {error}", exc_info=True)
                except Exception:
                    pass
                # FastMCP는 예외를 전파해도 클라이언트에 적절히 전달됨
                raise

    class TimingMiddleware(Middleware):
        async def on_call_tool(self, context: MiddlewareContext, call_next):
            start = time.perf_counter()
            try:
                return await call_next()
            finally:
                duration_ms = (time.perf_counter() - start) * 1000.0
                try:
                    context.fastmcp_context.set_state("duration_ms", duration_ms)
                except Exception:
                    pass

    class LoggingMiddleware(Middleware):
        async def on_call_tool(self, context: MiddlewareContext, call_next):
            try:
                server = context.fastmcp_context.fastmcp
                logger = getattr(server, "logger", None)
                if logger:
                    meta = {
                        "request_id": getattr(context.fastmcp_context, "request_id", None),
                        "client_id": getattr(context.fastmcp_context, "client_id", None),
                        "session_id": getattr(context.fastmcp_context, "session_id", None),
                    }
                    logger.info(f"Tool call start: {meta}")
                result = await call_next()
                if logger:
                    duration_ms = context.fastmcp_context.get_state("duration_ms")
                    logger.info(f"Tool call end: duration_ms={duration_ms}")
                return result
            except Exception:
                raise

    class RateLimitingMiddleware(Middleware):
        """간단한 Redis 기반 레이트 리밋 (슬라이딩 윈도우/고정 윈도우 혼합).

        환경 변수:
          - REDIS_URL: redis 접속 URL (기본: redis://redis:6379/0)
          - MCP_RATE_LIMIT_RPS: 초당 최대 요청 수 (기본: 50)
          - MCP_RATE_LIMIT_BURST: 버스트 허용량 (기본: RPS)
        """

        def __init__(self, redis_url: str, rps: int = 50, burst: int | None = None):
            self.redis_url = redis_url
            self.rps = max(1, int(rps))
            self.burst = int(burst) if burst is not None else self.rps
            self._pool = None

        @classmethod
        def from_env(cls) -> "BaseMCPServer.RateLimitingMiddleware":
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            rps = int(os.getenv("MCP_RATE_LIMIT_RPS", "50"))
            burst = os.getenv("MCP_RATE_LIMIT_BURST")
            burst_i = int(burst) if burst is not None else None
            return cls(redis_url=redis_url, rps=rps, burst=burst_i)

        async def _acquire(self):
            if self._pool is None:
                self._pool = await aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            return self._pool

        async def on_call_tool(self, context: MiddlewareContext, call_next):
            try:
                redis = await self._acquire()

                # 키: 초 단위 고정 윈도우 + 버스트 토큰 관리
                now = int(time.time())
                key_counter = f"mcp:rate:cnt:{now}"
                key_tokens = "mcp:rate:tokens"

                pipe = redis.pipeline()
                pipe.incr(key_counter, 1)
                pipe.expire(key_counter, 2)
                current, _ = await pipe.execute()

                # 카운터 기반 즉시 차단
                if int(current) > (self.rps + self.burst):
                    raise RuntimeError("Rate limit exceeded")

                # 간단 토큰 버킷: 매 초 rps 만큼 토큰 충전, 최대 burst 유지
                async with redis.pipeline(transaction=True) as p:
                    await p.watch(key_tokens)
                    tokens = await redis.get(key_tokens)
                    tokens = int(tokens) if tokens is not None else self.burst
                    # 충전
                    tokens = min(self.burst, tokens + self.rps)
                    if tokens <= 0:
                        await p.unwatch()
                        raise RuntimeError("Rate limit exceeded")
                    # 1 토큰 사용
                    tokens -= 1
                    p.multi()
                    p.set(key_tokens, tokens, ex=2)
                    await p.execute()

                return await call_next()
            except Exception:
                raise



"""
**DO NOT UPDATE THIS FILE. ONLY HUMAN CAN UPDATE THIS FILE.**
"""
