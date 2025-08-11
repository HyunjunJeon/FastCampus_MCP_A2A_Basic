"""
**DO NOT UPDATE THIS FILE. ONLY HUMAN CAN UPDATE THIS FILE.**
MCP 서버들의 공통 베이스 클래스.
이 모듈은 모든 MCP 서버가 상속받아 사용할 수 있는 기본 클래스를 제공합니다.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse


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
        port: int,
        host: str = "0.0.0.0",
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

        self.host = host
        self.port = port
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

    def create_app(self) -> Any:
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

        return self.mcp.http_app(path=self.MCP_PATH)



"""
**DO NOT UPDATE THIS FILE. ONLY HUMAN CAN UPDATE THIS FILE.**
"""
