"""A2A 클라이언트 CLI 진입점.

이 모듈은 멀티에이전트 오케스트레이션을 수행하는 A2A 클라이언트를
커맨드라인에서 실행할 수 있도록 합니다.

주요 기능:
    - 원격 A2A 에이전트에 질문 전송
    - 스트리밍 응답 수신 및 컬러 출력
    - 에이전트 선택 및 라우팅

실행 방법:
    python -m no_llm_framework.client --question "What is A2A?"
"""
import asyncio

from typing import Literal

import asyncclick as click
import colorama

from no_llm_framework.client.agent import Agent


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=9999)
@click.option('--mode', 'mode', default='streaming')
@click.option('--question', 'question', required=True)
async def a_main(
    host: str,
    port: int,
    mode: Literal['completion', 'streaming'],
    question: str,
):
    """A2A 클라이언트를 실행하는 비동기 메인 함수.

    Args:
        host: 연결할 서버 호스트 주소.
        port: 연결할 서버 포트 번호.
        mode: 실행 모드 ('completion' 또는 'streaming').
        question: 에이전트에게 물어볼 질문.
    """
    agent = Agent(
        mode='stream',
        token_stream_callback=None,
        agent_urls=[f'http://{host}:{port}/'],
    )
    async for chunk in agent.stream(question):
        if chunk.startswith('<Agent name="'):
            print(colorama.Fore.CYAN + chunk, end='', flush=True)
        elif chunk.startswith('</Agent>'):
            print(colorama.Fore.RESET + chunk, end='', flush=True)
        else:
            print(chunk, end='', flush=True)


def main() -> None:
    """클라이언트 실행을 위한 동기 래퍼 함수."""
    asyncio.run(a_main())


if __name__ == '__main__':
    main()
