"""VEO 비디오 생성 AgentExecutor 모듈.

이 모듈은 VideoGenerationAgent를 A2A 프로토콜과 연결하는
AgentExecutor 구현을 제공합니다. 비디오 생성 진행률을
스트리밍하고 결과를 아티팩트로 반환합니다.
"""
import logging

from typing import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    FilePart,
    FileWithUri,
    Part,
    Task,
    TaskState,
    UnsupportedOperationError,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from agent import VideoGenerationAgent


logger = logging.getLogger(__name__)


class VideoGenerationAgentExecutor(AgentExecutor):
    """VEO 비디오 생성 에이전트를 위한 AgentExecutor 구현.

    이 클래스는 A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    VideoGenerationAgent를 A2A 서버와 연결합니다. 비디오 생성 진행률을
    스트리밍하고 완료된 비디오를 FileWithUri 아티팩트로 반환합니다.

    Attributes:
        agent: VideoGenerationAgent 인스턴스. VEO 모델을 사용한 비디오 생성.
    """

    def __init__(self) -> None:
        """VideoGenerationAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 VideoGenerationAgent 인스턴스를 생성합니다.
        """
        self.agent = VideoGenerationAgent()

    @override
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리하고 비디오 생성을 시작합니다.

        VideoGenerationAgent.stream()을 호출하여 비디오 생성을 시작하고,
        진행률 업데이트를 스트리밍합니다. 완료되면 비디오 URL을
        FilePart 아티팩트로 반환합니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력, 태스크 ID 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 진행률 업데이트와 아티팩트를 클라이언트에 전달합니다.

        처리 흐름:
            1. 사용자 입력 추출 및 태스크 생성
            2. VideoGenerationAgent.stream() 호출
            3. 진행률 업데이트 스트리밍
            4. 완료 시 비디오 URL을 아티팩트로 추가
            5. 태스크 완료 처리
        """
        # 사용자 입력 추출
        query = context.get_user_input()
        if not query:
            logger.warning('No user input found in context.')
            return

        # 태스크 생성 또는 기존 태스크 사용
        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        logger.info(
            f"Executing VideoGenerationAgent for task {task.id} with query: '{query}'"
        )

        # VideoGenerationAgent 스트리밍 처리
        async for item in self.agent.stream(query, task.context_id):
            progress_percent = item.get('progress_percent')
            progress_float = (
                float(progress_percent / 100.0)
                if progress_percent is not None
                else None
            )

            # 진행 중인 경우: 상태 업데이트
            if not item.get('is_task_complete', False):
                updates_text = item.get('updates', 'Processing...')
                progress_percent = item.get('progress_percent')
                progress_float = (
                    float(progress_percent / 100.0)
                    if progress_percent is not None
                    else None
                )

                agent_update_message = new_agent_text_message(
                    updates_text, task.context_id, task.id
                )

                logger.debug(
                    f'Task {task.id}: Updating status to WORKING. '
                    f"message_text='{updates_text}', "
                    f'intended_progress_float={progress_float * 100 if progress_float is not None else "N/A"} (note: progress arg not supported by update_status in this SDK version)'
                )
                try:
                    await updater.update_status(
                        TaskState.working, message=agent_update_message
                    )
                    logger.debug(
                        f'Task {task.id}: Successfully called updater.update_status(TaskState.working).'
                    )

                except Exception as e_update:
                    logger.error(
                        f'Task {task.id}: ERROR during updater.update_status: {e_update}',
                        exc_info=True,
                    )
                    raise
                continue

            # 완료된 경우: 최종 결과 처리
            logger.info(
                f'Task {task.id} marked complete by agent. Item: {item}'
            )
            final_message_text = item.get(
                'final_message_text', item.get('content', 'Task finished.')
            )
            final_message_obj = new_agent_text_message(
                final_message_text, task.context_id, task.id
            )

            # 비디오 파일이 있는 경우: FilePart 아티팩트로 추가
            if 'file_part_data' in item:
                file_data = item['file_part_data']

                artifact_name = item.get('artifact_name', 'generated_video')
                # MIME 타입에서 확장자 추출하여 아티팩트 이름에 추가
                if '.' not in artifact_name and 'mimeType' in file_data:
                    extension = file_data['mimeType'].split('/')[-1]
                    if extension and len(extension) < 5:
                        artifact_name = f'{artifact_name}.{extension}'

                # FileWithUri로 비디오 파일 래핑
                file_with_uri = FileWithUri(
                    uri=file_data['uri'],
                    mime_type=file_data['mimeType'],
                    name=artifact_name,
                )
                video_file_part = FilePart(
                    file=file_with_uri,
                )

                logger.info(
                    f'Task {task.id} completed with file. Artifact: {artifact_name}, URI: {file_data["uri"]}'
                )
                await updater.add_artifact([Part(root=video_file_part)])
                await updater.complete(final_message_obj)

            else:
                # 파일 없음: 텍스트 기반 완료 (오류 또는 정보성 메시지)
                is_error = item.get('is_error', False)
                final_task_state = (
                    TaskState.failed if is_error else TaskState.completed
                )
                logger.info(
                    f'Task {task.id} completed text-based. State: {final_task_state}, Message: {final_message_text}'
                )

                await updater.update_status(
                    final_task_state,
                    final_message_obj,
                    final=True,  # 태스크 완료/실패 표시
                )
            break  # 첫 번째 최종 항목 후 처리 중단

    @override
    async def cancel(
        self, request: RequestContext, event_queue: EventQueue
    ) -> Task | None:
        """태스크 취소 요청을 처리합니다.

        VEO 작업은 API를 통해 취소 가능할 수 있지만,
        이 구현에서는 지원하지 않습니다.

        Args:
            request: 요청 컨텍스트.
            event_queue: 이벤트 큐.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생.
        """
        logger.warning(
            f'Cancel operation requested for task {request.current_task.id if request.current_task else "unknown"}. Not supported by this agent version.'
        )
        raise ServerError(
            error=UnsupportedOperationError(
                message='Video generation cancellation is not supported.'
            )
        )
