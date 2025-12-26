"""GitHub 에이전트 서버 진입점.

이 모듈은 GitHub API를 사용하여 저장소 정보, 커밋 히스토리,
프로젝트 활동을 조회하는 A2A 에이전트 서버를 실행합니다.
OpenRouter API를 통해 Claude 3.5 Sonnet 모델을 사용합니다.

실행 방법:
    python -m github-agent --host localhost --port 10007

필수 환경 변수:
    - OPENROUTER_API_KEY: OpenRouter API 키
    - GITHUB_TOKEN: GitHub API 토큰 (선택사항, 없으면 제한된 속도로 동작)

서버 포트:
    기본 포트: 10007

주요 기능:
    - 사용자 저장소 목록 조회
    - 특정 저장소의 최근 커밋 조회
    - 활발한 저장소 검색
"""
import logging
import os

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv
from openai_agent import create_agent  # type: ignore[import-not-found]
from openai_agent_executor import (
    OpenAIAgentExecutor,  # type: ignore[import-untyped]
)
from starlette.applications import Starlette


load_dotenv()

logging.basicConfig()


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10007)
def main(host: str, port: int) -> None:
    """GitHub 에이전트 서버를 시작합니다.

    OpenRouter API를 통해 Claude 모델을 사용하여 GitHub 저장소 정보를
    조회하는 에이전트를 실행합니다. PyGithub 라이브러리를 통해 GitHub API와
    연동합니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.

    Raises:
        ValueError: OPENROUTER_API_KEY 환경 변수가 설정되지 않은 경우.
    """
    # API 키 검증
    if not os.getenv('OPENROUTER_API_KEY'):
        raise ValueError('OPENROUTER_API_KEY environment variable not set')

    # 에이전트 스킬 정의
    # GitHub 저장소 관련 기능을 설명합니다
    skill = AgentSkill(
        id='github_repositories',
        name='GitHub Repositories',
        description='Query GitHub repositories, recent updates, commits, and project activity',
        tags=['github', 'repositories', 'commits'],
        examples=[
            'Show my recent repository updates',
            'What are the latest commits in my project?',
            'Search for popular Python repositories with recent activity',
        ],
    )

    # OpenAI 기반 에이전트를 위한 AgentCard 설정
    agent_card = AgentCard(
        name='GitHub Agent',
        description='An agent that can query GitHub repositories and recent project updates',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    # OpenAI 에이전트 생성
    # create_agent()는 도구 세트와 시스템 프롬프트를 반환합니다
    agent_data = create_agent()

    # AgentExecutor 초기화
    # OpenRouter를 통해 Claude 3.5 Sonnet 모델 사용
    agent_executor = OpenAIAgentExecutor(
        card=agent_card,
        tools=agent_data['tools'],
        api_key=os.getenv('OPENROUTER_API_KEY'),
        system_prompt=agent_data['system_prompt'],
    )

    # 요청 핸들러 설정
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    # A2A 서버 애플리케이션 생성
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    routes = a2a_app.routes()

    # Starlette 애플리케이션으로 래핑하여 실행
    app = Starlette(routes=routes)

    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    main()
