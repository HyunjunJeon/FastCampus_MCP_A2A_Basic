"""A2A 에이전트 서버 진입점.

이 모듈은 MCP 도구를 사용하여 A2A 프로토콜 관련 질문에
답변하는 에이전트 서버를 실행합니다.

주요 기능:
    - A2A 프로토콜 지식 기반 질의응답
    - GitMCP를 통한 A2A 문서 조회
    - 스트리밍 응답 지원

서버 포트:
    기본 포트: 9999

아키텍처:
    - HelloWorldAgentExecutor: MCP 도구 기반 에이전트 실행
    - A2ARequestHandler: A2A 요청 처리
    - A2AStarletteApplication: HTTP 서버 제공
"""
import click
import uvicorn

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import (
    DefaultRequestHandler,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    GetTaskRequest,
    GetTaskResponse,
    SendMessageRequest,
    SendMessageResponse,
)

from no_llm_framework.server.agent_executor import HelloWorldAgentExecutor


class A2ARequestHandler(DefaultRequestHandler):
    """A2A 요청 처리를 위한 커스텀 핸들러.

    DefaultRequestHandler를 상속하여 태스크 조회 및 메시지 전송을 처리합니다.
    """

    def __init__(
        self, agent_executor: AgentExecutor, task_store: InMemoryTaskStore
    ):
        super().__init__(agent_executor, task_store)

    async def on_get_task(self, request: GetTaskRequest) -> GetTaskResponse:
        return await super().on_get_task(request)

    async def on_message_send(
        self, request: SendMessageRequest
    ) -> SendMessageResponse:
        return await super().on_message_send(request)


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=9999)
def main(host: str, port: int):
    """A2A 에이전트 서버를 시작합니다.

    지정된 호스트와 포트로 A2A 프로토콜 지식 에이전트 서버를
    초기화하고 실행합니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    skill = AgentSkill(
        id='answer_detail_about_A2A_repo',
        name='Answer any information about A2A repo',
        description='The agent will look up the information about A2A repo and answer the question.',
        tags=['A2A repo'],
        examples=['What is A2A repo?', 'What is Google A2A repo?'],
    )

    agent_card = AgentCard(
        name='A2A Protocol Agent',
        description='A2A Protocol knowledge agent who has information about A2A Protocol and can answer questions about it',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(
            input_modes=['text'],
            output_modes=['text'],
            streaming=True,
        ),
        skills=[skill],
        # authentication=AgentAuthentication(schemes=['public']),
        examples=['What is A2A protocol?', 'What is Google A2A?'],
    )

    task_store = InMemoryTaskStore()
    request_handler = A2ARequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=task_store,
    )

    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    uvicorn.run(server.build(), host=host, port=port)


if __name__ == '__main__':
    main()
