"""프로토콜 래퍼 모듈.

에이전트 코드가 비즈니스 로직에 집중할 수 있도록
A2A SDK 타입을 래핑하는 헬퍼 함수들입니다.

주요 기능:
    - send_text: 텍스트 메시지를 에이전트에 전송
    - send_text_async: 비동기 텍스트 메시지 전송
    - send_followup: 후속 메시지 전송
    - cancel_task: 태스크 취소 요청
    - extract_text: Task 또는 Message에서 텍스트 추출
"""

from __future__ import annotations

import asyncio
import uuid

from a2a.client import ClientConfig, ClientFactory, minimal_agent_card
from a2a.client.client_task_manager import ClientTaskManager
from a2a.types import Message, Role, Task, TaskIdParams, TextPart
from a2a.utils.message import get_message_text


__all__ = [
    'cancel_task',
    'extract_text',
    'send_followup',
    'send_text',
    'send_text_async',
]


# ---------------------------------------------------------------------------
# 클라이언트 헬퍼 (Bob 등)
# ---------------------------------------------------------------------------


_client_factory = ClientFactory(ClientConfig())


async def send_text_async(
    port: int,
    text: str,
    *,
    context_id: str | None = None,
    reference_task_ids: list[str] | None = None,
    task_id: str | None = None,
):
    """A2A ``message/send`` 연산을 통해 *text*를 대상 에이전트에 전송합니다.

    Args:
        port: 대상 에이전트가 리스닝하는 TCP 포트.
        text: 일반 텍스트 메시지로 전송할 페이로드.
        context_id: 멀티턴 상태를 유지하기 위한 선택적 대화 컨텍스트 ID.
        reference_task_ids: 이 메시지가 응답하는 태스크 ID들의 선택적 리스트.
        task_id: 재사용할 명시적 태스크 ID (후속 시나리오).

    Returns:
        Task | Message: 에이전트가 생성한 최종 객체—일반적으로 ``Task``이지만
            매우 작은 상호작용의 경우 일반 ``Message``일 수 있습니다.
    """
    client = _client_factory.create(
        minimal_agent_card(f'http://localhost:{port}/a2a/v1')
    )
    msg = Message(
        kind='message',
        role=Role.user,
        message_id=uuid.uuid4().hex,
        context_id=context_id,
        reference_task_ids=reference_task_ids or [],
        parts=[TextPart(text=text)],
        task_id=task_id,
    )

    task_manager = ClientTaskManager()
    last_message: Message | None = None

    async for event in client.send_message(msg):  # type: ignore[attr-defined]
        # 전송 구현에서 튜플 언래핑
        if isinstance(event, tuple):
            event = event[0]
        # SDK 태스크 매니저가 상태 집계를 처리하도록 함
        await task_manager.process(event)
        if isinstance(event, Message):
            last_message = event

    task = task_manager.get_task()
    if task:
        return task
    if last_message is not None:
        return last_message
    raise RuntimeError('No response from agent')


def send_text(
    port: int,
    text: str,
    *,
    context_id: str | None = None,
    reference_task_ids: list[str] | None = None,
    task_id: str | None = None,
):
    """:func:`send_text_async`에 위임하는 동기 헬퍼.

    이 헬퍼는 호출자가 이미 이벤트 루프 내에서 실행 중인지
    (예: Jupyter 노트북이나 다른 async 프레임워크 내부) 투명하게 감지하고
    적절한 실행 전략을 선택합니다.

    Args:
        port: 대상 에이전트가 리스닝하는 TCP 포트.
        text: 일반 텍스트 메시지로 전송할 페이로드.
        context_id: 선택적 대화 컨텍스트 ID.
        reference_task_ids: 이 메시지가 응답하는 태스크 ID들의 선택적 리스트.
        task_id: 재사용할 명시적 태스크 ID (후속 시나리오).

    Returns:
        Task | Message: :func:`send_text_async` 참조.
    """
    try:
        return asyncio.run(
            send_text_async(
                port,
                text,
                context_id=context_id,
                reference_task_ids=reference_task_ids,
                task_id=task_id,
            )
        )
    except RuntimeError:
        # 기존 실행 중인 루프 내에서 호출된 경우 폴백 (예: Jupyter)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return loop.run_until_complete(
                send_text_async(
                    port,
                    text,
                    context_id=context_id,
                    reference_task_ids=reference_task_ids,
                    task_id=task_id,
                )
            )
        raise


def send_followup(
    port: int,
    resp_task: Task,
    text: str,
):
    """기존 대화 컨텍스트와 태스크 식별자를 유지하면서
    *text* 후속 메시지를 보내는 편의 헬퍼.

    Args:
        port: 대상 에이전트의 리스닝 포트.
        resp_task: 후속 메시지를 보내려는 원본 Task.
        text: 후속 메시지의 일반 텍스트 내용.

    Returns:
        Task | Message: 에이전트가 반환한 결과 SDK 객체 (일반적으로 Task).
    """
    return send_text(
        port,
        text,
        context_id=resp_task.context_id,
        reference_task_ids=[resp_task.id],
        task_id=resp_task.id,
    )


# ---------------------------------------------------------------------------
# cancel_task 헬퍼
# ---------------------------------------------------------------------------


async def _cancel_task_async(port: int, task_id: str) -> None:
    """원격 에이전트에 태스크 취소를 비동기로 요청합니다.

    Args:
        port: 대상 에이전트의 TCP 포트.
        task_id: 취소할 태스크 식별자.
    """
    client = _client_factory.create(
        minimal_agent_card(f'http://localhost:{port}/a2a/v1')
    )
    await client.cancel_task(TaskIdParams(id=task_id))


def cancel_task(port: int, task_id: str) -> None:
    """원격 에이전트에 *task_id* 취소를 동기적으로 요청합니다.

    이 래퍼는 호출자가 이미 이벤트 루프 내에 있을 수 있는
    일반적인 경우를 처리하면서 :func:`_cancel_task_async`를 실행합니다.

    Args:
        port: 대상 에이전트에 도달할 수 있는 TCP 포트.
        task_id: 취소할 태스크의 식별자.
    """
    try:
        asyncio.run(_cancel_task_async(port, task_id))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_until_complete(_cancel_task_async(port, task_id))
        else:
            raise


# ---------------------------------------------------------------------------
# 편의 추출 헬퍼
# ---------------------------------------------------------------------------


def extract_text(obj: Task | Message) -> str:
    """Task 또는 Message에서 일반 텍스트를 반환합니다.

    가능한 경우 SDK 헬퍼를 사용합니다.

    Args:
        obj: Task 또는 Message 객체.

    Returns:
        str: 추출된 텍스트. 추출할 수 없는 경우 빈 문자열.
    """
    if isinstance(obj, Message):
        return get_message_text(obj)

    if isinstance(obj, Task) and obj.artifacts:
        # 최신 아티팩트/파트 (끝)를 선호하지만 우아하게 폴백
        for artifact in reversed(obj.artifacts):
            if artifact.parts:
                for part in reversed(artifact.parts):
                    if hasattr(part, 'root') and hasattr(part.root, 'text'):
                        return part.root.text  # type: ignore[attr-defined]
    return ''
