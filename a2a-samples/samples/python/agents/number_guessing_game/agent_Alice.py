"""에이전트 Alice - 숫자 맞추기 게임의 평가자.

이 에이전트는 프로세스 시작 시 1과 100 사이의 비밀 정수를 선택하고,
A2A `message/send` 연산을 통해 전송된 추측을 평가합니다.
각 추측에 대해 다음 힌트 중 하나로 응답합니다:

* ``"Go higher"`` – 추측이 비밀 숫자보다 낮음.
* ``"Go lower"``  – 추측이 비밀 숫자보다 높음.
* ``"correct! attempts: <n>"`` – 정답! ``n``은 시도 횟수.

이 모듈은 단일 공개 호출 가능한 :pyfunc:`alice_handler`를 제공하며,
이는 :pyfunc:`utils.server.run_agent_blocking`을 사용하여 A2A SDK 서버
스택을 통해 실행되고 ``__main__`` 블록에서 시작된 HTTP 서버 내에서 동작합니다.

에이전트는 공식 A2A Python SDK와 작은 헬퍼 레이어를 사용하여 구현되었으며,
코드는 프로토콜 배관보다 게임 로직에 집중합니다.

서버 포트:
    기본 포트: 8001

실행 방법:
    python agent_Alice.py
"""

import uuid

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCard, Part, TextPart
from a2a.utils.message import get_message_text
from config import AGENT_ALICE_PORT
from utils.game_logic import process_guess
from utils.server import run_agent_blocking


# ------------------ 에이전트 카드 ------------------

alice_skills = [
    {
        'id': 'number_guess_evaluator',
        'name': 'Number Guess Evaluator',
        'description': 'Evaluates numeric guesses (1-100) against a secret number and replies with guidance (higher/lower/correct).',
        'tags': ['game', 'demo'],
        'inputModes': ['text/plain'],
        'outputModes': ['text/plain'],
        'examples': ['50'],
    }
]

alice_card_dict = {
    'name': 'AgentAlice',
    'description': 'Hosts the number-guessing game by picking a secret number and grading guesses.',
    'url': f'http://localhost:{AGENT_ALICE_PORT}/a2a/v1',
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
    'skills': alice_skills,
}
alice_card = AgentCard.model_validate(alice_card_dict)

# ------------------ 내부 헬퍼 ------------------


class NumberGuessExecutor(AgentExecutor):
    """숫자 맞추기 로직을 직접 구현하는 AgentExecutor.

    비밀 숫자와 사용자 추측을 비교하여 힌트를 제공합니다.
    """

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """피어 에이전트로부터 수신한 새 메시지를 처리합니다.

        사용자의 추측을 평가하고 적절한 힌트를 아티팩트로 반환합니다.

        Args:
            context: 요청 컨텍스트. 메시지와 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐. 응답을 전달합니다.
        """
        raw_text = get_message_text(context.message) if context.message else ''
        response_text = process_guess(raw_text)

        updater = TaskUpdater(
            event_queue,
            task_id=context.task_id or str(uuid.uuid4()),
            context_id=context.context_id or str(uuid.uuid4()),
        )
        # 클라이언트에게 태스크 시작을 알리고, 답변을 발행한 다음,
        # 완료로 표시하여 Bob이 아티팩트가 첨부된 전체 Task 객체를 볼 수 있도록 함
        await updater.submit()
        await updater.add_artifact([Part(root=TextPart(text=response_text))])
        await updater.complete()

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """참조된 태스크가 제공된 경우 거부합니다.

        Args:
            context: 요청 컨텍스트. 태스크 ID를 포함할 수 있습니다.
            event_queue: 이벤트 큐.
        """
        if context.task_id:
            updater = TaskUpdater(
                event_queue,
                task_id=context.task_id,
                context_id=context.context_id or str(uuid.uuid4()),
            )
            await updater.reject()


if __name__ == '__main__':
    run_agent_blocking(
        name='AgentAlice',
        port=AGENT_ALICE_PORT,
        agent_card=alice_card,
        executor=NumberGuessExecutor(),
    )
