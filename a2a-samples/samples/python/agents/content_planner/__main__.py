"""콘텐츠 플래너 에이전트 서버 진입점.

이 모듈은 Google ADK(Agent Development Kit)와 Gemini 모델을 사용하여
콘텐츠 개요를 생성하는 A2A 에이전트 서버를 실행합니다.

실행 방법:
    python -m content_planner --host localhost --port 10001

서버 포트:
    기본 포트: 10001

주요 기능:
    - 고수준 콘텐츠 설명에서 상세하고 논리적인 개요 생성
    - Google Search 도구를 활용한 정보 수집
    - 스트리밍 응답 지원
"""
import logging

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
from content_planner_agent import root_agent as content_planner_agent
from agent_executor import ADKAgentExecutor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """API 키 누락 예외.

    필수 API 키가 설정되지 않은 경우 발생합니다.
    """


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10001)
def main(host: str, port: int) -> None:
    """콘텐츠 플래너 에이전트 서버를 시작합니다.

    Google ADK와 Gemini 모델을 사용하여 콘텐츠 개요를 생성하는
    에이전트 서버를 실행합니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    # AgentCard 설정 (에이전트 메타데이터)
    # description은 ADK 에이전트에서 가져옴
    agent_card = AgentCard(
        name='Content Planner Agent',
        description=content_planner_agent.description,
        url=f'http://{host}:{port}',
        version="1.0.0",
        defaultInputModes=["text", "text/plain"],
        defaultOutputModes=["text", "text/plain"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            AgentSkill(
                id="content_planner",
                name="Creates outlines for content",
                description="Creates outlines for content given a high-level description of the content",
                tags=["plan", "outline"],
                examples=[
                    "Create an outline for a short, upbeat, and encouraging X post about learning Java",
                ],
            )
        ],
    )

    # 요청 핸들러 설정
    # ADKAgentExecutor가 ADK 에이전트를 A2A 프로토콜과 연결합니다
    request_handler = DefaultRequestHandler(
        agent_executor=ADKAgentExecutor(
            agent=content_planner_agent,
        ),
        task_store=InMemoryTaskStore(),
    )

    # A2A 서버 애플리케이션 생성 및 실행
    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )

    uvicorn.run(server.build(), host=host, port=port)


if __name__ == "__main__":
    main()
