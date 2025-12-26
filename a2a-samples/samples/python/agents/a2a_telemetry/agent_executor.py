"""Q&A 에이전트 실행자 모듈.

이 모듈은 Google ADK(Agent Development Kit)를 사용하여 질문에 답변하는
A2A AgentExecutor 구현을 제공합니다. Google Search 도구를 활용하여
실시간 정보를 검색하고 사용자 질문에 답변합니다.

주요 특징:
    - Google ADK 기반 LLM 에이전트 통합
    - LiteLLM을 통한 다양한 LLM 모델 지원
    - Google Search 도구 통합
    - 세션 기반 대화 관리

환경 변수:
    LITELLM_MODEL: 사용할 LLM 모델 (기본값: gemini/gemini-2.0-flash-exp)
"""
import logging
import os

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState, TextPart, UnsupportedOperationError
from a2a.utils import new_agent_text_message
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search_tool
from google.genai import types


logger = logging.getLogger(__name__)


class QnAAgentExecutor(AgentExecutor):
    """Google ADK를 사용하여 질문에 답변하는 에이전트 실행자.

    이 클래스는 A2A AgentExecutor 인터페이스를 구현하여 Google ADK 기반의
    Q&A 에이전트를 A2A 프로토콜과 연결합니다. Google Search 도구를 활용하여
    실시간 정보를 검색하고 사용자 질문에 답변합니다.

    Attributes:
        agent: LlmAgent 인스턴스. Google Search 도구가 장착된 LLM 에이전트.
        runner: Runner 인스턴스. 에이전트 실행 및 세션 관리를 담당.

    Note:
        에이전트와 러너는 첫 번째 요청 시 지연 초기화(lazy initialization)됩니다.
        이는 시작 시간을 단축하고 환경 변수 로딩을 보장합니다.
    """

    def __init__(self) -> None:
        """QnAAgentExecutor 인스턴스를 초기화합니다.

        에이전트와 러너는 None으로 초기화되며, 첫 번째 execute() 호출 시
        _init_agent() 메서드를 통해 실제로 생성됩니다.
        """
        self.agent = None
        self.runner = None

    def _init_agent(self) -> None:
        """LLM 에이전트와 러너를 초기화합니다.

        LITELLM_MODEL 환경 변수에서 모델명을 읽어오고, Google Search 도구를
        장착한 LlmAgent를 생성합니다. 세션, 아티팩트, 메모리 서비스는
        모두 인메모리 구현을 사용합니다.

        Note:
            이 메서드는 execute()에서 self.agent가 None일 때 자동으로 호출됩니다.
        """
        # 환경 변수에서 LLM 모델 설정 (기본값: gemini/gemini-2.0-flash-exp)
        LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini/gemini-2.0-flash-exp')

        # LLM 에이전트 생성: Google Search 도구를 사용하여 질문에 답변
        self.agent = LlmAgent(
            model=LiteLlm(model=LITELLM_MODEL),
            name='question_answer_agent',
            description='A helpful assistant agent that can answer questions.',
            instruction="""Respond to the query using google search""",
            tools=[google_search_tool.google_search],
        )

        # 에이전트 러너 생성: 세션, 아티팩트, 메모리 서비스 설정
        self.runner = self.runner = Runner(
            app_name=self.agent.name,
            agent=self.agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            context: 요청 컨텍스트. 취소할 태스크 정보를 포함.
            event_queue: 이벤트 큐. 취소 이벤트 전달에 사용.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생. 취소 미지원을 나타냄.
        """
        raise ServerError(error=UnsupportedOperationError())

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 질문을 처리하고 Google Search를 통해 답변합니다.

        이 메서드는 A2A 서버가 메시지를 수신할 때 호출됩니다.
        Google ADK 에이전트를 사용하여 질문에 답변하고,
        실시간으로 작업 상태를 업데이트합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 태스크 ID, 컨텍스트 ID 등을 포함.
            event_queue: 이벤트 큐. 응답 메시지와 상태 업데이트를 클라이언트에 전달.

        처리 흐름:
            1. 에이전트가 초기화되지 않았으면 초기화
            2. 사용자 입력 추출 및 태스크 상태 업데이트
            3. 세션 조회 또는 생성
            4. ADK 에이전트 실행 및 스트리밍 응답 처리
            5. 최종 응답을 아티팩트로 저장하고 태스크 완료
        """
        # 에이전트가 아직 초기화되지 않았으면 초기화
        if self.agent is None:
            self._init_agent()
        logger.debug(f'Executing agent {self.agent.name}')

        # 사용자 입력 추출
        query = context.get_user_input()

        # 태스크 상태 업데이트를 위한 TaskUpdater 생성
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # 새 태스크인 경우 제출
        if not context.current_task:
            await updater.submit()

        # 작업 시작 상태로 전환
        await updater.start_work()

        # 사용자 메시지를 ADK Content 형식으로 변환
        content = types.Content(role='user', parts=[types.Part(text=query)])

        # 기존 세션 조회 또는 새 세션 생성
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name,
            user_id='123',
            session_id=context.context_id,
        ) or await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id='123',
            session_id=context.context_id,
        )

        # ADK 에이전트 실행 및 스트리밍 응답 처리
        async for event in self.runner.run_async(
            session_id=session.id, user_id='123', new_message=content
        ):
            logger.debug(f'Event from ADK {event}')

            # 최종 응답인 경우 아티팩트로 저장하고 완료
            if event.is_final_response():
                parts = event.content.parts
                text_parts = [
                    TextPart(text=part.text) for part in parts if part.text
                ]
                await updater.add_artifact(
                    text_parts,
                    name='result',
                )
                await updater.complete()
                break

            # 중간 상태: 작업 진행 중 알림
            await updater.update_status(
                TaskState.working, message=new_agent_text_message('Working...')
            )
        else:
            # for 루프가 break 없이 종료된 경우 (에이전트 실패)
            logger.debug('Agent failed to complete')
            await updater.update_status(
                TaskState.failed,
                message=new_agent_text_message(
                    'Failed to generate a response.'
                ),
            )
