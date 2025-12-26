# pylint: disable=logging-fstring-interpolation
"""Airbnb 에이전트 AgentExecutor 모듈.

이 모듈은 AirbnbAgent를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다.

주요 기능:
    - AirbnbAgent 스트리밍 응답을 A2A 이벤트로 변환
    - 태스크 상태 관리 (working, input_required, completed)
    - 아티팩트 생성 및 전송
"""
import logging

from typing import Any, override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact
from airbnb_agent import (
    AirbnbAgent,
)


logger = logging.getLogger(__name__)


class AirbnbAgentExecutor(AgentExecutor):
    """사전 로드된 도구를 사용하는 Airbnb 에이전트 실행자.

    MCP 도구를 사용하여 Airbnb 숙소 검색 요청을 처리합니다.
    스트리밍 응답을 지원하여 실시간 진행 상황을 전달합니다.
    """

    def __init__(self, mcp_tools: list[Any]):
        """AirbnbAgentExecutor 인스턴스를 초기화합니다.

        Args:
            mcp_tools: AirbnbAgent용 사전 로드된 MCP 도구 목록.
        """
        super().__init__()
        logger.info(
            f'Initializing AirbnbAgentExecutor with {len(mcp_tools) if mcp_tools else "no"} MCP tools.'
        )
        self.agent = AirbnbAgent(mcp_tools=mcp_tools)

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
        # invoke the underlying agent, using streaming results
        async for event in self.agent.stream(query, task.context_id):
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
