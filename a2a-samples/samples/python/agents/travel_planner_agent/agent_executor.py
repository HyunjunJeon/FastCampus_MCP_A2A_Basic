"""여행 플래너 AgentExecutor 모듈.

이 모듈은 TravelPlannerAgent를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다. 스트리밍 응답을 아티팩트로
변환하여 클라이언트에 전달합니다.

클래스:
    TravelPlannerAgentExecutor: A2A AgentExecutor 인터페이스를 구현하는 래퍼
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
from a2a.utils import new_text_artifact
from agent import TravelPlannerAgent


class TravelPlannerAgentExecutor(AgentExecutor):
    """여행 플래너 에이전트를 위한 AgentExecutor 구현.

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    TravelPlannerAgent를 A2A 서버와 연결합니다. 스트리밍 응답을
    아티팩트 업데이트 이벤트로 변환하여 실시간으로 클라이언트에 전달합니다.

    Attributes:
        agent: TravelPlannerAgent 인스턴스. 실제 여행 계획 로직을 수행합니다.

    응답 흐름:
        1. 사용자 입력 추출
        2. TravelPlannerAgent.stream() 호출로 스트리밍 응답 수신
        3. 각 청크를 TaskArtifactUpdateEvent로 변환하여 전송
        4. 완료 시 TaskStatusUpdateEvent(completed)로 종료
    """

    def __init__(self) -> None:
        """TravelPlannerAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 TravelPlannerAgent 인스턴스를 생성합니다.
        """
        self.agent = TravelPlannerAgent()

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 여행 계획 응답을 스트리밍합니다.

        TravelPlannerAgent로부터 스트리밍 응답을 수신하여 각 청크를
        아티팩트 업데이트 이벤트로 변환합니다. 스트리밍이 완료되면
        태스크 상태를 'completed'로 업데이트합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 태스크 ID 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 아티팩트와 상태 업데이트를 클라이언트에 전달합니다.

        Raises:
            Exception: 메시지가 제공되지 않은 경우.

        Note:
            각 스트리밍 청크는 'current_result'라는 이름의 텍스트 아티팩트로
            전달됩니다. 이전 아티팩트를 덮어쓰는 것이 아니라 누적되므로,
            클라이언트는 마지막 아티팩트를 표시해야 합니다.
        """
        # 사용자 입력 추출
        query = context.get_user_input()
        if not context.message:
            raise Exception('No message provided')

        # TravelPlannerAgent의 스트리밍 응답 처리
        async for event in self.agent.stream(query):
            # 각 청크를 아티팩트 업데이트 이벤트로 변환
            message = TaskArtifactUpdateEvent(
                context_id=context.context_id,  # type: ignore
                task_id=context.task_id,  # type: ignore
                artifact=new_text_artifact(
                    name='current_result',
                    text=event['content'],
                ),
            )
            await event_queue.enqueue_event(message)

            # 스트리밍 완료 확인
            if event['done']:
                break

        # 태스크 완료 상태 전송
        status = TaskStatusUpdateEvent(
            context_id=context.context_id,  # type: ignore
            task_id=context.task_id,  # type: ignore
            status=TaskStatus(state=TaskState.completed),
            final=True,  # 이것이 마지막 상태 업데이트임을 표시
        )
        await event_queue.enqueue_event(status)

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            context: 요청 컨텍스트. 취소할 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐. 취소 관련 이벤트 전달에 사용될 수 있습니다.

        Raises:
            Exception: 항상 발생. 취소가 지원되지 않음을 나타냅니다.
        """
        raise Exception('cancel not supported')
