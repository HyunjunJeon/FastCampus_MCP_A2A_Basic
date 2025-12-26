"""Hello World 에이전트 테스트 클라이언트.

이 모듈은 Hello World A2A 에이전트 서버에 연결하여 테스트하는 클라이언트입니다.
A2ACardResolver를 사용하여 공개 및 확장 AgentCard를 가져오고,
A2AClient를 사용하여 메시지를 전송하는 방법을 보여줍니다.

주요 기능:
    - 공개 AgentCard 조회 (/.well-known/agent.json)
    - 인증된 확장 AgentCard 조회 (/agent/authenticatedExtendedCard)
    - 일반 메시지 전송 (send_message)
    - 스트리밍 메시지 전송 (send_message_streaming)

실행 방법:
    python test_client.py

사전 조건:
    Hello World 에이전트 서버가 localhost:9999에서 실행 중이어야 합니다.
"""
import logging

from typing import Any
from uuid import uuid4

import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
)
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)


async def main() -> None:
    """테스트 클라이언트의 메인 함수.

    Hello World 에이전트 서버에 연결하여 다음 작업을 수행합니다:
    1. 공개 AgentCard 조회
    2. 확장 AgentCard 조회 (지원되는 경우)
    3. 일반 메시지 전송 테스트
    4. 스트리밍 메시지 전송 테스트
    """
    # INFO 레벨 메시지를 표시하도록 로깅 설정
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)  # 로거 인스턴스 생성

    # --8<-- [start:A2ACardResolver]

    base_url = 'http://localhost:9999'

    async with httpx.AsyncClient() as httpx_client:
        # A2ACardResolver 초기화
        # agent_card_path와 extended_agent_card_path는 기본값 사용
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=base_url,
        )
        # --8<-- [end:A2ACardResolver]

        # 공개 AgentCard 조회 및 클라이언트 초기화
        final_agent_card_to_use: AgentCard | None = None

        try:
            logger.info(
                f'공개 AgentCard 조회 시도: {base_url}{AGENT_CARD_WELL_KNOWN_PATH}'
            )
            _public_card = (
                await resolver.get_agent_card()
            )  # 기본 공개 경로에서 조회
            logger.info('공개 AgentCard 조회 성공:')
            logger.info(
                _public_card.model_dump_json(indent=2, exclude_none=True)
            )
            final_agent_card_to_use = _public_card
            logger.info(
                '\n클라이언트 초기화에 공개 AgentCard 사용 (기본값).'
            )

            # 공개 카드가 인증된 확장 카드를 지원하는지 확인
            if _public_card.supports_authenticated_extended_card:
                try:
                    logger.info(
                        f'\n공개 카드가 인증된 확장 카드를 지원합니다. 조회 시도: {base_url}{EXTENDED_AGENT_CARD_PATH}'
                    )
                    # 더미 인증 헤더 설정 (실제 환경에서는 유효한 토큰 사용)
                    auth_headers_dict = {
                        'Authorization': 'Bearer dummy-token-for-extended-card'
                    }
                    _extended_card = await resolver.get_agent_card(
                        relative_card_path=EXTENDED_AGENT_CARD_PATH,
                        http_kwargs={'headers': auth_headers_dict},
                    )
                    logger.info(
                        '인증된 확장 AgentCard 조회 성공:'
                    )
                    logger.info(
                        _extended_card.model_dump_json(
                            indent=2, exclude_none=True
                        )
                    )
                    final_agent_card_to_use = (
                        _extended_card  # 확장 카드로 업데이트
                    )
                    logger.info(
                        '\n클라이언트 초기화에 인증된 확장 AgentCard 사용.'
                    )
                except Exception as e_extended:
                    logger.warning(
                        f'확장 AgentCard 조회 실패: {e_extended}. 공개 카드로 진행합니다.',
                        exc_info=True,
                    )
            elif (
                _public_card
            ):  # supports_authenticated_extended_card가 False 또는 None인 경우
                logger.info(
                    '\n공개 카드가 확장 카드를 지원하지 않습니다. 공개 카드를 사용합니다.'
                )

        except Exception as e:
            logger.error(
                f'공개 AgentCard 조회 중 치명적 오류: {e}', exc_info=True
            )
            raise RuntimeError(
                '공개 AgentCard를 조회하지 못했습니다. 계속할 수 없습니다.'
            ) from e

        # --8<-- [start:send_message]
        # A2AClient 초기화 및 메시지 전송
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )
        logger.info('A2AClient 초기화 완료.')

        # 전송할 메시지 페이로드 구성
        send_message_payload: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [
                    {'kind': 'text', 'text': 'how much is 10 USD in INR?'}
                ],
                'messageId': uuid4().hex,
            },
        }
        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        # 일반 메시지 전송 및 응답 출력
        response = await client.send_message(request)
        print(response.model_dump(mode='json', exclude_none=True))
        # --8<-- [end:send_message]

        # --8<-- [start:send_message_streaming]
        # 스트리밍 메시지 전송 테스트
        streaming_request = SendStreamingMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        # 스트리밍 응답을 청크 단위로 수신하여 출력
        stream_response = client.send_message_streaming(streaming_request)

        async for chunk in stream_response:
            print(chunk.model_dump(mode='json', exclude_none=True))
        # --8<-- [end:send_message_streaming]


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
