"""날씨 에이전트 서버 진입점.

이 모듈은 Google ADK와 MCP를 사용하여 날씨 정보를 제공하는
A2A 에이전트 서버를 실행합니다.

아키텍처:
    - Google ADK LlmAgent로 날씨 쿼리 처리
    - MCP 도구를 통해 NWS API 접근
    - A2A 프로토콜을 통한 스트리밍 응답 지원

서버 포트:
    기본 포트: 10001

필수 환경 변수:
    - GOOGLE_API_KEY: Google AI API 키 (Vertex AI 미사용 시)
    - LITELLM_MODEL: 사용할 LiteLLM 모델 이름 (기본: gemini-2.5-flash)
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
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from weather_executor import (
    WeatherExecutor,
)

from weather_agent import (
    create_weather_agent,
)


load_dotenv()

logging.basicConfig()

DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 10001


def main(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """날씨 에이전트 서버를 시작합니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    # API 키 설정 확인
    # Vertex AI API 사용 시에는 필요 없음
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI') != 'TRUE' and not os.getenv(
        'GOOGLE_API_KEY'
    ):
        raise ValueError(
            'GOOGLE_API_KEY environment variable not set and '
            'GOOGLE_GENAI_USE_VERTEXAI is not TRUE.'
        )

    skill = AgentSkill(
        id='weather_search',
        name='Search weather',
        description='Helps with weather in city, or states',
        tags=['weather'],
        examples=['weather in LA, CA'],
    )

    app_url = os.environ.get('APP_URL', f'http://{host}:{port}')

    agent_card = AgentCard(
        name='Weather Agent',
        description='Helps with weather',
        url=app_url,
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    adk_agent = create_weather_agent()
    runner = Runner(
        app_name=agent_card.name,
        agent=adk_agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )
    agent_executor = WeatherExecutor(runner, agent_card)

    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )

    uvicorn.run(a2a_app.build(), host=host, port=port)


@click.command()
@click.option('--host', 'host', default=DEFAULT_HOST)
@click.option('--port', 'port', default=DEFAULT_PORT)
def cli(host: str, port: int):
    main(host, port)


if __name__ == '__main__':
    main()
