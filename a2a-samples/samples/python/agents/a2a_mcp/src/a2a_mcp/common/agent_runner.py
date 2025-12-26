"""ADK 에이전트 실행 관리 모듈.

이 모듈은 ADK 에이전트의 실행을 관리하고 세션 처리 및
스트리밍 응답을 담당합니다.

주요 기능:
    - 인메모리 세션 서비스 관리
    - 에이전트 스트리밍 실행
    - 최종 응답 및 중간 상태 처리
"""
# type: ignore

import uuid

from collections.abc import AsyncGenerator

from google.adk.agents import Agent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


class AgentRunner:
    """ADK 에이전트 실행 관리자.

    에이전트 실행 로직을 캡슐화하고 세션 관리(생성/조회) 및
    스트리밍 응답을 처리합니다. 인메모리 세션 서비스를 사용합니다.

    Attributes:
        session_service: InMemorySessionService 인스턴스.
        session: 현재 세션.
        app_name: 애플리케이션 이름.
        user_id: 사용자 ID.
    """

    def __init__(
        self,
        user_id: str = 'user_1',
        app_name: str = 'A2A-MCP',
    ):
        self.session_service = InMemorySessionService()
        self.session = None
        self.app_name = app_name
        self.user_id = user_id

    async def run_stream(
        self, agent: Agent, query: str, session_id: str
    ) -> AsyncGenerator[Event, None]:
        """에이전트를 스트리밍 모드로 실행합니다.

        Args:
            agent: 실행할 ADK Agent.
            query: 사용자 쿼리.
            session_id: 세션 ID.

        Yields:
            dict: 중간 상태 또는 최종 결과.
        """
        runner = Runner(
            agent=agent,
            app_name=self.app_name,
            session_service=self.session_service,
        )
        if not session_id:
            session_id = uuid.uuid4().hex
        else:
            self.session = await self.session_service.get_session(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=session_id,
            )
        if not self.session:
            self.session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
                session_id=session_id,
            )
        content = types.Content(role='user', parts=[types.Part(text=query)])

        async for event in runner.run_async(
            user_id=self.user_id,
            session_id=self.session.id,
            new_message=content,
        ):
            if event.is_final_response():
                response = ''
                if (
                    event.content
                    and event.content.parts
                    and event.content.parts[0].text
                ):
                    response = '\n'.join(
                        [p.text for p in event.content.parts if p.text]
                    )
                elif (
                    event.content
                    and event.content.parts
                    and any(
                        True for p in event.content.parts if p.function_response
                    )
                ):
                    response = next(
                        p.function_response.model_dump()
                        for p in event.content.parts
                    )
                else:
                    response = f'Error in running agent: {agent.name}'
                yield {
                    'type': 'final_result',
                    'response': response,
                }
            else:
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': f'{agent.name}: Processing request...',
                }
