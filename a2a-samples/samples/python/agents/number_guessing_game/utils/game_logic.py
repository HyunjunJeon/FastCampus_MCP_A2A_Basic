"""게임 로직 모듈.

숫자 맞추기 데모에서 공유하는 게임 메커닉입니다.
이 모듈은 전송 프로토콜에 독립적입니다.

현재 포함된 기능:
    - Agent Alice용 숫자 추측 평가 (`process_guess`)
    - Agent Carol용 히스토리 시각화 및 셔플 헬퍼
      (`build_visualisation`, `process_history_payload`)
"""

from __future__ import annotations

import json
import random

from utils.helpers import parse_int_in_range, try_parse_json


__all__ = [
    'build_visualisation',
    'is_sorted_history',
    'process_guess',
    'process_history_payload',
]

# ---------------------------------------------------------------------------
# 숫자 맞추기 상태 (Alice)
# ---------------------------------------------------------------------------

_target_number: int = random.randint(1, 100)
_attempts: int = 0
_secret_logged: bool = False


# ---------------------------------------------------------------------------
# 숫자 맞추기 헬퍼
# ---------------------------------------------------------------------------


def process_guess(raw_text: str) -> str:
    """단일 추측을 평가하고 Agent Alice의 피드백을 반환합니다.

    Args:
        raw_text: 1과 100 사이의 정수(포함)를 나타내야 하는
            원시 사용자 입력.

    Returns:
        str: 다음 응답 문자열 중 하나:
            * ``"Go higher"`` – 추측이 비밀 숫자보다 낮음.
            * ``"Go lower"`` – 추측이 비밀 숫자보다 높음.
            * ``"correct! attempts: <n>"`` – 정답. *n*은 시도 횟수.
            * 입력이 유효하지 않은 경우 오류 프롬프트.
    """
    global _attempts, _target_number, _secret_logged

    if not _secret_logged:
        print('[GameLogic] Secret number selected. Waiting for guesses…')
        _secret_logged = True

    guess = parse_int_in_range(raw_text, 1, 100)
    if guess is None:
        print(f"[GameLogic] Received invalid input '{raw_text}'.")
        return 'Please send a number between 1 and 100.'

    _attempts += 1

    if guess < _target_number:
        hint = 'Go higher'
    elif guess > _target_number:
        hint = 'Go lower'
    else:
        hint = f'correct! attempts: {_attempts}'

    print(f'[GameLogic] Guess {guess} -> {hint}')
    return hint


# ---------------------------------------------------------------------------
# 히스토리 헬퍼 (Carol과 Bob)
# ---------------------------------------------------------------------------


def build_visualisation(history: list[dict[str, str]]) -> str:
    """추측/응답 히스토리 리스트의 사람이 읽을 수 있는 렌더링을 생성합니다.

    Args:
        history: 최소한 ``"guess"``와 ``"response"`` 키를 포함하는
            딕셔너리의 시퀀스.

    Returns:
        str: 콘솔에 출력할 준비가 된 여러 줄 문자열.
    """
    if not history:
        return 'No guesses yet.'

    lines = ['Guesses so far:']
    for idx, entry in enumerate(history, 1):
        guess = entry.get('guess', '?')
        response = entry.get('response', '?')
        lines.append(f' {idx:>2}. {guess:>3} -> {response}')
    print('[GameLogic] Created a visualisation for Bob')
    return '\n'.join(lines)


def is_sorted_history(history: list[dict[str, str]]) -> bool:
    """*history*가 추측 기준으로 오름차순 정렬되어 있으면 ``True``를 반환합니다.

    이 헬퍼는 전체 딕셔너리 대신 일반 숫자나 숫자 문자열을 포함하는
    히스토리도 우아하게 처리합니다.

    Args:
        history: 추측 값을 나타내는 딕셔너리(``'guess'`` 키 포함) **또는**
            일반 숫자의 리스트.

    Returns:
        bool: 값이 비감소 순서일 때 ``True``.
            파싱 오류 시 ``False``.
    """
    # 히스토리 리스트는 ('guess' 키가 있는) dict 항목 또는
    # 다른 에이전트가 단순화된 리스트로 응답할 때 bare 숫자 값을 포함할 수 있음
    try:
        if history and isinstance(history[0], dict):
            guesses = [int(entry['guess']) for entry in history]
        else:
            # 일반 숫자 / 숫자 문자열의 이터러블로 가정
            guesses = [int(entry) for entry in history]
    except (ValueError, TypeError, KeyError):
        return False
    return guesses == sorted(guesses)


def process_history_payload(raw_text: str) -> str:
    """제공된 페이로드에 대한 Agent Carol의 응답을 반환합니다.

    해석은 JSON 구조에 따라 달라집니다:

    1. ``{"action": "shuffle", "history": [...]}`` – 히스토리 리스트가
       제자리에서 셔플되고 JSON 문자열로 반환됩니다.
    2. ``[ ... ]`` – 리스트가 전체 히스토리로 처리되고
       :func:`build_visualisation`을 통해 포맷됩니다.

    JSON으로 파싱할 수 없는 입력은 유효하지 않은 입력을 나타내기 위해
    빈 시각화를 반환합니다.

    Args:
        raw_text: Bob으로부터 받은 원시 페이로드.

    Returns:
        str: JSON 인코딩된 리스트 또는 일반 텍스트 시각화.
    """
    success, parsed = try_parse_json(raw_text)
    if not success:
        # JSON이 아님 – 유효하지 않은 입력을 나타내기 위해 빈 시각화 반환
        return build_visualisation([])

    # 셔플 요청
    if isinstance(parsed, dict) and parsed.get('action') == 'shuffle':
        history_list = parsed.get('history', [])
        if not isinstance(history_list, list):
            history_list = []
        random.shuffle(history_list)
        print('[GameLogic] Shuffled history and returned JSON list')
        return json.dumps(history_list)

    # 시각화 요청
    if isinstance(parsed, list):
        return build_visualisation(parsed)

    # 지원되지 않는 JSON 페이로드에 대한 폴백
    return build_visualisation([])
