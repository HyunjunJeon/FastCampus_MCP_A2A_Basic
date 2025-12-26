"""OAuth2 인증 미들웨어 모듈.

이 모듈은 A2A 에이전트 서버에 OAuth2 Bearer 토큰 인증을
적용하는 Starlette 미들웨어를 구현합니다.

주요 기능:
    - AgentCard의 인증 요구사항 자동 파싱
    - Bearer 토큰 검증
    - 스코프 기반 권한 확인
    - 공개 경로 예외 처리

인증 흐름:
    1. AgentCard에서 인증 스키마 및 필수 스코프 추출
    2. 요청의 Authorization 헤더에서 Bearer 토큰 추출
    3. Auth0 API로 토큰 검증
    4. 토큰의 스코프가 필수 스코프를 포함하는지 확인
    5. 검증 실패 시 401/403 응답 반환
"""
import json
import os

from a2a.types import AgentCard
from auth0_api_python import ApiClient, ApiClientOptions
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse


# Auth0 API 클라이언트 초기화
api_client = ApiClient(
    ApiClientOptions(
        domain=os.getenv('HR_AUTH0_DOMAIN'),
        audience=os.getenv('HR_AGENT_AUTH0_AUDIENCE'),
    )
)


class OAuth2Middleware(BaseHTTPMiddleware):
    """OAuth2 Bearer 토큰 인증 미들웨어.

    A2A 에이전트 서버에 OAuth2 인증을 적용합니다.
    AgentCard의 인증 요구사항을 기반으로 토큰을 검증합니다.

    Attributes:
        agent_card: 에이전트 카드 (인증 요구사항 포함).
        public_paths: 인증 없이 접근 가능한 경로 집합.
        a2a_auth: 인증 설정 (필수 스코프 등).
    """

    def __init__(
        self,
        app: Starlette,
        agent_card: AgentCard = None,
        public_paths: list[str] = None,
    ) -> None:
        """OAuth2Middleware 인스턴스를 초기화합니다.

        AgentCard에서 인증 요구사항을 파싱하여 설정합니다.

        Args:
            app: Starlette 애플리케이션 인스턴스.
            agent_card: 에이전트 카드 (인증 정보 포함).
            public_paths: 공개 접근 허용 경로 목록.
        """
        super().__init__(app)
        self.agent_card = agent_card
        self.public_paths = set(public_paths or [])

        # AgentCard에서 인증 요구사항 추출
        # 데모를 위해 앱 상태에 저장
        self.a2a_auth = {}

        # Authentication 객체 처리
        if agent_card.authentication:
            credentials = json.loads(
                agent_card.authentication.credentials or '{}'
            )
            if 'scopes' in credentials:
                self.a2a_auth = {
                    'required_scopes': credentials['scopes'].keys()
                }

    async def dispatch(self, request: Request, call_next):
        """요청을 처리하고 인증을 검증합니다.

        공개 경로이거나 인증 요구사항이 없으면 바로 통과합니다.
        그 외의 경우 Bearer 토큰을 검증합니다.

        Args:
            request: HTTP 요청.
            call_next: 다음 미들웨어/핸들러 호출 함수.

        Returns:
            Response: HTTP 응답.
        """
        path = request.url.path

        # 공개 경로 및 익명 접근 허용
        if path in self.public_paths or not self.a2a_auth:
            return await call_next(request)

        # 요청 인증
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return self._unauthorized(
                'Missing or malformed Authorization header.', request
            )

        access_token = auth_header.split('Bearer ')[1]

        try:
            if self.a2a_auth:
                # 토큰 검증
                payload = await api_client.verify_access_token(
                    access_token=access_token
                )
                # 스코프 확인
                scopes = payload.get('scope', '').split()
                missing_scopes = [
                    s
                    for s in self.a2a_auth['required_scopes']
                    if s not in scopes
                ]
                if missing_scopes:
                    return self._forbidden(
                        f'Missing required scopes: {missing_scopes}', request
                    )

        except Exception as e:
            return self._forbidden(f'Authentication failed: {e}', request)

        return await call_next(request)

    def _forbidden(self, reason: str, request: Request):
        """403 Forbidden 응답을 반환합니다.

        SSE 요청인 경우 text/event-stream 형식으로 응답합니다.

        Args:
            reason: 거부 사유.
            request: HTTP 요청.

        Returns:
            Response: 403 응답.
        """
        accept_header = request.headers.get('accept', '')
        if 'text/event-stream' in accept_header:
            return PlainTextResponse(
                f'error forbidden: {reason}',
                status_code=403,
                media_type='text/event-stream',
            )
        return JSONResponse(
            {'error': 'forbidden', 'reason': reason}, status_code=403
        )

    def _unauthorized(self, reason: str, request: Request):
        """401 Unauthorized 응답을 반환합니다.

        SSE 요청인 경우 text/event-stream 형식으로 응답합니다.

        Args:
            reason: 인증 실패 사유.
            request: HTTP 요청.

        Returns:
            Response: 401 응답.
        """
        accept_header = request.headers.get('accept', '')
        if 'text/event-stream' in accept_header:
            return PlainTextResponse(
                f'error unauthorized: {reason}',
                status_code=401,
                media_type='text/event-stream',
            )
        return JSONResponse(
            {'error': 'unauthorized', 'reason': reason}, status_code=401
        )
