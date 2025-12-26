"""HR 에이전트 테스트 클라이언트.

이 모듈은 OAuth2 인증이 적용된 HR 에이전트와 통신하는
대화형 CLI 클라이언트를 구현합니다.

주요 기능:
    - AgentCard에서 인증 요구사항 자동 파싱
    - Auth0에서 액세스 토큰 자동 획득
    - 스트리밍 및 비스트리밍 응답 지원
    - 멀티턴 대화 지원

실행 방법:
    python test_client.py --agent http://localhost:10050

옵션:
    --agent: 에이전트 서버 URL (기본: http://localhost:10050)
    --context_id: 기존 대화 컨텍스트 ID
    --history: 대화 히스토리 표시 여부
    --debug: 디버그 모드 (전체 이벤트 출력)

필수 환경 변수:
    - A2A_CLIENT_AUTH0_CLIENT_ID: A2A 클라이언트 ID
    - A2A_CLIENT_AUTH0_CLIENT_SECRET: A2A 클라이언트 시크릿
    - HR_AGENT_AUTH0_AUDIENCE: HR 에이전트 OAuth2 audience
"""
import asyncio
import json
import os

from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import asyncclick as click
import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    GetTaskRequest,
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskQueryParams,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)
from auth0.authentication.get_token import GetToken
from dotenv import load_dotenv


load_dotenv()
access_token = None  # 전역 토큰 캐시


class AgentAuth(httpx.Auth):
    """에이전트 인증을 위한 httpx Auth 클래스.

    AgentCard의 인증 요구사항에 따라 액세스 토큰을 획득하고
    요청에 Bearer 토큰을 주입합니다.

    Attributes:
        agent_card: 에이전트 카드 (인증 정보 포함).
    """

    def __init__(self, agent_card: AgentCard) -> None:
        """AgentAuth 인스턴스를 초기화합니다.

        Args:
            agent_card: 에이전트 카드.
        """
        self.agent_card = agent_card

    def auth_flow(self, request):
        """인증 플로우를 실행합니다.

        OAuth2 인증이 필요한 경우 Auth0에서 토큰을 획득하고
        요청에 Authorization 헤더를 추가합니다.

        Args:
            request: httpx 요청 객체.

        Yields:
            request: 인증 헤더가 추가된 요청.
        """
        global access_token
        auth = self.agent_card.authentication

        # OAuth2 스키마가 아니거나 credentials가 없으면 스킵
        if not (
            any(scheme.lower() == 'oauth2' for scheme in auth.schemes)
            and auth.credentials
        ):
            yield request
            return

        # 토큰이 없으면 Auth0에서 획득
        if not access_token:
            token_url = json.loads(auth.credentials)['tokenUrl']
            print(f'\nFetching agent access token from {token_url}...')
            get_token = GetToken(
                domain=urlparse(token_url).hostname,
                client_id=os.getenv('A2A_CLIENT_AUTH0_CLIENT_ID'),
                client_secret=os.getenv('A2A_CLIENT_AUTH0_CLIENT_SECRET'),
            )
            access_token = get_token.client_credentials(
                os.getenv('HR_AGENT_AUTH0_AUDIENCE')
            )['access_token']
            print('Done.\n')

        request.headers['Authorization'] = f'Bearer {access_token}'
        yield request


@click.command()
@click.option('--agent', default='http://localhost:10050')
@click.option('--context_id')
@click.option('--history', default=False, is_flag=True)
@click.option('--debug', default=False, is_flag=True)
async def cli(
    agent: str, context_id: str | None, history: bool, debug: bool
) -> None:
    """HR 에이전트와 대화형 세션을 시작합니다.

    에이전트 카드를 가져와 인증을 설정하고,
    사용자 입력을 받아 에이전트에 전송합니다.

    Args:
        agent: 에이전트 서버 URL.
        context_id: 기존 대화 컨텍스트 ID (없으면 새로 생성).
        history: 대화 히스토리 표시 여부.
        debug: 디버그 모드 여부.
    """
    async with httpx.AsyncClient() as httpx_client:
        # AgentCard 가져오기
        agent_card = await (
            A2ACardResolver(
                httpx_client=httpx_client,
                base_url=agent,
            )
        ).get_agent_card()

        print('======= Agent Card ========')
        print(agent_card.model_dump_json(exclude_none=True, indent=2))

        # 인증 설정
        httpx_client.auth = AgentAuth(agent_card)

        # A2A 클라이언트 생성
        client = A2AClient(
            httpx_client=httpx_client,
            agent_card=agent_card,
        )

        if not context_id:
            context_id = uuid4().hex

        continue_loop = True
        streaming = agent_card.capabilities.streaming

        # 대화 루프
        while continue_loop:
            task_id = uuid4().hex
            print('=========  Starting a New Task ======== ')
            continue_loop = await complete_task(
                client,
                streaming,
                task_id,
                context_id,
                debug,
            )

            # 히스토리 출력
            if history and continue_loop:
                print('========= History ======== ')
                get_task_response = await client.get_task(
                    GetTaskRequest(
                        id=str(uuid4()),
                        params=TaskQueryParams(id=task_id, history_length=10),
                    )
                )
                print(
                    get_task_response.root.model_dump_json(
                        include={'result': {'history': True}}
                    )
                )


def create_send_params(
    text: str, task_id: str | None = None, context_id: str | None = None
) -> MessageSendParams:
    """메시지 전송 파라미터를 생성합니다.

    A2A 메시지 전송에 필요한 페이로드를 구성합니다.

    Args:
        text: 전송할 텍스트 메시지.
        task_id: 태스크 ID (멀티턴 대화용).
        context_id: 컨텍스트 ID.

    Returns:
        MessageSendParams: 메시지 전송 파라미터.
    """
    send_params: dict[str, Any] = {
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': text}],
            'messageId': uuid4().hex,
        },
        'configuration': {
            'acceptedOutputModes': ['text'],
        },
    }

    if task_id:
        send_params['message']['taskId'] = task_id

    if context_id:
        send_params['message']['contextId'] = context_id

    return MessageSendParams(**send_params)


async def complete_task(
    client: A2AClient,
    streaming: bool,
    task_id: str,
    context_id: str,
    debug: bool = False,
) -> bool:
    """태스크를 완료합니다.

    사용자 입력을 받아 에이전트에 전송하고 응답을 처리합니다.
    input_required 상태인 경우 재귀적으로 추가 입력을 받습니다.

    Args:
        client: A2A 클라이언트.
        streaming: 스트리밍 모드 여부.
        task_id: 태스크 ID.
        context_id: 컨텍스트 ID.
        debug: 디버그 모드 여부.

    Returns:
        bool: 대화 계속 여부 (False면 종료).
    """
    prompt = click.prompt(
        '\nWhat do you want to send to the agent? (:q or quit to exit)'
    )

    if prompt == ':q' or prompt == 'quit':
        return False

    send_params = create_send_params(
        text=prompt,
        task_id=task_id,
        context_id=context_id,
    )

    task = None
    if streaming:
        # 스트리밍 모드
        stream_response = client.send_message_streaming(
            SendStreamingMessageRequest(id=str(uuid4()), params=send_params)
        )
        async for chunk in stream_response:
            result = chunk.root.result
            print(
                f'stream event => {chunk.root.model_dump_json(exclude_none=True)}'
                if debug
                else (
                    next(
                        (
                            f'stream message => role: {result.role.value}, type: {part.root.type}, text: {part.root.text}'
                            for part in result.parts
                            if isinstance(part.root, TextPart)
                        ),
                        '',
                    )
                    if isinstance(result, Message)
                    else next(
                        (
                            f'stream message => role: {msg.role.value}, type: {part.root.type}, text: {part.root.text}'
                            for msg in result.history or []
                            for part in msg.parts
                            if isinstance(part.root, TextPart)
                        ),
                        '',
                    )
                    if isinstance(result, Task)
                    else next(
                        (
                            f'stream message => role: {result.status.message.role.value}, type: {part.root.type}, text: {part.root.text}'
                            for part in (
                                result.status.message.parts
                                if result.status.message
                                else []
                            )
                            if isinstance(part.root, TextPart)
                        ),
                        '',
                    )
                    if isinstance(result, TaskStatusUpdateEvent)
                    else next(
                        (
                            f'stream artifact => type: {part.root.type}, text: {part.root.text}'
                            for part in result.artifact.parts
                            if isinstance(part.root, TextPart)
                        ),
                        '',
                    )
                    if isinstance(result, TaskArtifactUpdateEvent)
                    else ''
                )
            )

        # 최종 태스크 상태 조회
        get_task_response = await client.get_task(
            GetTaskRequest(id=str(uuid4()), params=TaskQueryParams(id=task_id))
        )
        task = get_task_response.root.result
    else:
        # 비스트리밍 모드
        send_message_response = await client.send_message(
            SendMessageRequest(id=str(uuid4()), params=send_params)
        )
        task = send_message_response.root.result
        print(f'\n{task.model_dump_json(exclude_none=True)}')

    # 추가 입력 필요 시 재귀 호출
    if task.status.state == TaskState.input_required:
        return await complete_task(
            client,
            streaming,
            task_id,
            context_id,
            debug,
        )

    # 태스크 완료
    return True


if __name__ == '__main__':
    asyncio.run(cli())
