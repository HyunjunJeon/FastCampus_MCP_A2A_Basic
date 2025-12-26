"""여행 플래너 에이전트 대화형 테스트 클라이언트.

이 모듈은 여행 플래너 에이전트와 상호작용하는 대화형 CLI 클라이언트를
제공합니다. 사용자가 터미널에서 질문을 입력하고 에이전트의 응답을
실시간으로 확인할 수 있습니다.

실행 방법:
    python loop_client.py

사전 조건:
    여행 플래너 에이전트 서버가 localhost:10001에서 실행 중이어야 합니다.

사용법:
    - 프롬프트(>)에 여행 관련 질문 입력
    - 'exit' 입력으로 종료
"""
import asyncio

import httpx

from a2a.client import (
    A2ACardResolver,
    Client,
    ClientConfig,
    ClientFactory,
    create_text_message_object,
)
from a2a.types import TransportProtocol
from a2a.utils.message import get_message_text


def print_welcome_message() -> None:
    """환영 메시지를 출력합니다.

    클라이언트 시작 시 사용자에게 안내 메시지를 표시합니다.
    """
    print('Welcome to the generic A2A client!')
    print("Please enter your query (type 'exit' to quit):")


def get_user_query() -> str:
    """사용자로부터 입력을 받습니다.

    Returns:
        str: 사용자가 입력한 쿼리 문자열.
    """
    return input('\n> ')


async def interact_with_server(client: Client) -> None:
    """에이전트 서버와 대화형 세션을 실행합니다.

    사용자 입력을 받아 에이전트에 전송하고 응답을 출력하는
    루프를 실행합니다. 'exit' 입력 시 종료됩니다.

    Args:
        client: A2A 클라이언트 인스턴스. 메시지 전송에 사용됩니다.

    Note:
        스트리밍 응답을 지원하며, 각 응답 청크의 마지막 아티팩트를
        출력합니다. 이는 누적된 전체 응답을 표시하기 위함입니다.
    """
    while True:
        user_input = get_user_query()
        if user_input.lower() == 'exit':
            print('bye!~')
            break

        try:
            # 텍스트 메시지 객체 생성
            request = create_text_message_object(content=user_input)

            # 요청 전송 및 스트리밍 응답 수신
            async for response in client.send_message(request):
                task, _ = response
                # 마지막 아티팩트의 텍스트 내용 출력
                # 스트리밍 중에는 아티팩트가 누적되므로 항상 마지막 것을 표시
                print(get_message_text(task.artifacts[-1]))
        except Exception as e:
            print(f'An error occurred: {e}')


async def main() -> None:
    """테스트 클라이언트의 메인 함수.

    A2ACardResolver를 사용하여 AgentCard를 조회하고,
    A2A 클라이언트를 초기화한 후 대화형 세션을 시작합니다.

    동작 흐름:
        1. 환영 메시지 출력
        2. localhost:10001에서 AgentCard 조회
        3. 클라이언트 설정 및 초기화
        4. 대화형 세션 실행
    """
    print_welcome_message()
    async with httpx.AsyncClient() as httpx_client:
        # A2ACardResolver 초기화
        # agent_card_path와 extended_agent_card_path는 기본값 사용
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url='http://localhost:10001',
        )

        try:
            # AgentCard 조회
            agent_card = await resolver.get_agent_card()

            # AgentCard 정보를 기반으로 A2A 클라이언트 생성
            config = ClientConfig(
                httpx_client=httpx_client,
                supported_transports=[
                    TransportProtocol.jsonrpc,  # JSON-RPC 전송 프로토콜
                    TransportProtocol.http_json,  # HTTP JSON 전송 프로토콜
                ],
                streaming=agent_card.capabilities.streaming,  # 서버의 스트리밍 지원 여부
            )
            client = ClientFactory(config).create(agent_card)
        except Exception as e:
            print(f'Error initializing client: {e}')
            return

        # 대화형 세션 시작
        await interact_with_server(client)


if __name__ == '__main__':
    asyncio.run(main())
