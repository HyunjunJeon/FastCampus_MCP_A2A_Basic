"""범용 에이전트 실행자 모듈.

이 모듈은 여행 에이전트들을 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다.

주요 기능:
    - 에이전트 스트리밍 응답을 A2A 이벤트로 변환
    - 태스크 상태 관리 (working, input_required, completed)
    - 아티팩트 생성 및 전송
    - 에이전트 간 호출 결과 프록시
"""
import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    DataPart,
    InvalidParamsError,
    SendStreamingMessageSuccessResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError
from a2a_mcp.common.base_agent import BaseAgent


logger = logging.getLogger(__name__)


class GenericAgentExecutor(AgentExecutor):
    """여행 에이전트를 위한 범용 AgentExecutor.

    BaseAgent 인터페이스를 구현하는 모든 에이전트를 A2A 프로토콜과
    연결합니다. 스트리밍 응답과 에이전트 간 호출을 지원합니다.

    Attributes:
        agent: 실행할 BaseAgent 인스턴스.
    """

    def __init__(self, agent: BaseAgent):
        self.agent = agent

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """에이전트를 실행하고 이벤트를 큐에 전송합니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 전송용 큐.
        """
        logger.info(f'Executing agent {self.agent.agent_name}')
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()

        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        async for item in self.agent.stream(query, task.context_id, task.id):
            # Agent to Agent call will return events,
            # Update the relevant ids to proxy back.
            if hasattr(item, 'root') and isinstance(
                item.root, SendStreamingMessageSuccessResponse
            ):
                event = item.root.result
                if isinstance(
                    event,
                    (TaskStatusUpdateEvent | TaskArtifactUpdateEvent),
                ):
                    await event_queue.enqueue_event(event)
                continue

            is_task_complete = item['is_task_complete']
            require_user_input = item['require_user_input']

            if is_task_complete:
                if item['response_type'] == 'data':
                    part = DataPart(data=item['content'])
                else:
                    part = TextPart(text=item['content'])

                await updater.add_artifact(
                    [part],
                    name=f'{self.agent.agent_name}-result',
                )
                await updater.complete()
                break
            if require_user_input:
                await updater.update_status(
                    TaskState.input_required,
                    new_agent_text_message(
                        item['content'],
                        task.context_id,
                        task.id,
                    ),
                    final=True,
                )
                break
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(
                    item['content'],
                    task.context_id,
                    task.id,
                ),
            )

    def _validate_request(self, context: RequestContext) -> bool:
        """요청을 검증합니다.

        Returns:
            bool: 검증 실패 시 True.
        """
        return False

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """태스크 취소를 처리합니다 (미지원).

        Raises:
            ServerError: 취소 작업 미지원 오류.
        """
        raise ServerError(error=UnsupportedOperationError())
