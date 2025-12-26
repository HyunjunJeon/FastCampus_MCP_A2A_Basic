"""차트 생성 에이전트 서버 진입점.

이 모듈은 CSV 형식의 데이터를 기반으로 막대 차트를 생성하는
A2A 에이전트 서버를 초기화하고 실행합니다. CrewAI 프레임워크를
사용하여 데이터 시각화 전문가 역할의 에이전트를 구현합니다.

실행 방법:
    python -m analytics --host localhost --port 10011

서버 포트:
    기본 포트: 10011

주요 기능:
    - CSV 형식 데이터에서 막대 차트 이미지 생성
    - matplotlib을 통한 시각화
    - 이미지를 PNG 형식의 Base64로 인코딩하여 반환

Note:
    스트리밍은 지원하지 않습니다 (capabilities.streaming=False).
"""
import logging

import click

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent import ChartGenerationAgent
from agent_executor import ChartGenerationAgentExecutor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10011)
def main(host: str, port: int) -> None:
    """A2A 차트 생성 에이전트 서버를 시작합니다.

    CrewAI 프레임워크를 사용하여 CSV 데이터를 막대 차트로 변환하는
    에이전트 서버를 실행합니다. 생성된 차트는 PNG 이미지로 반환됩니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    try:
        # 에이전트 기능 설정 (스트리밍 비활성화)
        capabilities = AgentCapabilities(streaming=False)

        # 차트 생성 스킬 정의
        skill = AgentSkill(
            id='chart_generator',
            name='Chart Generator',
            description='Generate a chart based on CSV-like data passed in',
            tags=['generate image', 'edit image'],
            examples=[
                'Generate a chart of revenue: Jan,$1000 Feb,$2000 Mar,$1500'
            ],
        )

        # AgentCard 설정
        # 입력/출력 모드에 이미지 타입을 포함 (text, text/plain, image/png)
        agent_card = AgentCard(
            name='Chart Generator Agent',
            description='Generate charts from structured CSV-like data input.',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            default_input_modes=ChartGenerationAgent.SUPPORTED_CONTENT_TYPES,
            default_output_modes=ChartGenerationAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # 요청 핸들러 설정
        request_handler = DefaultRequestHandler(
            agent_executor=ChartGenerationAgentExecutor(),
            task_store=InMemoryTaskStore(),
        )

        # A2A 서버 애플리케이션 생성 및 실행
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        import uvicorn

        uvicorn.run(server.build(), host=host, port=port)

    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        exit(1)


if __name__ == '__main__':
    main()
