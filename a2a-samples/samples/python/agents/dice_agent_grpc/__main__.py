"""주사위 에이전트 gRPC 서버 진입점.

이 모듈은 gRPC 전송 프로토콜을 사용하는 A2A 주사위 에이전트 서버를 실행합니다.
gRPC 서버와 별도의 HTTP 서버(AgentCard 제공용)를 동시에 실행합니다.

아키텍처:
    gRPC 서버는 /.well-known/agent.json 경로를 직접 제공할 수 없습니다.
    따라서 클라이언트가 에이전트를 발견할 수 있도록 별도의 HTTP 서버에서
    공개 AgentCard를 제공합니다.

주요 기능:
    - gRPC 기반 A2A 프로토콜 지원
    - 스트리밍 응답 지원
    - gRPC 리플렉션 활성화 (디버깅/테스트용)
    - 우아한 종료(Graceful shutdown) 지원

실행 방법:
    python -m dice_agent_grpc --host localhost --port 11001 --agent-card-port 11000

환경 변수:
    GOOGLE_API_KEY: Google API 키 (Vertex AI 미사용 시 필수)
    GOOGLE_GENAI_USE_VERTEXAI: 'TRUE'로 설정 시 Vertex AI API 사용

포트:
    - gRPC 서버: 11001 (기본값)
    - AgentCard HTTP 서버: 11000 (기본값)
"""
import asyncio
import logging
import os
import signal

import asyncclick as click
import grpc
import uvicorn

from a2a.grpc import a2a_pb2, a2a_pb2_grpc
from a2a.server.request_handlers import DefaultRequestHandler, GrpcHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TransportProtocol,
)
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from agent_executor import DiceAgentExecutor  # type: ignore[import-untyped]
from dotenv import load_dotenv
from grpc_reflection.v1alpha import reflection
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


load_dotenv()

logging.basicConfig(level=logging.INFO)


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--agent-card-port', 'agent_card_port', default=11000)
@click.option('--port', 'port', default=11001)
async def main(host: str, port: int, agent_card_port: int) -> None:
    """gRPC 기반 주사위 에이전트 서버를 시작합니다.

    gRPC 서버와 AgentCard용 HTTP 서버를 동시에 실행합니다.
    SIGINT/SIGTERM 시그널을 처리하여 우아한 종료를 지원합니다.

    Args:
        host: 서버가 바인딩할 호스트 주소. 기본값은 'localhost'.
        port: gRPC 서버 포트 번호. 기본값은 11001.
        agent_card_port: AgentCard HTTP 서버 포트 번호. 기본값은 11000.

    Raises:
        ValueError: GOOGLE_API_KEY가 설정되지 않고 Vertex AI도 사용하지 않는 경우.
    """
    # API 키 확인: Vertex AI를 사용하지 않는 경우 GOOGLE_API_KEY 필수
    if os.getenv('GOOGLE_GENAI_USE_VERTEXAI') != 'TRUE' and not os.getenv(
        'GOOGLE_API_KEY'
    ):
        raise ValueError(  # noqa: TRY003
            'GOOGLE_API_KEY environment variable not set and '
            'GOOGLE_GENAI_USE_VERTEXAI is not TRUE.'
        )

    agent_card = get_agent_card(host, port)

    # gRPC 서버 생성
    grpc_server = await create_grpc_server(agent_card, host, port)

    # gRPC 서버는 well-known URL에서 공개 AgentCard를 제공할 수 없습니다.
    # 클라이언트가 gRPC 엔드포인트를 발견할 수 있도록 별도의 HTTP 서버에서
    # 공개 AgentCard를 제공합니다.

    # AgentCard 제공용 HTTP 서버 생성
    http_server = create_agent_card_server(agent_card, host, agent_card_port)

    loop = asyncio.get_running_loop()

    async def shutdown(sig: signal.Signals) -> None:
        """서버들을 우아하게 종료합니다.

        Args:
            sig: 수신된 시그널 (SIGINT 또는 SIGTERM).
        """
        logging.warning(f'종료 시그널 수신: {sig.name}...')
        # Uvicorn 서버 종료
        http_server.should_exit = True

        await grpc_server.stop(5)
        logging.warning('서버들이 중지되었습니다.')

    # SIGINT, SIGTERM 시그널 핸들러 등록
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    await grpc_server.start()

    # HTTP 서버와 gRPC 서버를 동시에 실행
    await asyncio.gather(http_server.serve(), grpc_server.wait_for_termination())


def create_agent_card_server(agent_card: AgentCard, host: str, agent_card_port: int) -> uvicorn.Server:
    """AgentCard 제공용 Starlette 앱을 생성합니다.

    gRPC 서버는 HTTP 경로를 직접 처리할 수 없으므로,
    /.well-known/agent.json 경로에서 AgentCard를 제공하기 위한
    별도의 HTTP 서버를 생성합니다.

    Args:
        agent_card: 제공할 AgentCard 인스턴스.
        host: 서버가 바인딩할 호스트 주소.
        agent_card_port: HTTP 서버 포트 번호.

    Returns:
        uvicorn.Server: 설정된 uvicorn 서버 인스턴스.
    """
    def get_agent_card_http(request: Request) -> Response:
        """AgentCard를 JSON 형식으로 반환하는 엔드포인트."""
        return JSONResponse(
            agent_card.model_dump(mode='json', exclude_none=True)
        )

    routes = [
        Route(AGENT_CARD_WELL_KNOWN_PATH, endpoint=get_agent_card_http)
    ]
    app = Starlette(routes=routes)

    # AgentCard용 uvicorn 서버 생성
    config = uvicorn.Config(
        app,
        host=host,
        port=agent_card_port,
        log_config=None,
    )
    logging.info(f'HTTP 서버 시작: 포트 {agent_card_port}')
    return uvicorn.Server(config)


async def create_grpc_server(agent_card: AgentCard, host: str, port: int) -> grpc.aio.Server:
    """gRPC 서버를 생성합니다.

    A2A 프로토콜을 처리하는 gRPC 서버를 생성하고,
    리플렉션을 활성화하여 grpcurl 등의 도구로 테스트할 수 있게 합니다.

    Args:
        agent_card: 에이전트 카드 인스턴스.
        host: 서버가 바인딩할 호스트 주소.
        port: gRPC 서버 포트 번호.

    Returns:
        grpc.aio.Server: 설정된 비동기 gRPC 서버 인스턴스.
    """
    agent_executor = DiceAgentExecutor()
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    server = grpc.aio.server()
    a2a_pb2_grpc.add_A2AServiceServicer_to_server(
        GrpcHandler(agent_card, request_handler),
        server,
    )

    # gRPC 리플렉션 활성화 (grpcurl 등 도구에서 서비스 검색 가능)
    SERVICE_NAMES = (
        a2a_pb2.DESCRIPTOR.services_by_name['A2AService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    server.add_insecure_port(f'{host}:{port}')
    logging.info(f'gRPC 서버 시작: 포트 {port}')
    return server


def get_agent_card(host: str, port: int) -> AgentCard:
    """에이전트 카드를 생성하여 반환합니다.

    gRPC 전송 프로토콜을 선호하는 에이전트 카드를 생성합니다.
    인증된 확장 카드 지원이 활성화되어 있습니다.

    Args:
        host: 에이전트 서버 호스트 주소.
        port: gRPC 서버 포트 번호.

    Returns:
        AgentCard: 구성된 에이전트 카드 인스턴스.
    """
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

    return AgentCard(
        name='Dice Agent',
        description='An agent that can roll arbitrary dice and answer if numbers are prime',
        url=f'{host}:{port}',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        supports_authenticated_extended_card=True,
        skills=skills,
        preferred_transport=TransportProtocol.grpc,  # gRPC 전송 프로토콜 선호
    )



if __name__ == '__main__':
    main(_anyio_backend='asyncio')
