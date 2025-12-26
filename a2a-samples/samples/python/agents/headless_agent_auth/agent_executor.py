"""HR 에이전트 AgentExecutor 모듈.

이 모듈은 HRAgent를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다.

주요 기능:
    - HRAgent 스트리밍 응답을 A2A 이벤트로 변환
    - 태스크 상태 관리 (working, input_required, completed, failed)
    - 아티팩트 생성 및 전송
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message, new_task, new_text_artifact
from agent import HRAgent


class HRAgentExecutor(AgentExecutor):
    """HR 에이전트를 위한 AgentExecutor 구현.

    HRAgent를 A2A 프로토콜과 연결하여 직원 재직 상태
    확인 요청을 처리합니다. 스트리밍 응답을 지원합니다.

    Attributes:
        agent: HRAgent 인스턴스.
    """

    def __init__(self) -> None:
        """HRAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 HRAgent 인스턴스를 생성합니다.
        """
        self.agent = HRAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리합니다.

        HRAgent.stream()을 호출하여 직원 재직 상태 확인을 수행하고,
        진행 상황과 결과를 이벤트로 전송합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 상태 업데이트와 아티팩트를 전달합니다.

        처리 흐름:
            1. 사용자 입력 추출 및 태스크 생성
            2. HRAgent.stream() 호출
            3. 진행 상황을 TaskStatusUpdateEvent로 전송
            4. 완료 시 TaskArtifactUpdateEvent로 결과 전송
        """
        query = context.get_user_input()
        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # 에이전트 스트리밍 처리
        async for event in self.agent.stream(query, task.context_id):
            task_state = TaskState(event['task_state'])

            if event['is_task_complete']:
                # 완료: 아티팩트로 결과 전송
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
                        status=TaskStatus(state=task_state),
                        final=True,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )
            else:
                # 진행 중: 상태 업데이트 전송
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=task_state,
                            message=new_agent_text_message(
                                event['content'],
                                task.context_id,
                                task.id,
                            ),
                        ),
                        # 입력 필요, 실패, 알 수 없음 상태는 final로 표시
                        final=task_state
                        in {
                            TaskState.input_required,
                            TaskState.failed,
                            TaskState.unknown,
                        },
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """태스크 취소 요청을 처리합니다.

        현재 이 에이전트는 취소를 지원하지 않습니다.

        Args:
            request: 요청 컨텍스트.
            event_queue: 이벤트 큐.

        Raises:
            Exception: 취소가 지원되지 않음을 나타내는 예외.
        """
        raise Exception('cancel not supported')
