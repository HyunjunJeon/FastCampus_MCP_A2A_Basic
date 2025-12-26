"""멀티에이전트 오케스트레이션 클라이언트 에이전트 모듈.

이 모듈은 여러 원격 A2A 에이전트를 조율하여 복잡한 질문에
답변하는 클라이언트 에이전트를 구현합니다.

주요 기능:
    - 원격 에이전트 카드 검색 및 등록
    - LLM 기반 에이전트 선택 결정
    - 선택된 에이전트로 메시지 전송 및 스트리밍 수신
    - 멀티턴 대화를 통한 반복적 에이전트 호출

아키텍처:
    - Jinja2 템플릿으로 LLM 프롬프트 생성
    - A2AClient로 원격 에이전트와 통신
    - Google Gemini LLM으로 에이전트 선택 결정
"""
import asyncio
import json
import re

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx

from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendStreamingMessageRequest,
    SendStreamingMessageSuccessResponse,
    TaskStatusUpdateEvent,
    TextPart,
)
from google import genai
from jinja2 import Template

from no_llm_framework.client.constant import GOOGLE_API_KEY


# --- Jinja2 템플릿 로드 ---
dir_path = Path(__file__).parent

with Path(dir_path / 'decide.jinja').open('r') as f:
    decide_template = Template(f.read())

with Path(dir_path / 'agents.jinja').open('r') as f:
    agents_template = Template(f.read())

with Path(dir_path / 'agent_answer.jinja').open('r') as f:
    agent_answer_template = Template(f.read())


def stream_llm(prompt: str) -> Generator[str]:
    """LLM 응답을 스트리밍합니다.

    Args:
        prompt: LLM에 보낼 프롬프트.

    Yields:
        str: LLM 응답 청크.
    """
    client = genai.Client(vertexai=False, api_key=GOOGLE_API_KEY)
    for chunk in client.models.generate_content_stream(
        model='gemini-2.5-flash-lite',
        contents=prompt,
    ):
        yield chunk.text


class Agent:
    """멀티에이전트 오케스트레이션을 수행하는 클라이언트 에이전트.

    여러 원격 A2A 에이전트를 조율하여 복잡한 질문에 답변합니다.
    LLM을 사용해 어떤 에이전트를 호출할지 결정하고,
    선택된 에이전트에게 메시지를 전송합니다.

    Attributes:
        mode: 실행 모드 ('complete' 또는 'stream').
        token_stream_callback: 토큰 스트리밍 콜백 함수.
        agent_urls: 원격 에이전트 URL 목록.
        agents_registry: 에이전트 이름과 AgentCard 매핑.
    """

    def __init__(
        self,
        mode: Literal['complete', 'stream'] = 'stream',
        token_stream_callback: Callable[[str], None] | None = None,
        agent_urls: list[str] | None = None,
        agent_prompt: str | None = None,
    ):
        self.mode = mode
        self.token_stream_callback = token_stream_callback
        self.agent_urls = agent_urls
        self.agents_registry: dict[str, AgentCard] = {}

    async def get_agents(self) -> tuple[dict[str, AgentCard], str]:
        """모든 에이전트 URL에서 에이전트 카드를 조회하고 프롬프트를 렌더링합니다.

        Returns:
            tuple[dict[str, AgentCard], str]: 에이전트 이름-카드 매핑 딕셔너리와
                렌더링된 에이전트 프롬프트 문자열.
        """
        async with httpx.AsyncClient() as httpx_client:
            card_resolvers = [
                A2ACardResolver(httpx_client, url) for url in self.agent_urls
            ]
            agent_cards = await asyncio.gather(
                *[
                    card_resolver.get_agent_card()
                    for card_resolver in card_resolvers
                ]
            )
            agents_registry = {
                agent_card.name: agent_card for agent_card in agent_cards
            }
            agent_prompt = agents_template.render(agent_cards=agent_cards)
            return agents_registry, agent_prompt

    def call_llm(self, prompt: str) -> str:
        """LLM을 호출하고 응답을 반환합니다.

        Args:
            prompt: LLM에 보낼 프롬프트.

        Returns:
            str 또는 Generator[str]: 모드에 따라 문자열 또는 제너레이터.
        """
        if self.mode == 'complete':
            return stream_llm(prompt)

        result = ''
        for chunk in stream_llm(prompt):
            result += chunk
        return result

    async def decide(
        self,
        question: str,
        agents_prompt: str,
        called_agents: list[dict] | None = None,
    ) -> Generator[str, None]:
        """질문에 답하기 위해 사용할 에이전트를 결정합니다.

        Args:
            question: 답변할 질문.
            agents_prompt: 사용 가능한 에이전트를 설명하는 프롬프트.
            called_agents: 이전에 호출된 에이전트와 그 답변 목록.

        Returns:
            Generator[str, None]: LLM 응답의 문자열 제너레이터.
        """
        if called_agents:
            call_agent_prompt = agent_answer_template.render(
                called_agents=called_agents
            )
        else:
            call_agent_prompt = ''
        prompt = decide_template.render(
            question=question,
            agent_prompt=agents_prompt,
            call_agent_prompt=call_agent_prompt,
        )
        return self.call_llm(prompt)

    def extract_agents(self, response: str) -> list[dict]:
        """LLM 응답에서 에이전트 정보를 추출합니다.

        Args:
            response: LLM 응답 문자열.

        Returns:
            list[dict]: 추출된 에이전트 정보 목록.
        """
        pattern = r'```json\n(.*?)\n```'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return []

    async def send_message_to_an_agent(
        self, agent_card: AgentCard, message: str
    ):
        """특정 에이전트에 메시지를 전송하고 스트리밍 응답을 수신합니다.

        Args:
            agent_card: 메시지를 보낼 에이전트 카드.
            message: 전송할 메시지.

        Yields:
            str: 에이전트의 스트리밍 응답.
        """
        async with httpx.AsyncClient() as httpx_client:
            client = A2AClient(httpx_client, agent_card=agent_card)
            message = MessageSendParams(
                message=Message(
                    role=Role.user,
                    parts=[Part(TextPart(text=message))],
                    message_id=uuid4().hex,
                    task_id=uuid4().hex,
                )
            )

            streaming_request = SendStreamingMessageRequest(
                id=str(uuid4().hex), params=message
            )
            async for chunk in client.send_message_streaming(streaming_request):
                if isinstance(
                    chunk.root, SendStreamingMessageSuccessResponse
                ) and isinstance(chunk.root.result, TaskStatusUpdateEvent):
                    message = chunk.root.result.status.message
                    if message:
                        yield message.parts[0].root.text

    async def stream(self, question: str):
        """질문 답변 과정을 스트리밍합니다 (여러 에이전트 호출 가능).

        Args:
            question: 답변할 질문.

        Yields:
            str: 에이전트 응답과 중간 단계를 포함한 스트리밍 출력.
        """
        agent_answers: list[dict] = []
        for _ in range(3):
            agents_registry, agent_prompt = await self.get_agents()
            response = ''
            for chunk in await self.decide(
                question, agent_prompt, agent_answers
            ):
                response += chunk
                if self.token_stream_callback:
                    self.token_stream_callback(chunk)
                yield chunk

            agents = self.extract_agents(response)
            if agents:
                for agent in agents:
                    agent_response = ''
                    agent_card = agents_registry[agent['name']]
                    yield f'<Agent name="{agent["name"]}">\n'
                    async for chunk in self.send_message_to_an_agent(
                        agent_card, agent['prompt']
                    ):
                        agent_response += chunk
                        if self.token_stream_callback:
                            self.token_stream_callback(chunk)
                        yield chunk
                    yield '</Agent>\n'
                    match = re.search(
                        r'<Answer>(.*?)</Answer>', agent_response, re.DOTALL
                    )
                    answer = match.group(1).strip() if match else agent_response
                    agent_answers.append(
                        {
                            'name': agent['name'],
                            'prompt': agent['prompt'],
                            'answer': answer,
                        }
                    )
            else:
                return


if __name__ == '__main__':
    import asyncio

    import colorama

    async def main():
        """클라이언트 에이전트 테스트를 위한 메인 함수."""
        agent = Agent(
            mode='stream',
            token_stream_callback=None,
            agent_urls=['http://localhost:9999/'],
        )

        async for chunk in agent.stream('What is A2A protocol?'):
            if chunk.startswith('<Agent name="'):
                print(colorama.Fore.CYAN + chunk, end='', flush=True)
            elif chunk.startswith('</Agent>'):
                print(colorama.Fore.RESET + chunk, end='', flush=True)
            else:
                print(chunk, end='', flush=True)

    asyncio.run(main())
