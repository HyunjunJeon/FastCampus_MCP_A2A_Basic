"""HR API 서버 모듈.

이 모듈은 직원 정보를 제공하는 간단한 FastAPI REST API를
구현합니다. Auth0를 통한 인증이 필요합니다.

엔드포인트:
    - GET /employees/{id}: 직원 정보 조회

인증:
    - Auth0 JWT 토큰 검증
    - 필수 스코프: read:employee
"""
import os

from fastapi import Depends, FastAPI
from fastapi_plugin import Auth0FastAPI


# Auth0 인증 설정
auth0 = Auth0FastAPI(
    domain=os.getenv('HR_AUTH0_DOMAIN'),
    audience=os.getenv('HR_API_AUTH0_AUDIENCE'),
)

app = FastAPI()


@app.get('/employees/{id}')
def get_employee(
    id: str, _claims: dict = Depends(auth0.require_auth(scopes='read:employee'))
) -> dict[str, str]:
    """직원 정보를 조회합니다.

    인증된 요청에 대해 직원 ID를 반환합니다.
    실제 구현에서는 더 많은 직원 정보를 반환할 수 있습니다.

    Args:
        id: 직원 식별자.
        _claims: Auth0 JWT 클레임 (의존성 주입).

    Returns:
        dict: 직원 정보 (employee_id 포함).
    """
    # TODO: 필요 시 더 많은 직원 정보 반환
    return {'employee_id': id}


# 모듈 수준 API 인스턴스 내보내기
hr_api = app
