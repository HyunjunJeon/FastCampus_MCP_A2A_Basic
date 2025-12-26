"""주사위 에이전트 REST 서버 진입점.

이 모듈은 주사위 굴리기와 소수 판별 기능을 제공하는 A2A REST 에이전트 서버를 실행합니다.
A2ARESTFastAPIApplication을 사용하여 HTTP/JSON 기반 A2A 프로토콜을 지원합니다.

주요 기능:
    - N면 주사위 굴리기 (기본값: 6면)
    - 숫자 목록에서 소수 판별
    - HTTP/JSON 전송 프로토콜 (JSONRPC 대신)
    - 스트리밍 응답 지원

실행 방법:
    python -m dice_agent_rest --host localhost --port 10101

환경 변수:
    GOOGLE_API_KEY: Google API 키 (Vertex AI 미사용 시 필수)
    GOOGLE_GENAI_USE_VERTEXAI: 'TRUE'로 설정 시 Vertex AI API 사용

서버 포트:
    기본 포트: 10101
"""
import logging
import os

import click
import uvicorn

from a2a.server.apps import A2ARESTFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TransportProtocol,
)
from agent_executor import DiceAgentExecutor  # type: ignore[import-untyped]
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig()


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10101)
def main(host: str, port: int) -> None:
    """주사위 에이전트 REST 서버를 시작합니다.

    FastAPI 기반 A2A REST 애플리케이션을 생성하고 uvicorn으로 실행합니다.
    HTTP/JSON 전송 프로토콜을 사용하여 JSONRPC 대신 일반 REST API 형태로
    A2A 프로토콜을 제공합니다.

    Args:
        host: 서버가 바인딩할 호스트 주소. 기본값은 'localhost'.
        port: 서버가 리스닝할 포트 번호. 기본값은 10101.

    Raises:
        ValueError: GOOGLE_API_KEY가 설정되지 않고 Vertex AI도 사용하지 않는 경우.
    """
    # API 키 확인: Vertex AI를 사용하지 않는 경우 GOOGLE_API_KEY 필수
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI') != 'TRUE' and not os.getenv(
        'GOOGLE_API_KEY'
    ):
        raise ValueError(
            'GOOGLE_API_KEY environment variable not set and '
            'GOOGLE_GENAI_USE_VERTEXAI is not TRUE.'
        )

    # 에이전트 스킬 정의
    skills = [
        # 스킬 1: 주사위 굴리기
        AgentSkill(
            id='f56cab88-3fe9-47ec-ba6e-86a13c9f1f74',
            name='Roll Dice',
            description='Rolls an N sided dice and returns the result. By default uses a 6 sided dice.',
            tags=['dice'],
            examples=['Can you roll an 11 sided dice?'],
        ),
        # 스킬 2: 소수 판별
        AgentSkill(
            id='33856129-d686-4a54-9c6e-fffffec3561b',
            name='Prime Detector',
            description='Determines which numbers from a list are prime numbers.',
            tags=['prime'],
            examples=['Which of these are prime numbers 1, 4, 6, 7'],
        ),
    ]

    # AgentCard 설정: HTTP/JSON 전송 프로토콜 사용
    agent_card = AgentCard(
        name='Dice Agent',
        description='An agent that can roll arbitrary dice and answer if numbers are prime',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=skills,
        preferred_transport=TransportProtocol.http_json,  # REST API 형태로 제공
    )

    # 에이전트 실행자 및 요청 핸들러 설정
    agent_executor = DiceAgentExecutor()
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    # REST FastAPI 애플리케이션 생성 (JSONRPC 대신 HTTP/JSON 사용)
    server = A2ARESTFastAPIApplication(
        agent_card=agent_card, http_handler=request_handler
    )

    # uvicorn으로 서버 실행
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == '__main__':
    main()
