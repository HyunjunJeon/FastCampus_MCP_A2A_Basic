"""원격 에이전트 연결 모듈.

이 모듈은 원격 A2A 에이전트와의 연결을 관리하는 클래스를 제공합니다.

주요 기능:
    - A2A 클라이언트를 통한 메시지 전송
    - AgentCard 관리
    - 타임아웃 설정
"""
from collections.abc import Callable

import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from dotenv import load_dotenv


load_dotenv()

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """원격 에이전트 연결을 관리하는 클래스.

    A2A 클라이언트를 통해 원격 에이전트와 통신합니다.
    """

    def __init__(self, agent_card: AgentCard, agent_url: str):
        print(f'agent_card: {agent_card}')
        print(f'agent_url: {agent_url}')
        self._httpx_client = httpx.AsyncClient(timeout=30)
        self.agent_client = A2AClient(
            self._httpx_client, agent_card, url=agent_url
        )
        self.card = agent_card

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(
        self, message_request: SendMessageRequest
    ) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)
