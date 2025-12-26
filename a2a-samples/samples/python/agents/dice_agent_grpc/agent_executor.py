"""주사위 에이전트 실행자 모듈 (gRPC 버전).

이 모듈은 DiceAgent를 A2A gRPC 프로토콜과 연결하는 AgentExecutor 구현을 제공합니다.
스트리밍 응답을 지원하며, 작업 진행 상태를 실시간으로 업데이트합니다.

클래스:
    DiceAgentExecutor: A2A AgentExecutor 인터페이스를 구현하는 주사위 에이전트 래퍼
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from agent import DiceAgent


class DiceAgentExecutor(AgentExecutor):
    """주사위 에이전트를 위한 AgentExecutor 구현 (gRPC 버전).

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    DiceAgent를 gRPC 기반 A2A 서버와 연결합니다. 스트리밍 응답을 처리하고
    작업 상태를 실시간으로 클라이언트에 전달합니다.

    Attributes:
        agent: DiceAgent 인스턴스. 주사위 굴리기 및 소수 판별 로직을 수행합니다.
    """

    def __init__(self) -> None:
        """DiceAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 DiceAgent 인스턴스를 생성하여 저장합니다.
        """
        self.agent = DiceAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 주사위 굴리기 또는 소수 판별을 수행합니다.

        이 메서드는 스트리밍 방식으로 응답을 처리합니다. DiceAgent로부터
        스트림 이벤트를 수신하여 작업 진행 상태를 실시간으로 업데이트하고,
        최종 결과가 나오면 아티팩트로 저장합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 현재 태스크 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 태스크 상태 업데이트와 응답을 클라이언트에 전달합니다.

        처리 흐름:
            1. 사용자 입력 추출
            2. 태스크가 없으면 새로 생성
            3. DiceAgent 스트리밍 호출
            4. 중간 상태는 'working'으로 업데이트
            5. 최종 결과는 아티팩트로 저장하고 완료 처리
        """
        # 사용자 입력 추출
        query = context.get_user_input()
        task = context.current_task

        # 이 에이전트는 항상 Task 객체를 생성합니다.
        # 현재 요청에 태스크가 없으면 새로 생성하여 사용합니다.
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # 기본 에이전트를 스트리밍 모드로 호출합니다.
        # 스트림은 현재 업데이트 이벤트로 처리됩니다.
        async for finished, text in self.agent.stream(query, task.context_id):
            if not finished:
                # 아직 완료되지 않음: 작업 진행 중 상태로 업데이트
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(text, task.context_id, task.id),
                )
                continue

            # 완료됨: 적절한 이벤트 발생
            await updater.add_artifact(
                [Part(root=TextPart(text=text))],
                name='response',
            )
            await updater.complete()
            break

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            request: 요청 컨텍스트. 취소할 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐. 취소 관련 이벤트 전달에 사용될 수 있습니다.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생. 취소 미지원을 나타냅니다.
        """
        raise ServerError(error=UnsupportedOperationError())
