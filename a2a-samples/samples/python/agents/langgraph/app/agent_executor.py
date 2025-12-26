"""통화 변환 에이전트 실행자 모듈.

이 모듈은 CurrencyAgent를 A2A 프로토콜과 연결하는 AgentExecutor 구현을 제공합니다.
스트리밍 응답과 태스크 상태 관리를 지원하며, 구조화된 응답 형식에 따라
대화 흐름을 제어합니다.

클래스:
    CurrencyAgentExecutor: A2A AgentExecutor 인터페이스를 구현하는 통화 에이전트 래퍼
"""
import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
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

from app.agent import CurrencyAgent


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CurrencyAgentExecutor(AgentExecutor):
    """통화 변환 에이전트를 위한 AgentExecutor 구현.

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    CurrencyAgent를 A2A 서버와 연결합니다. 스트리밍 응답을 처리하고
    에이전트의 구조화된 응답에 따라 태스크 상태를 관리합니다.

    Attributes:
        agent: CurrencyAgent 인스턴스. 환율 조회 로직을 수행합니다.

    태스크 상태 흐름:
        - working: 도구 호출 중 (환율 조회 중)
        - input_required: 사용자로부터 추가 정보 필요
        - completed: 요청 완료, 결과가 아티팩트로 저장됨
    """

    def __init__(self) -> None:
        """CurrencyAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 CurrencyAgent 인스턴스를 생성하여 저장합니다.
        """
        self.agent = CurrencyAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 환율 조회를 수행합니다.

        이 메서드는 스트리밍 방식으로 응답을 처리합니다. CurrencyAgent로부터
        스트림 이벤트를 수신하여 태스크 상태를 업데이트하고, 에이전트의
        구조화된 응답에 따라 최종 처리를 수행합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 현재 태스크 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 태스크 상태 업데이트와 응답을 클라이언트에 전달합니다.

        Raises:
            ServerError: InvalidParamsError - 요청 유효성 검사 실패 시.
            ServerError: InternalError - 스트리밍 응답 처리 중 오류 발생 시.

        처리 흐름:
            1. 요청 유효성 검사
            2. 태스크가 없으면 새로 생성
            3. CurrencyAgent 스트리밍 호출
            4. 중간 상태(도구 호출)는 'working'으로 업데이트
            5. 사용자 입력 필요 시 'input_required' 상태로 종료
            6. 완료 시 결과를 아티팩트로 저장
        """
        # 요청 유효성 검사
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # 사용자 입력 및 현재 태스크 추출
        query = context.get_user_input()
        task = context.current_task

        # 태스크가 없으면 새로 생성
        if not task:
            task = new_task(context.message)  # type: ignore
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            # CurrencyAgent 스트리밍 호출
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item['is_task_complete']
                require_user_input = item['require_user_input']

                if not is_task_complete and not require_user_input:
                    # 도구 호출 중: 'working' 상태로 업데이트
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(
                            item['content'],
                            task.context_id,
                            task.id,
                        ),
                    )
                elif require_user_input:
                    # 사용자 입력 필요: 'input_required' 상태로 종료
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
                else:
                    # 태스크 완료: 결과를 아티팩트로 저장하고 완료 처리
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item['content']))],
                        name='conversion_result',
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.error(f'스트리밍 응답 처리 중 오류 발생: {e}')
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """요청의 유효성을 검사합니다.

        현재 구현에서는 항상 유효한 것으로 처리합니다.

        Args:
            context: 검사할 요청 컨텍스트.

        Returns:
            bool: 유효성 검사 실패 여부. False는 유효함을 의미합니다.
        """
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            context: 요청 컨텍스트. 취소할 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐. 취소 관련 이벤트 전달에 사용될 수 있습니다.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생. 취소 미지원을 나타냅니다.
        """
        raise ServerError(error=UnsupportedOperationError())
