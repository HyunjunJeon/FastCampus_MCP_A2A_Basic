"""주사위 에이전트 gRPC 테스트 클라이언트.

이 모듈은 gRPC 기반 주사위 에이전트 서버에 연결하여 테스트하는 클라이언트입니다.
HTTP 서버에서 공개 AgentCard를 조회한 후, gRPC 채널을 통해 메시지를 전송합니다.

주요 기능:
    - HTTP 서버에서 공개 AgentCard 조회
    - gRPC 채널을 통한 인증된 확장 AgentCard 조회
    - 일반 메시지 전송 (send_message)
    - 스트리밍 메시지 전송 (send_message_streaming)

실행 방법:
    python test_client.py --agent-card-url http://localhost:11000
    python test_client.py --grpc-endpoint localhost:11001

사전 조건:
    gRPC 서버(11001)와 HTTP 서버(11000)가 모두 실행 중이어야 합니다.
"""
import logging  # 로깅 모듈 임포트

from uuid import uuid4

import asyncclick as click
import grpc
import httpx

from a2a.client import A2ACardResolver, A2AGrpcClient
from a2a.grpc import a2a_pb2, a2a_pb2_grpc
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    Role,
    TextPart,
)
from a2a.utils import proto_utils


@click.command()
@click.option('--agent-card-url', 'agent_card_url', default='http://localhost:11000')
@click.option('--grpc-endpoint', 'grpc_endpoint', default=None)
async def main(agent_card_url: str, grpc_endpoint: str | None) -> None:
    """gRPC 테스트 클라이언트의 메인 함수.

    공개 AgentCard를 조회하고 gRPC를 통해 에이전트와 통신합니다.
    일반 메시지와 스트리밍 메시지 전송을 모두 테스트합니다.

    Args:
        agent_card_url: AgentCard를 제공하는 HTTP 서버 URL. 기본값: http://localhost:11000
        grpc_endpoint: gRPC 서버 엔드포인트. 지정하지 않으면 AgentCard에서 URL을 가져옵니다.
    """
    # INFO 레벨 메시지를 표시하도록 로깅 설정
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)  # 로거 인스턴스 생성

    if grpc_endpoint is None:
        logger.info('gRPC 엔드포인트가 지정되지 않음. HTTP 서버에서 공개 AgentCard 조회 중')
        # gRPC URL이 지정되지 않으면 공개 AgentCard 조회
        agent_card = await get_public_agent_card(agent_card_url)
        base_url = agent_card.url
    else:
        logger.info('gRPC 엔드포인트가 지정됨. HTTP 서버에서 공개 AgentCard 조회 건너뜀')
        # gRPC 엔드포인트가 지정된 경우
        base_url = grpc_endpoint


    async with grpc.aio.insecure_channel(base_url) as channel:
        stub = a2a_pb2_grpc.A2AServiceStub(channel)

        # gRPC 채널을 사용하여 인증된 AgentCard 조회
        # 실제 애플리케이션에서는 agent_card.supports_authenticated_extended_card 플래그를 확인하여
        # 인증된 카드를 조회해야 하는지 결정합니다.
        # 인증된 AgentCard가 제공되면, gRPC 서비스와 상호작용할 때 이를 사용해야 합니다.
        try:
            if agent_card.supports_authenticated_extended_card:
                logger.info(
                    'gRPC 엔드포인트에서 인증된 AgentCard 조회 시도 중'
                )
                proto_card = await stub.GetAgentCard(a2a_pb2.GetAgentCardRequest())
                logger.info('AgentCard 조회 성공:')
                logger.info(proto_card)
                final_agent_card_to_use = proto_utils.FromProto.agent_card(
                    proto_card
                )
            else:
                final_agent_card_to_use = agent_card
        except Exception:
            logging.exception('인증된 AgentCard 조회 실패. 종료합니다.')
            return


        # A2AGrpcClient 초기화
        client = A2AGrpcClient(stub, agent_card=final_agent_card_to_use)
        logger.info('A2AClient 초기화 완료.')

        # 테스트 메시지 생성: 5면 주사위 굴리기 요청
        request = MessageSendParams(
            message=Message(
                role=Role.user,
                parts=[Part(root=TextPart(text='roll a 5 sided dice'))],
                message_id=str(uuid4()),
            )
        )

        # 일반 메시지 전송 테스트
        response = await client.send_message(request)
        logging.info(response.model_dump(mode='json', exclude_none=True))

        # 스트리밍 메시지 전송 테스트
        stream_response = client.send_message_streaming(request)

        async for chunk in stream_response:
            logging.info(chunk.model_dump(mode='json', exclude_none=True))


async def get_public_agent_card(agent_card_url: str) -> AgentCard:
    """HTTP 서버에서 공개 AgentCard를 조회합니다.

    Args:
        agent_card_url: AgentCard를 제공하는 HTTP 서버의 기본 URL.

    Returns:
        AgentCard: 조회된 공개 AgentCard 인스턴스.

    Raises:
        ValueError: 공개 AgentCard를 찾을 수 없는 경우.
    """
    agent_card: AgentCard | None = None
    async with httpx.AsyncClient() as httpx_client:
        # A2ACardResolver를 사용하여 AgentCard 조회
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=agent_card_url,
        )
        # 기본 AgentCard 조회
        agent_card = await resolver.get_agent_card()

    if not agent_card:
        raise ValueError('공개 AgentCard를 찾을 수 없습니다')

    return agent_card


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
