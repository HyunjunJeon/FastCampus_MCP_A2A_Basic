"""utils 패키지.

숫자 맞추기 데모에서 공유하는 헬퍼 함수들을 제공합니다.

제공되는 함수:
    - parse_int_in_range: 범위 내 정수 파싱
    - try_parse_json: JSON 파싱 시도
"""

from utils.helpers import parse_int_in_range, try_parse_json


__all__ = [
    'parse_int_in_range',
    'try_parse_json',
]
