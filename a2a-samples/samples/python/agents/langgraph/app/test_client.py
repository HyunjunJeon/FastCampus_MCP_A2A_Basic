"""LangGraph 통화 에이전트 테스트 클라이언트.

이 모듈은 LangGraph 기반 통화 변환 에이전트 서버에 연결하여 테스트하는 클라이언트입니다.
일반 메시지 전송, 멀티턴 대화, 스트리밍 응답 등 다양한 시나리오를 테스트합니다.

주요 테스트 시나리오:
    1. 단일 요청: 완전한 환율 조회 질문
    2. 멀티턴 대화: 추가 정보가 필요한 불완전한 질문 → 후속 응답
    3. 스트리밍: 실시간 응답 스트리밍

실행 방법:
    python test_client.py

사전 조건:
    통화 변환 에이전트 서버가 localhost:10000에서 실행 중이어야 합니다.
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

    통화 변환 에이전트 서버에 연결하여 다음 테스트를 수행합니다:
    1. AgentCard 조회 (공개 및 확장)
    2. 단일 환율 조회 요청
    3. 멀티턴 대화 (불완전한 질문 → 추가 정보 제공)
    4. 스트리밍 메시지 전송
    """
    # INFO 레벨 메시지를 표시하도록 로깅 설정
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)  # 로거 인스턴스 생성

    # --8<-- [start:A2ACardResolver]

    base_url = 'http://localhost:10000'

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
                        '\n공개 카드가 인증된 확장 카드를 지원합니다. '
                        f'조회 시도: {base_url}{EXTENDED_AGENT_CARD_PATH}'
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
                        f'확장 AgentCard 조회 실패: {e_extended}. '
                        '공개 카드로 진행합니다.',
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
        # A2AClient 초기화
        client = A2AClient(
            httpx_client=httpx_client, agent_card=final_agent_card_to_use
        )
        logger.info('A2AClient 초기화 완료.')

        # 테스트 1: 완전한 환율 조회 질문
        send_message_payload: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [
                    {'kind': 'text', 'text': 'how much is 10 USD in INR?'}
                ],
                'message_id': uuid4().hex,
            },
        }
        request = SendMessageRequest(
            id=str(uuid4()), params=MessageSendParams(**send_message_payload)
        )

        # 일반 메시지 전송
        response = await client.send_message(request)
        print(response.model_dump(mode='json', exclude_none=True))
        # --8<-- [end:send_message]

        # --8<-- [start:Multiturn]
        # 테스트 2: 멀티턴 대화 - 불완전한 질문 (대상 통화 누락)
        send_message_payload_multiturn: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [
                    {
                        'kind': 'text',
                        'text': 'How much is the exchange rate for 1 USD?',
                    }
                ],
                'message_id': uuid4().hex,
            },
        }
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**send_message_payload_multiturn),
        )

        # 에이전트가 'input_required' 상태를 반환할 것으로 예상
        response = await client.send_message(request)
        print(response.model_dump(mode='json', exclude_none=True))

        # 응답에서 태스크 ID와 컨텍스트 ID 추출 (대화 연속성 유지)
        task_id = response.root.result.id
        context_id = response.root.result.context_id

        # 후속 메시지: 누락된 정보 제공 (대상 통화: CAD)
        second_send_message_payload_multiturn: dict[str, Any] = {
            'message': {
                'role': 'user',
                'parts': [{'kind': 'text', 'text': 'CAD'}],
                'message_id': uuid4().hex,
                'task_id': task_id,      # 기존 태스크 ID 사용
                'context_id': context_id,  # 기존 컨텍스트 ID 사용
            },
        }

        second_request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**second_send_message_payload_multiturn),
        )

        # 이제 에이전트가 완전한 정보로 환율 조회 가능
        second_response = await client.send_message(second_request)
        print(second_response.model_dump(mode='json', exclude_none=True))
        # --8<-- [end:Multiturn]

        # --8<-- [start:send_message_streaming]
        # 테스트 3: 스트리밍 메시지 전송
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
