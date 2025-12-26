"""에이전트 Carol - Bob의 추측 히스토리를 시각화하거나 셔플하는 헬퍼 에이전트.

Carol은 AgentBob으로부터 일반 텍스트 JSON 페이로드를 받아 요청에 따라
(1) 지금까지의 추측에 대한 사람이 읽을 수 있는 테이블 또는
(2) 항목이 무작위로 셔플된 JSON 리스트를 반환합니다.
이 기능은 A2A 메시지 흐름에 집중하기 위해 의도적으로 단순하게 구현되었습니다.

주요 기능:
    - 추측 히스토리 시각화: 테이블 형식으로 출력
    - 추측 히스토리 셔플: 무작위 순서로 섞기

서버 포트:
    기본 포트: 8003

실행 방법:
    python agent_Carol.py
"""

import json
import random
import uuid

from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCard, Part, TextPart
from a2a.utils.message import get_message_text
from config import AGENT_CAROL_PORT
from utils import try_parse_json
from utils.game_logic import process_history_payload
from utils.server import run_agent_blocking


# ------------------ 에이전트 카드 ------------------

carol_skills = [
    {
        'id': 'history_visualiser',
        'name': 'Guess History Visualiser',
        'description': 'Generates a formatted text summary of guess/response history to aid the player.',
        'tags': ['visualisation', 'demo'],
        'inputModes': ['text/plain'],
        'outputModes': ['text/plain'],
        'examples': ['[{"guess": 25, "response": "Go higher"}]'],
    },
    {
        'id': 'history_shuffler',
        'name': 'Guess History Shuffler',
        'description': 'Randomly shuffles the order of guess/response entries in a provided history list and returns JSON.',
        'tags': ['shuffling', 'demo'],
        'inputModes': ['text/plain'],
        'outputModes': ['text/plain'],
        'examples': [
            '{"action": "shuffle", "history": [{"guess": 25, "response": "Go higher"}]}'
        ],
    },
]

carol_card = AgentCard.model_validate(
    {
        'name': 'AgentCarol',
        'description': 'Visualises the history of guesses and hints from AgentAlice in a readable table format.',
        'url': f'http://localhost:{AGENT_CAROL_PORT}/a2a/v1',
        'preferredTransport': 'JSONRPC',
        'protocolVersion': '0.3.0',
        'version': '1.0.0',
        'capabilities': {
            'streaming': False,
            'pushNotifications': False,
            'stateTransitionHistory': False,
        },
        'defaultInputModes': ['text/plain'],
        'defaultOutputModes': ['text/plain'],
        'skills': carol_skills,
    }
)

# ------------------ SDK AgentExecutor 구현 ------------------


class HistoryHelperExecutor(AgentExecutor):
    """Carol의 시각화/셔플 기능을 구현하는 AgentExecutor.

    히스토리 리스트를 시각화하거나 셔플하는 요청을 처리합니다.
    멀티턴 대화를 지원하여 Bob과의 협상을 가능하게 합니다.

    Attributes:
        _last_history: 마지막으로 처리한 히스토리 리스트 (재셔플용).
    """

    @staticmethod
    def _print_guesses(label: str, history: list[dict[str, Any]]) -> None:
        """유틸리티: 디버깅을 위해 *history*의 숫자 추측만 출력합니다.

        Args:
            label: 출력 레이블.
            history: 추측 히스토리 리스트.
        """
        try:
            guesses = [int(item.get('guess', '?')) for item in history]
        except Exception:
            guesses = []
        print(f'[Carol] {label}: {guesses}')

    def __init__(self) -> None:
        """HistoryHelperExecutor 인스턴스를 초기화합니다.

        후속 요청에서 재셔플할 수 있도록 마지막 히스토리 리스트를 저장합니다.
        """
        self._last_history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    async def _handle_followup(
        self, context: RequestContext, raw_text: str, event_queue: EventQueue
    ) -> None:
        """기존 태스크를 참조하는 후속 메시지를 처리합니다.

        "Well done"으로 시작하면 태스크를 완료하고,
        그 외의 경우 다시 셔플하여 추가 입력을 요청합니다.

        Args:
            context: 요청 컨텍스트.
            raw_text: 메시지 텍스트.
            event_queue: 이벤트 큐.
        """
        task_id = context.task_id or (
            context.message.reference_task_ids[0]  # type: ignore[index]
            if context.message and context.message.reference_task_ids
            else str(uuid.uuid4())
        )
        updater = TaskUpdater(
            event_queue,
            task_id=task_id,
            context_id=context.context_id or str(uuid.uuid4()),
        )

        if raw_text.lower().startswith('well done'):
            print('[Carol] Received well done – completing task')
            await updater.complete()
            return

        # 그 외 텍스트 → 다시 셔플하고 추가 입력 요청
        print('[Carol] Shuffling again and returning list')
        random.shuffle(self._last_history)
        # Bob에게 보내기 전 디버그 출력
        self._print_guesses('Shuffled list', self._last_history)
        response_text = json.dumps(self._last_history)
        await updater.add_artifact([Part(root=TextPart(text=response_text))])
        # 추가 입력 요청 및 이 호출의 마지막 이벤트임을 표시
        await updater.requires_input(final=True)

    async def _handle_initial(
        self, raw_text: str, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """새 대화의 첫 번째 메시지를 처리합니다.

        요청 유형에 따라 시각화 또는 셔플 응답을 생성합니다.

        Args:
            raw_text: 메시지 텍스트.
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.
        """
        response_text = (
            process_history_payload(raw_text) if raw_text else 'Invalid input.'
        )

        # 나중에 다시 셔플할 수 있도록 히스토리 리스트 저장
        success, parsed = try_parse_json(raw_text)
        if (
            success
            and isinstance(parsed, dict)
            and parsed.get('action') == 'shuffle'
        ):
            hist = parsed.get('history', [])
            if isinstance(hist, list):
                self._last_history = hist

        task_id = context.task_id or str(uuid.uuid4())
        updater = TaskUpdater(
            event_queue,
            task_id=task_id,
            context_id=context.context_id or str(uuid.uuid4()),
        )
        # 초기 응답 전송 전 디버그 출력
        try:
            if success and isinstance(parsed, list):
                self._print_guesses('Initial list', parsed)
            else:
                self._print_guesses('Initial list', self._last_history)
        except Exception:
            pass
        await updater.add_artifact([Part(root=TextPart(text=response_text))])
        # Bob에게 추가 입력 요청
        await updater.requires_input(final=True)

    # ------------------------------------------------------------------
    # AgentExecutor 인터페이스
    # ------------------------------------------------------------------

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """수신 메시지를 처리하고 적절한 핸들러로 디스패치합니다.

        후속 메시지인지 초기 메시지인지 판별하여 해당 핸들러를 호출합니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.
        """
        raw_text = get_message_text(context.message) if context.message else ''
        is_followup = bool(
            context.message and context.message.reference_task_ids
        )

        if is_followup:
            await self._handle_followup(context, raw_text, event_queue)
        else:
            await self._handle_initial(raw_text, context, event_queue)

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """피어 에이전트의 명시적 요청에 따라 진행 중인 태스크를 취소합니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.
        """
        if context.task_id:
            print(
                f'[Carol] Task {context.task_id} canceled on request of peer agent'
            )
            updater = TaskUpdater(
                event_queue,
                task_id=context.task_id,
                context_id=context.context_id or str(uuid.uuid4()),
            )
            await updater.cancel()


if __name__ == '__main__':
    run_agent_blocking(
        name='AgentCarol',
        port=AGENT_CAROL_PORT,
        agent_card=carol_card,
        executor=HistoryHelperExecutor(),
    )
