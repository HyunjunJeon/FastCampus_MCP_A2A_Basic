"""A2A 프로토콜 에이전트 실행자 모듈.

이 모듈은 MCP 도구 기반 에이전트를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다.

주요 기능:
    - 에이전트 스트리밍 응답을 A2A 이벤트로 변환
    - 태스크 상태 관리 (working, input_required, completed)
    - 아티팩트 생성 및 전송
"""
from typing import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact
from src.no_llm_framework.server.agent import Agent


class HelloWorldAgentExecutor(AgentExecutor):
    """A2A 프로토콜 지식 에이전트 실행자.

    MCP 도구를 사용하여 A2A 프로토콜 관련 질문에 답변합니다.
    GitMCP를 통해 A2A 저장소 문서를 조회하고 응답을 생성합니다.

    Attributes:
        agent: MCP 도구 기반 서버 에이전트.
    """

    def __init__(self):
        self.agent = Agent(
            mode='stream',
            token_stream_callback=print,
            mcp_url='https://gitmcp.io/google/A2A',
        )

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        query = context.get_user_input()
        task = context.current_task

        if not context.message:
            raise Exception('No message provided')

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        async for event in self.agent.stream(query):
            if event['is_task_complete']:
                await event_queue.enqueue_event(
                    TaskArtifactUpdateEvent(
                        append=False,
                        context_id=task.context_id,
                        task_id=task.id,
                        last_chunk=True,
                        artifact=new_text_artifact(
                            name='current_result',
                            description='Result of request to agent.',
                            text=event['content'],
                        ),
                    )
                )
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(state=TaskState.completed),
                        final=True,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )
            elif event['require_user_input']:
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.input_required,
                            message=new_agent_text_message(
                                event['content'],
                                task.context_id,
                                task.id,
                            ),
                        ),
                        final=True,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )
            else:
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        append=True,
                        status=TaskStatus(
                            state=TaskState.working,
                            message=new_agent_text_message(
                                event['content'],
                                task.context_id,
                                task.id,
                            ),
                        ),
                        final=False,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('cancel not supported')
