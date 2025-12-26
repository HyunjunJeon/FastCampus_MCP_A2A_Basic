"""유틸리티 모듈.

이 모듈은 에이전트 전반에서 사용되는 유틸리티 클래스를 제공합니다.
현재는 스레드 안전한 인메모리 캐시 구현이 포함되어 있습니다.
"""
import threading

from typing import Any


class InMemoryCache:
    """스레드 안전한 인메모리 캐시.

    만료 시간 없이 키-값 쌍을 저장하는 간단한 캐시입니다.
    threading.Lock을 사용하여 동시 접근 시 데이터 무결성을 보장합니다.

    Attributes:
        _lock: 스레드 동기화를 위한 Lock 객체.
        _store: 실제 데이터를 저장하는 딕셔너리.

    Note:
        이 캐시는 서버 재시작 시 모든 데이터가 손실됩니다.
        영구 저장이 필요한 경우 Redis 등의 외부 스토리지를 사용하세요.
    """

    def __init__(self) -> None:
        """InMemoryCache 인스턴스를 초기화합니다."""
        self._lock = threading.Lock()
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        """키에 해당하는 값을 조회합니다.

        Args:
            key: 조회할 키.

        Returns:
            저장된 값. 키가 없으면 None.
        """
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        """키-값 쌍을 저장합니다.

        Args:
            key: 저장할 키.
            value: 저장할 값.
        """
        with self._lock:
            self._store[key] = value

    def delete(self, key: str) -> None:
        """키에 해당하는 값을 삭제합니다.

        Args:
            key: 삭제할 키.
        """
        with self._lock:
            if key in self._store:
                del self._store[key]

    def clear(self) -> None:
        """캐시의 모든 데이터를 삭제합니다."""
        with self._lock:
            self._store.clear()


# 모듈 전반에서 사용할 싱글톤 캐시 인스턴스
cache = InMemoryCache()
