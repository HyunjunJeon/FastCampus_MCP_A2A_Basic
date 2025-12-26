"""날씨 에이전트 AgentExecutor 모듈.

이 모듈은 ADK 기반 날씨 에이전트를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다.

주요 기능:
    - ADK Runner를 통한 날씨 쿼리 처리
    - 세션 관리 (생성/조회)
    - 스트리밍 응답 지원
    - Part 타입 변환 (A2A ↔ GenAI)
"""
import logging

from typing import TYPE_CHECKING

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCard,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError
from google.adk import Runner
from google.genai import types


if TYPE_CHECKING:
    from google.adk.sessions.session import Session


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Constants
DEFAULT_USER_ID = 'self'


class WeatherExecutor(AgentExecutor):
    """ADK 기반 날씨 에이전트를 실행하는 AgentExecutor.

    ADK Runner를 사용하여 날씨 쿼리를 처리하고
    A2A 프로토콜 형식으로 응답합니다.
    """

    def __init__(self, runner: Runner, card: AgentCard):
        self.runner = runner
        self._card = card
        # Track active sessions for potential cancellation
        self._active_sessions: set[str] = set()

    async def _process_request(
        self,
        new_message: types.Content,
        session_id: str,
        task_updater: TaskUpdater,
    ) -> None:
        session_obj = await self._upsert_session(session_id)
        # Update session_id with the ID from the resolved session object.
        # (it may be the same as the one passed in if it already exists)
        session_id = session_obj.id

        # Track this session as active
        self._active_sessions.add(session_id)

        try:
            async for event in self.runner.run_async(
                session_id=session_id,
                user_id=DEFAULT_USER_ID,
                new_message=new_message,
            ):
                if event.is_final_response():
                    parts = [
                        convert_genai_part_to_a2a(part)
                        for part in event.content.parts
                        if (part.text or part.file_data or part.inline_data)
                    ]
                    logger.debug('Yielding final response: %s', parts)
                    await task_updater.add_artifact(parts)
                    await task_updater.update_status(
                        TaskState.completed, final=True
                    )
                    break
                if not event.get_function_calls():
                    logger.debug('Yielding update response')
                    await task_updater.update_status(
                        TaskState.working,
                        message=task_updater.new_agent_message(
                            [
                                convert_genai_part_to_a2a(part)
                                for part in event.content.parts
                                if (
                                    part.text
                                    or part.file_data
                                    or part.inline_data
                                )
                            ],
                        ),
                    )
                else:
                    logger.debug('Skipping event')
        finally:
            # Remove from active sessions when done
            self._active_sessions.discard(session_id)

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        # Run the agent until either complete or the task is suspended.
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        # Immediately notify that the task is submitted.
        if not context.current_task:
            await updater.update_status(TaskState.submitted)
        await updater.update_status(TaskState.working)
        await self._process_request(
            types.UserContent(
                parts=[
                    convert_a2a_part_to_genai(part)
                    for part in context.message.parts
                ],
            ),
            context.context_id,
            updater,
        )
        logger.debug('[weather] execute exiting')

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """주어진 컨텍스트의 실행을 취소합니다.

        현재는 취소 시도를 로깅합니다. ADK 러너가 진행 중인
        태스크의 직접 취소를 지원하지 않기 때문입니다.
        """
        session_id = context.context_id
        if session_id in self._active_sessions:
            logger.info(
                f'Cancellation requested for active weather session: {session_id}'
            )
            # TODO: Implement proper cancellation when ADK supports it
            self._active_sessions.discard(session_id)
        else:
            logger.debug(
                f'Cancellation requested for inactive weather session: {session_id}'
            )

        raise ServerError(error=UnsupportedOperationError())

    async def _upsert_session(self, session_id: str) -> 'Session':
        """세션을 조회하거나 없으면 새로 생성합니다.

        비동기 세션 서비스 메서드가 적절히 await되도록 보장합니다.
        """
        session = await self.runner.session_service.get_session(
            app_name=self.runner.app_name,
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
        )
        if session is None:
            session = await self.runner.session_service.create_session(
                app_name=self.runner.app_name,
                user_id=DEFAULT_USER_ID,
                session_id=session_id,
            )
        return session


def convert_a2a_part_to_genai(part: Part) -> types.Part:
    """A2A Part 타입을 Google Gen AI Part 타입으로 변환합니다.

    Args:
        part: 변환할 A2A Part.

    Returns:
        types.Part: 동등한 Google Gen AI Part.

    Raises:
        ValueError: 지원하지 않는 파트 타입인 경우.
    """
    part = part.root
    if isinstance(part, TextPart):
        return types.Part(text=part.text)
    if isinstance(part, FilePart):
        if isinstance(part.file, FileWithUri):
            return types.Part(
                file_data=types.FileData(
                    file_uri=part.file.uri, mime_type=part.file.mime_type
                )
            )
        if isinstance(part.file, FileWithBytes):
            return types.Part(
                inline_data=types.Blob(
                    data=part.file.bytes, mime_type=part.file.mime_type
                )
            )
        raise ValueError(f'Unsupported file type: {type(part.file)}')
    raise ValueError(f'Unsupported part type: {type(part)}')


def convert_genai_part_to_a2a(part: types.Part) -> Part:
    """Google Gen AI Part 타입을 A2A Part 타입으로 변환합니다.

    Args:
        part: 변환할 Google Gen AI Part.

    Returns:
        Part: 동등한 A2A Part.

    Raises:
        ValueError: 지원하지 않는 파트 타입인 경우.
    """
    if part.text:
        return TextPart(text=part.text)
    if part.file_data:
        return FilePart(
            file=FileWithUri(
                uri=part.file_data.file_uri,
                mime_type=part.file_data.mime_type,
            )
        )
    if part.inline_data:
        return Part(
            root=FilePart(
                file=FileWithBytes(
                    bytes=part.inline_data.data,
                    mime_type=part.inline_data.mime_type,
                )
            )
        )
    raise ValueError(f'Unsupported part type: {part}')
