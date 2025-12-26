"""범용 헬퍼 함수 모듈.

데모 에이전트들이 공유하는 유틸리티 함수들입니다.

제공되는 함수:
    - parse_int_in_range: 지정된 범위 내의 정수 파싱
    - try_parse_json: 안전한 JSON 파싱 시도
"""

from __future__ import annotations

import json

from typing import Any


# ---------------------------------------------------------------------------
# 작은 재사용 가능 유틸리티
# ---------------------------------------------------------------------------


def parse_int_in_range(text: str, low: int, high: int) -> int | None:
    """*text*에서 파싱된 정수가 포함 범위 내에 있으면 반환합니다.

    Args:
        text: 정수를 나타내야 하는 입력 문자열.
        low: 포함 하한.
        high: 포함 상한.

    Returns:
        int: 파싱된 정수가 ``[low, high]`` 범위 내에 있는 경우.
        None: 입력이 정수가 아니거나 범위를 벗어난 경우.
    """
    try:
        value = int(text)
    except (ValueError, TypeError):
        return None
    return value if low <= value <= high else None


def try_parse_json(text: str) -> tuple[bool, Any]:
    """*text*를 JSON으로 파싱하려고 시도합니다.

    Args:
        text: 파싱할 원시 문자열.

    Returns:
        tuple[bool, Any]: 첫 번째 요소가 파싱 성공 여부를 나타내는
            불리언 플래그이고, 두 번째 요소는 성공 시 파싱된 Python 객체,
            실패 시 ``None``인 쌍.
    """
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, None
