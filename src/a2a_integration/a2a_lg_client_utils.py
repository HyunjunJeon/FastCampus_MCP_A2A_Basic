"""
A2A Client Utilities - A2A 클라이언트 0.3.0 기준
"""

from typing import Any
import re

import httpx
from a2a.types import AgentCard, Message, Role, TransportProtocol
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.client.helpers import create_text_message_object


class A2AClientManager:
    """A2A 클라이언트 관리 클래스"""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        streaming: bool = True,
    ):
        self.base_url = base_url
        self.streaming = streaming
        self.client = None
        self.agent_card: AgentCard | None = None
        self._httpx_client = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self) -> "A2AClientManager":
        self._httpx_client = httpx.AsyncClient()
        resolver = A2ACardResolver(
            httpx_client=self._httpx_client,
            base_url=self.base_url,
        )
        self.agent_card: AgentCard = await resolver.get_agent_card()
        config = ClientConfig(
            streaming=self.streaming,
            supported_transports=[
                TransportProtocol.jsonrpc,
                TransportProtocol.http_json,
                TransportProtocol.grpc,
            ]
        )
        factory = ClientFactory(config=config)
        self.client = factory.create(card=self.agent_card)
        return self

    async def get_agent_card(self) -> AgentCard:
        return self.agent_card

    async def close(self):
        if self._httpx_client:
            await self._httpx_client.aclose()

    def get_agent_info(self) -> dict[str, Any]:
        return {
            "name": self.agent_card.name,
            "description": self.agent_card.description,
            "url": self.agent_card.url,
            "capabilities": self.agent_card.capabilities.model_dump(),
            "default_input_modes": self.agent_card.default_input_modes,
            "default_output_modes": self.agent_card.default_output_modes,
            "skills": [
                {"name": skill.name, "description": skill.description}
                for skill in self.agent_card.skills
            ],
        }

    async def send_query(self, user_query: str) -> str:
        if not self.client:
            raise RuntimeError("클라이언트가 초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        message: Message = create_text_message_object(role=Role.user, content=user_query)
        response_text = ""

        def merge_incremental_text(existing: str, new: str) -> str:
            """스트리밍/최종 아티팩트 혼합 상황에서 텍스트를 중복 없이 병합.

            - 최종 아티팩트가 전체 텍스트를 담아오는 경우: new가 existing으로 시작 → 전체 교체
            - 스트리밍 델타가 증가분만 오는 경우: 접두 중복 계산 후 증가분만 추가
            - 불일치 시: 가장 긴 접미사-접두사 중첩을 찾아 나머지 추가
            """
            if not existing:
                return new
            if new.startswith(existing):
                return new
            if existing.startswith(new):
                return existing
            # 일반 케이스: overlap 계산
            max_overlap = min(len(existing), len(new))
            overlap = 0
            for k in range(max_overlap, 0, -1):
                if existing.endswith(new[:k]):
                    overlap = k
                    break
            return existing + new[overlap:]

        async for event in self.client.send_message(message):
            text_content = self._extract_text_from_event(event)
            if not text_content:
                continue
            response_text = merge_incremental_text(response_text, text_content)

        # 상태 업데이트 텍스트(진행 알림)가 결과 앞에 섞이지 않도록 정리
        response_text = self._sanitize_agent_status_text(response_text)
        return response_text.strip()

    def _extract_text_from_event(self, event) -> str:
        if not isinstance(event, tuple) or len(event) < 1:
            return ""
        task = event[0]
        if hasattr(task, "artifacts") and task.artifacts:
            for artifact in task.artifacts:
                if hasattr(artifact, "parts") and artifact.parts:
                    for part in artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            return part.root.text
        elif hasattr(task, "history") and task.history:
            last_message = task.history[-1]
            if (
                hasattr(last_message, "role")
                and last_message.role.value == "agent"
                and hasattr(last_message, "parts")
                and last_message.parts
            ):
                for part in last_message.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        return part.root.text
        return ""

    def _sanitize_agent_status_text(self, text: str) -> str:
        """A2A 실행 상태 안내 문구를 최종 결과에서 제거합니다.

        - 예: "A2A Agent 'CompiledStateGraph' 요청 인입 완료"
        - 예: "A2A Agent 요청 처리 중..."
        """
        if not text:
            return text

        patterns = [
            r"A2A\s+Agent\s*'[^']*'\s*요청\s*인입\s*완료",
            r"A2A\s+Agent\s*요청\s*처리\s*중\.\.\.",
        ]

        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)

        # 중간에 남은 이중 공백/개행을 정리
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned


async def query_a2a_agent(
    user_query: str, 
    base_url: str = "http://localhost:8080",
) -> str:
    async with A2AClientManager(base_url=base_url) as manager:
        return await manager.send_query(user_query)


async def query_multiple_a2a(
    user_queries: list[str], 
    base_url: str = "http://localhost:8080",
) -> list[str]:
    async with A2AClientManager(base_url=base_url) as manager:
        responses = []
        for user_query in user_queries:
            response = await manager.send_query(user_query)
            responses.append(response)
        return responses


