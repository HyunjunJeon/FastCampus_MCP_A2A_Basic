"""HR 에이전트 OAuth2 인증 서버 진입점.

이 모듈은 OAuth2 인증이 적용된 HR(인사) 에이전트 서버를 실행합니다.
직원 재직 상태 확인 등 민감한 정보에 대한 인증된 접근을 제공합니다.

아키텍처:
    두 개의 서버가 동시에 실행됩니다:
    1. A2A 에이전트 서버 (port_agent): OAuth2 미들웨어로 보호
    2. HR API 서버 (port_api): 실제 직원 데이터 API

인증 흐름:
    1. 클라이언트가 Auth0에서 액세스 토큰 획득
    2. Bearer 토큰으로 에이전트 서버에 요청
    3. OAuth2Middleware가 토큰 검증 및 스코프 확인
    4. 인증 성공 시 에이전트가 요청 처리

실행 방법:
    python -m headless_agent_auth --host 0.0.0.0 --port_agent 10050 --port_api 10051

서버 포트:
    - 에이전트 서버: 10050 (기본값)
    - HR API 서버: 10051 (기본값)

필수 환경 변수:
    - HR_AUTH0_DOMAIN: Auth0 도메인
    - HR_AGENT_AUTH0_CLIENT_ID: 에이전트 클라이언트 ID
    - HR_AGENT_AUTH0_CLIENT_SECRET: 에이전트 클라이언트 시크릿

OAuth2 스코프:
    - read:employee_status: 직원 재직 상태 확인 권한
"""
import asyncio
import json
import logging
import os
import sys

import click
import uvicorn

from dotenv import load_dotenv


load_dotenv()

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentAuthentication,
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent import HRAgent
from agent_executor import HRAgentExecutor
from api import hr_api
from oauth2_middleware import OAuth2Middleware


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


@click.command()
@click.option('--host', default='0.0.0.0')
@click.option('--port_agent', default=10050)
@click.option('--port_api', default=10051)
def main(host: str, port_agent: int, port_api: int) -> None:
    """HR 에이전트 및 API 서버를 시작합니다.

    두 개의 서버를 동시에 실행합니다:
    - A2A 에이전트 서버: OAuth2 인증이 적용된 HR 에이전트
    - HR API 서버: 직원 정보 조회 API

    Args:
        host: 서버 바인딩 호스트 주소.
        port_agent: 에이전트 서버 포트 번호.
        port_api: HR API 서버 포트 번호.
    """
    async def run_all() -> None:
        """두 서버를 비동기로 동시 실행합니다."""
        await asyncio.gather(
            start_agent(host, port_agent),
            start_api(host, port_api),
        )

    asyncio.run(run_all())


async def start_agent(host: str, port: int) -> None:
    """A2A 에이전트 서버를 시작합니다.

    OAuth2 미들웨어가 적용된 HR 에이전트 서버를 실행합니다.
    AgentCard에 인증 요구사항이 정의되어 있습니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    # AgentCard 설정 (인증 정보 포함)
    agent_card = AgentCard(
        name='Staff0 HR Agent',
        description='This agent handles external verification requests about Staff0 employees made by third parties.',
        url=f'http://{host}:{port}/',
        version='0.1.0',
        default_input_modes=HRAgent.SUPPORTED_CONTENT_TYPES,
        default_output_modes=HRAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id='is_active_employee',
                name='Check Employment Status Tool',
                description='Confirm whether a person is an active employee of the company.',
                tags=['employment status'],
                examples=[
                    'Does John Doe with email jdoe@staff0.com work at Staff0?'
                ],
            )
        ],
        # OAuth2 인증 설정
        authentication=AgentAuthentication(
            schemes=['oauth2'],
            credentials=json.dumps(
                {
                    'tokenUrl': f'https://{os.getenv("HR_AUTH0_DOMAIN")}/oauth/token',
                    'scopes': {
                        'read:employee_status': 'Allows confirming whether a person is an active employee of the company.'
                    },
                }
            ),
        ),
    )

    # 요청 핸들러 설정
    request_handler = DefaultRequestHandler(
        agent_executor=HRAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # A2A 서버 애플리케이션 생성
    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )

    # OAuth2 미들웨어 추가
    app = server.build()
    app.add_middleware(
        OAuth2Middleware,
        agent_card=agent_card,
        public_paths=['/.well-known/agent.json'],  # AgentCard는 공개 접근 허용
    )

    logger.info(f'Starting HR Agent server on {host}:{port}')
    await uvicorn.Server(uvicorn.Config(app=app, host=host, port=port)).serve()


async def start_api(host: str, port: int) -> None:
    """HR API 서버를 시작합니다.

    직원 정보를 제공하는 REST API 서버를 실행합니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    logger.info(f'Starting HR API server on {host}:{port}')
    await uvicorn.Server(
        uvicorn.Config(app=hr_api, host=host, port=port)
    ).serve()


# `uv run .` 사용 시 main() 실행 보장
if not hasattr(sys, '_called_from_uvicorn'):
    main()
