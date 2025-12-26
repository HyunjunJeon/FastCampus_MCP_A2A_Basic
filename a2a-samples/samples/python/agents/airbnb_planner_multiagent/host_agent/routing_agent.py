# pylint: disable=logging-fstring-interpolation
"""라우팅 에이전트 모듈.

이 모듈은 사용자 요청을 적절한 원격 에이전트(날씨, Airbnb)로
라우팅하는 오케스트레이션 에이전트를 구현합니다.

아키텍처:
    - Google ADK Agent를 사용한 라우팅 로직
    - A2A 프로토콜을 통한 원격 에이전트 통신
    - 세션 상태 기반 활성 에이전트 추적

원격 에이전트:
    - Weather Agent: 날씨 정보 제공
    - Airbnb Agent: 숙소 검색

Note:
    root_instruction의 프롬프트는 영문으로 유지됩니다 (LLM 지시사항).
"""

import asyncio
import json
import os
import uuid

from typing import Any

import httpx

from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from remote_agent_connection import (
    RemoteAgentConnections,
    TaskUpdateCallback,
)


load_dotenv()


def convert_part(part: Part, tool_context: ToolContext):
    """파트를 텍스트로 변환합니다. 텍스트 파트만 지원합니다.

    Args:
        part: 변환할 파트.
        tool_context: 도구 컨텍스트.

    Returns:
        str: 파트의 텍스트 또는 알 수 없는 타입 메시지.
    """
    if part.type == 'text':
        return part.text

    return f'Unknown type: {part.type}'


def convert_parts(parts: list[Part], tool_context: ToolContext):
    """파트 리스트를 텍스트로 변환합니다.

    Args:
        parts: 파트 리스트.
        tool_context: 도구 컨텍스트.

    Returns:
        list: 텍스트 리스트.
    """
    rval = []
    for p in parts:
        rval.append(convert_part(p, tool_context))
    return rval


def create_send_message_payload(
    text: str, task_id: str | None = None, context_id: str | None = None
) -> dict[str, Any]:
    """태스크 전송을 위한 페이로드를 생성하는 헬퍼 함수.

    Args:
        text: 전송할 텍스트.
        task_id: 태스크 ID (선택사항).
        context_id: 컨텍스트 ID (선택사항).

    Returns:
        dict: 메시지 페이로드.
    """
    payload: dict[str, Any] = {
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': text}],
            'messageId': uuid.uuid4().hex,
        },
    }

    if task_id:
        payload['message']['taskId'] = task_id

    if context_id:
        payload['message']['contextId'] = context_id
    return payload


class RoutingAgent:
    """라우팅 에이전트.

    사용자 요청을 분석하여 적절한 원격 에이전트에 태스크를 전달하고
    조율하는 에이전트입니다.

    Attributes:
        task_callback: 태스크 업데이트 콜백.
        remote_agent_connections: 원격 에이전트 연결 딕셔너리.
        cards: 에이전트 카드 딕셔너리.
        agents: 사용 가능한 에이전트 정보 문자열.
    """

    def __init__(
        self,
        task_callback: TaskUpdateCallback | None = None,
    ):
        """RoutingAgent 인스턴스를 초기화합니다.

        Args:
            task_callback: 태스크 업데이트 콜백 (선택사항).
        """
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ''

    async def _async_init_components(
        self, remote_agent_addresses: list[str]
    ) -> None:
        """비동기 초기화를 수행합니다.

        원격 에이전트의 AgentCard를 가져와 연결을 설정합니다.

        Args:
            remote_agent_addresses: 원격 에이전트 주소 목록.
        """
        # 효율성을 위해 단일 httpx.AsyncClient 사용
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()

                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except httpx.ConnectError as e:
                    print(
                        f'ERROR: Failed to get agent card from {address}: {e}'
                    )
                except Exception as e:
                    print(
                        f'ERROR: Failed to initialize connection for {address}: {e}'
                    )

        # list_remote_agents를 통해 self.agents 채우기
        agent_info = []
        for agent_detail_dict in self.list_remote_agents():
            agent_info.append(json.dumps(agent_detail_dict))
        self.agents = '\n'.join(agent_info)

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: list[str],
        task_callback: TaskUpdateCallback | None = None,
    ) -> 'RoutingAgent':
        """RoutingAgent 인스턴스를 생성하고 비동기로 초기화합니다.

        Args:
            remote_agent_addresses: 원격 에이전트 주소 목록.
            task_callback: 태스크 업데이트 콜백 (선택사항).

        Returns:
            RoutingAgent: 초기화된 라우팅 에이전트 인스턴스.
        """
        instance = cls(task_callback)
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def create_agent(self) -> Agent:
        """RoutingAgent의 ADK Agent 인스턴스를 생성합니다.

        Returns:
            Agent: Google ADK 에이전트.
        """
        return Agent(
            model='gemini-2.5-flash-lite',
            name='Routing_agent',
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            description=(
                'This Routing agent orchestrates the decomposition of the user asking for weather forecast or airbnb accommodation'
            ),
            tools=[
                self.send_message,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        """RoutingAgent의 루트 지시사항을 생성합니다.

        Args:
            context: 읽기 전용 컨텍스트.

        Returns:
            str: 시스템 프롬프트 (영문 유지 - LLM 지시사항).
        """
        current_agent = self.check_active_agent(context)
        # 프롬프트는 영문 유지 (LLM 지시사항)
        return f"""
        **Role:** You are an expert Routing Delegator. Your primary function is to accurately delegate user inquiries regarding weather or accommodations to the appropriate specialized remote agents.

        **Core Directives:**

        * **Task Delegation:** Utilize the `send_message` function to assign actionable tasks to remote agents.
        * **Contextual Awareness for Remote Agents:** If a remote agent repeatedly requests user confirmation, assume it lacks access to the         full conversation history. In such cases, enrich the task description with all necessary contextual information relevant to that         specific agent.
        * **Autonomous Agent Engagement:** Never seek user permission before engaging with remote agents. If multiple agents are required to         fulfill a request, connect with them directly without requesting user preference or confirmation.
        * **Transparent Communication:** Always present the complete and detailed response from the remote agent to the user.
        * **User Confirmation Relay:** If a remote agent asks for confirmation, and the user has not already provided it, relay this         confirmation request to the user.
        * **Focused Information Sharing:** Provide remote agents with only relevant contextual information. Avoid extraneous details.
        * **No Redundant Confirmations:** Do not ask remote agents for confirmation of information or actions.
        * **Tool Reliance:** Strictly rely on available tools to address user requests. Do not generate responses based on assumptions. If         information is insufficient, request clarification from the user.
        * **Prioritize Recent Interaction:** Focus primarily on the most recent parts of the conversation when processing requests.
        * **Active Agent Prioritization:** If an active agent is already engaged, route subsequent related requests to that agent using the         appropriate task update tool.

        **Agent Roster:**

        * Available Agents: `{self.agents}`
        * Currently Active Seller Agent: `{current_agent['active_agent']}`
                """

    def check_active_agent(self, context: ReadonlyContext):
        """현재 활성 에이전트를 확인합니다.

        Args:
            context: 읽기 전용 컨텍스트.

        Returns:
            dict: 활성 에이전트 정보.
        """
        state = context.state
        if (
            'session_id' in state
            and 'session_active' in state
            and state['session_active']
            and 'active_agent' in state
        ):
            return {'active_agent': f'{state["active_agent"]}'}
        return {'active_agent': 'None'}

    def before_model_callback(
        self, callback_context: CallbackContext, llm_request
    ):
        """모델 호출 전 콜백.

        세션이 활성화되지 않은 경우 초기화합니다.

        Args:
            callback_context: 콜백 컨텍스트.
            llm_request: LLM 요청.
        """
        state = callback_context.state
        if 'session_active' not in state or not state['session_active']:
            if 'session_id' not in state:
                state['session_id'] = str(uuid.uuid4())
            state['session_active'] = True

    def list_remote_agents(self):
        """태스크 위임에 사용할 수 있는 원격 에이전트 목록을 반환합니다.

        Returns:
            list: 에이전트 이름과 설명이 포함된 딕셔너리 리스트.
        """
        if not self.cards:
            return []

        remote_agent_info = []
        for card in self.cards.values():
            print(f'Found agent card: {card.model_dump(exclude_none=True)}')
            print('=' * 100)
            remote_agent_info.append(
                {'name': card.name, 'description': card.description}
            )
        return remote_agent_info

    async def send_message(
        self, agent_name: str, task: str, tool_context: ToolContext
    ):
        """원격 판매자 에이전트에 태스크를 전송합니다.

        agent_name이라는 원격 에이전트에 메시지를 전송합니다.

        Args:
            agent_name: 태스크를 보낼 에이전트 이름.
            task: 사용자 문의 및 구매 요청에 대한 종합적인 대화 컨텍스트 요약
                및 달성해야 할 목표.
            tool_context: 이 메서드가 실행되는 도구 컨텍스트.

        Returns:
            Task: 원격 에이전트의 응답 태스크.

        Raises:
            ValueError: 에이전트를 찾을 수 없거나 클라이언트가 없는 경우.
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f'Agent {agent_name} not found')
        state = tool_context.state
        state['active_agent'] = agent_name
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f'Client not available for {agent_name}')
        task_id = state['task_id'] if 'task_id' in state else str(uuid.uuid4())

        if 'context_id' in state:
            context_id = state['context_id']
        else:
            context_id = str(uuid.uuid4())

        message_id = ''
        metadata = {}
        if 'input_message_metadata' in state:
            metadata.update(**state['input_message_metadata'])
            if 'message_id' in state['input_message_metadata']:
                message_id = state['input_message_metadata']['message_id']
        if not message_id:
            message_id = str(uuid.uuid4())

        payload = {
            'message': {
                'role': 'user',
                'parts': [
                    {'type': 'text', 'text': task}
                ],
                'messageId': message_id,
            },
        }

        if task_id:
            payload['message']['taskId'] = task_id

        if context_id:
            payload['message']['contextId'] = context_id

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )
        send_response: SendMessageResponse = await client.send_message(
            message_request=message_request
        )
        print(
            'send_response',
            send_response.model_dump_json(exclude_none=True, indent=2),
        )

        if not isinstance(send_response.root, SendMessageSuccessResponse):
            print('received non-success response. Aborting get task ')
            return None

        if not isinstance(send_response.root.result, Task):
            print('received non-task response. Aborting get task ')
            return None

        return send_response.root.result


def _get_initialized_routing_agent_sync() -> Agent:
    """RoutingAgent를 동기적으로 생성하고 초기화합니다.

    Returns:
        Agent: 초기화된 ADK 에이전트.

    Raises:
        RuntimeError: 이미 실행 중인 이벤트 루프에서 호출된 경우.
    """

    async def _async_main() -> Agent:
        routing_agent_instance = await RoutingAgent.create(
            remote_agent_addresses=[
                os.getenv('AIR_AGENT_URL', 'http://localhost:10002'),
                os.getenv('WEA_AGENT_URL', 'http://localhost:10001'),
            ]
        )
        return routing_agent_instance.create_agent()

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if 'asyncio.run() cannot be called from a running event loop' in str(e):
            print(
                f'Warning: Could not initialize RoutingAgent with asyncio.run(): {e}. '
                'This can happen if an event loop is already running (e.g., in Jupyter). '
                'Consider initializing RoutingAgent within an async function in your application.'
            )
        raise


root_agent = _get_initialized_routing_agent_sync()
