"""에이전트 Bob - 숫자 맞추기 게임의 CLI 프론트엔드.

Bob은 사람 플레이어와 두 피어 에이전트 사이를 중재합니다:

* **AgentAlice** – 비밀 숫자를 가지고 추측을 평가합니다.
* **AgentCarol** – Bob의 누적 추측 히스토리에 대한 텍스트 시각화
  (및 선택적 셔플)를 생성합니다.

이 모듈은 대화형 CLI 게임을 제공하며, A2A 프로토콜을 통해
다른 에이전트들과 통신합니다.

실행 방법:
    python agent_Bob.py

Note:
    Alice와 Carol 에이전트가 먼저 실행 중이어야 합니다.
"""

from __future__ import annotations

import json
import time

from typing import Any

from a2a.types import Task, TaskState
from config import AGENT_ALICE_PORT, AGENT_CAROL_PORT
from utils.game_logic import is_sorted_history
from utils.protocol_wrappers import (
    cancel_task,
    extract_text,
    send_followup,
    send_text,
)


# ---------------------------------------------------------------------------
# 로컬 인메모리 게임 상태
# ---------------------------------------------------------------------------

game_history: list[dict[str, str]] = []

MAX_NEGOTIATION_ATTEMPTS = 400  # 무한 루프 방지를 위한 상한


def _start_shuffle_request() -> Task | None:
    """AgentCarol에게 초기 셔플 요청을 보내고 Task를 반환받습니다.

    Returns:
        Task: Carol로부터 받은 태스크 객체.
        None: Task를 받지 못한 경우.
    """
    payload = json.dumps({'action': 'shuffle', 'history': game_history})
    resp_obj = send_text(AGENT_CAROL_PORT, payload)  # type: ignore[arg-type]
    return resp_obj if isinstance(resp_obj, Task) else None


def _extract_history_from_task(resp_task: Task) -> list[Any]:
    """*resp_task*에서 JSON 디코딩된 히스토리 리스트를 반환합니다.

    Args:
        resp_task: Agent Carol이 생성한 Task 객체.
            가장 최근 아티팩트에 단일 JSON 리스트가 포함되어 있어야 합니다.

    Returns:
        list: 파싱된 히스토리 리스트. 파싱 실패 또는 아티팩트가
        없거나 유효하지 않은 경우 빈 리스트를 반환합니다.
    """
    parts_text = extract_text(resp_task)
    try:
        return json.loads(parts_text)
    except json.JSONDecodeError:
        return []


def _negotiate_sorted_history(
    max_attempts: int = MAX_NEGOTIATION_ATTEMPTS,
) -> int:
    """히스토리 리스트가 정렬될 때까지 Carol에게 셔플을 요청합니다.

    새로운 *shuffle* 태스크를 시작한 다음, 반환된 리스트가 정렬되었는지에 따라
    "Try again" 또는 "Well done!" 후속 메시지를 보내는 요청/응답 루프에 진입합니다.

    Args:
        max_attempts: 무한 루프를 방지하기 위해 태스크가 취소되기 전
            재셔플 시도 횟수의 상한.

    Returns:
        int: 협상 중 Carol에게 보낸 메시지 수.
    """
    attempts = 0
    resp_task = _start_shuffle_request()
    if resp_task is None:
        return attempts

    print(
        f'[Bob] Received Task {resp_task.id} with state={resp_task.status.state}'
    )

    while (
        resp_task.status.state == TaskState.input_required
        and attempts < max_attempts
    ):
        # 어떤 후속 메시지를 보낼지 결정하기 *전에* 리스트를 평가
        maybe_hist = _extract_history_from_task(resp_task)
        if isinstance(maybe_hist, list):
            print(f'[Bob] Candidate history: {maybe_hist}')
            print(f'[Bob] is_sorted? {is_sorted_history(maybe_hist)}')

        if isinstance(maybe_hist, list) and is_sorted_history(maybe_hist):
            attempts += 1
            game_history.clear()
            game_history.extend(maybe_hist)
            print(f'[Bob] History is sorted after {attempts} attempt(s)')
            print(
                '(We do sorting by random to illustrate multi-turn communication)'
            )
            resp_task = send_followup(AGENT_CAROL_PORT, resp_task, 'Well done!')  # type: ignore[assignment]
            break

        # 정렬되지 않음 → Carol에게 다시 셔플 요청
        attempts += 1
        print(f"[Bob] Attempt {attempts}: sending 'Try again'")
        resp_obj = send_followup(AGENT_CAROL_PORT, resp_task, 'Try again')
        if not isinstance(resp_obj, Task):
            print(
                '[Bob] Did not receive Task in response; aborting negotiation'
            )
            break
        resp_task = resp_obj
        print(f'[Bob] Carol responded with state={resp_task.status.state}')

    if (
        resp_task.status.state == TaskState.input_required
        and attempts >= max_attempts
    ):
        print(
            f'[Bob] Reached maximum attempts ({max_attempts}). Cancelling task.'
        )
        cancel_task(AGENT_CAROL_PORT, resp_task.id)

    return attempts


def _handle_guess(guess: str) -> str:
    """*guess*를 Agent Alice에게 전달하고 텍스트 피드백을 반환합니다.

    Args:
        guess: 사용자의 추측 문자열.

    Returns:
        str: Alice의 피드백 메시지.
    """
    resp_obj = send_text(AGENT_ALICE_PORT, guess)
    feedback = extract_text(resp_obj)
    print(f'Alice says: {feedback}')
    return feedback


def _visualise_history() -> None:
    """*game_history*의 포맷된 시각화를 요청하고 출력합니다."""
    vis_obj = send_text(AGENT_CAROL_PORT, json.dumps(game_history))
    vis_text = extract_text(vis_obj)
    print("\n=== Carol's visualisation (sorted) ===")
    print(vis_text)
    print('============================\n')


def play_game() -> None:
    """숫자 맞추기 게임의 대화형 CLI 루프를 실행합니다.

    사용자로부터 추측을 입력받아 Alice에게 전송하고,
    Carol에게 히스토리 시각화를 요청합니다.
    정답을 맞출 때까지 반복합니다.
    """
    print('Guess the number AgentAlice chose (1-100)!')

    while True:
        user_input = input('Your guess: ').strip()
        if not user_input:
            continue

        feedback = _handle_guess(user_input)
        game_history.append({'guess': user_input, 'response': feedback})

        total_attempts = _negotiate_sorted_history()
        if total_attempts:
            print(
                f'Asked Carol to re-do the visualisation {total_attempts} times'
            )

        _visualise_history()

        if feedback.startswith('correct'):
            break

    print('You won! Exiting…')
    time.sleep(0.5)


def main() -> None:  # pragma: no cover
    """메인 진입점. 게임을 시작하기 전 안내 메시지를 출력합니다."""
    print("Hint: don't forget to also start Alice and Carol!")
    play_game()


if __name__ == '__main__':
    main()
