"""Google ADK 에이전트 실행자 모듈.

이 모듈은 Google ADK(Agent Development Kit) 에이전트를 A2A 프로토콜과
연결하는 범용 AgentExecutor 구현을 제공합니다.

클래스:
    ADKAgentExecutor: ADK 에이전트를 A2A와 연결하는 래퍼
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Part,
    TaskState,
    TextPart,
)
from a2a.utils import new_agent_text_message, new_task
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


class ADKAgentExecutor(AgentExecutor):
    """Google ADK 에이전트를 위한 범용 AgentExecutor 구현.

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    ADK 에이전트를 A2A 서버와 연결합니다. ADK Runner를 사용하여
    에이전트를 실행하고 응답을 아티팩트로 반환합니다.

    Attributes:
        agent: ADK Agent 인스턴스.
        status_message: 처리 중 표시할 상태 메시지.
        artifact_name: 응답 아티팩트 이름.
        runner: ADK Runner 인스턴스. 에이전트 실행을 관리합니다.
    """

    def __init__(
        self,
        agent,
        status_message: str = "Processing request...",
        artifact_name: str = "response",
    ) -> None:
        """ADKAgentExecutor 인스턴스를 초기화합니다.

        ADK Runner를 설정하여 에이전트 실행 환경을 구성합니다.
        인메모리 서비스(아티팩트, 세션, 메모리)를 사용합니다.

        Args:
            agent: ADK Agent 인스턴스.
            status_message: 처리 중 표시할 메시지 (기본값: "Processing request...").
            artifact_name: 응답 아티팩트 이름 (기본값: "response").
        """
        self.agent = agent
        self.status_message = status_message
        self.artifact_name = artifact_name

        # ADK Runner 설정
        # 인메모리 서비스를 사용하여 간단한 실행 환경 구성
        self.runner = Runner(
            app_name=agent.name,
            agent=agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """태스크 취소 요청을 처리합니다.

        ADK 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.

        Raises:
            NotImplementedError: 항상 발생. 취소가 지원되지 않습니다.
        """
        raise NotImplementedError(
            "Cancellation is not implemented for ADKAgentExecutor."
        )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 ADK 에이전트를 실행합니다.

        ADK Runner를 통해 에이전트를 실행하고, 최종 응답을
        아티팩트로 저장합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 태스크 ID 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 태스크 상태와 아티팩트를 클라이언트에 전달합니다.

        처리 흐름:
            1. 사용자 입력 및 태스크 추출
            2. 'working' 상태로 업데이트
            3. ADK 세션 생성 및 에이전트 실행
            4. 최종 응답을 아티팩트로 저장
            5. 태스크 완료 처리
        """
        # 사용자 입력 추출
        query = context.get_user_input()
        task = context.current_task or new_task(context.message)
        await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        # 사용자 ID 추출 (인증 컨텍스트가 있으면 사용)
        if context.call_context:
            user_id = context.call_context.user.user_name
        else:
            user_id = "a2a_user"

        try:
            # 처리 중 상태 업데이트
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(self.status_message, task.context_id, task.id),
            )

            # ADK 세션 생성
            session = await self.runner.session_service.create_session(
                app_name=self.agent.name,
                user_id=user_id,
                state={},
                session_id=task.context_id,
            )

            # 사용자 메시지를 ADK Content 형식으로 변환
            content = types.Content(
                role="user", parts=[types.Part.from_text(text=query)]
            )

            # ADK 에이전트 비동기 실행
            response_text = ""
            async for event in self.runner.run_async(
                user_id=user_id, session_id=session.id, new_message=content
            ):
                # 최종 응답만 수집
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            response_text += part.text + "\n"
                        elif hasattr(part, "function_call"):
                            # 함수 호출은 ADK 내부에서 처리됨
                            pass

            # 응답을 아티팩트로 저장
            await updater.add_artifact(
                [Part(root=TextPart(text=response_text))],
                name=self.artifact_name,
            )

            # 태스크 완료
            await updater.complete()

        except Exception as e:
            # 오류 발생 시 실패 상태로 업데이트
            await updater.update_status(
                TaskState.failed,
                new_agent_text_message(f"Error: {e!s}", task.context_id, task.id),
                final=True,
            )
