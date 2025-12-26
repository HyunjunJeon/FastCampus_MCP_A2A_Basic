"""차트 생성 AgentExecutor 모듈.

이 모듈은 ChartGenerationAgent를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다. 차트 이미지를 FilePart로
변환하여 클라이언트에 반환합니다.
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    FilePart,
    FileWithBytes,
    InvalidParamsError,
    Part,
    Task,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import (
    completed_task,
    new_artifact,
)
from a2a.utils.errors import ServerError
from agent import ChartGenerationAgent


class ChartGenerationAgentExecutor(AgentExecutor):
    """차트 생성 에이전트를 위한 AgentExecutor 구현.

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    ChartGenerationAgent를 A2A 서버와 연결합니다. 생성된 차트 이미지를
    FilePart로 변환하여 아티팩트로 반환합니다.

    Attributes:
        agent: ChartGenerationAgent 인스턴스. 실제 차트 생성 로직을 수행합니다.

    응답 흐름:
        1. 사용자 입력 추출
        2. ChartGenerationAgent.invoke() 호출
        3. 캐시에서 이미지 데이터 조회
        4. 이미지를 FilePart로 래핑하여 아티팩트로 반환
    """

    def __init__(self) -> None:
        """ChartGenerationAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 ChartGenerationAgent 인스턴스를 생성합니다.
        """
        self.agent = ChartGenerationAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 차트를 생성합니다.

        사용자 입력을 파싱하여 차트를 생성하고, 결과 이미지를
        아티팩트로 반환합니다. 이미지 생성에 실패하면 오류 메시지를
        텍스트로 반환합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 세션 ID 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 완료된 태스크를 클라이언트에 전달합니다.

        Raises:
            ServerError: 요청 유효성 검사 실패 또는 에이전트 호출 오류 시.
        """
        # 요청 유효성 검사
        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        # 사용자 입력 추출 및 에이전트 호출
        query = context.get_user_input()
        try:
            result = self.agent.invoke(query, context.context_id)
        except Exception as e:
            raise ServerError(
                error=ValueError(f'Error invoking agent: {e}')
            ) from e

        # 캐시에서 이미지 데이터 조회
        data = self.agent.get_image_data(
            session_id=context.context_id, image_key=result.raw
        )

        # 이미지 데이터 유효성에 따라 응답 구성
        if data and not data.error:
            # 성공: 이미지를 FilePart로 래핑
            parts = [
                Part(
                    root=FilePart(
                        file=FileWithBytes(
                            bytes=data.bytes,
                            mime_type=data.mime_type,
                            name=data.name,
                        )
                    )
                )
            ]

        else:
            # 실패: 오류 메시지를 TextPart로 래핑
            parts = [
                Part(
                    root=TextPart(
                        text=data.error
                        if data
                        else 'Failed to generate chart image.'
                    ),
                )
            ]

        # 완료된 태스크를 이벤트 큐에 추가
        await event_queue.enqueue_event(
            completed_task(
                context.task_id,
                context.context_id,
                [new_artifact(parts, f'chart_{context.task_id}')],
                [context.message],
            )
        )

    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            request: 요청 컨텍스트. 취소할 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생.
        """
        raise ServerError(error=UnsupportedOperationError())

    def _validate_request(self, context: RequestContext) -> bool:
        """요청의 유효성을 검사합니다.

        현재 구현에서는 항상 유효한 것으로 처리합니다.

        Args:
            context: 검사할 요청 컨텍스트.

        Returns:
            bool: 유효성 검사 실패 여부. False는 유효함을 의미합니다.
        """
        return False
