"""
프로젝트 전체에서 사용되는 통합 로깅 설정 모듈

이 모듈은 다음과 같은 기능을 제공합니다:
1. 일관된 로깅 포맷 설정
2. 환경별 로그 레벨 자동 설정
3. 모듈별 로거 생성
4. 로그 파일 출력 설정 (선택적)
5. 구조화된 로깅 (JSON) 지원

사용법:
    from src.utils.logging_config import get_logger

    logger = get_logger(__name__)
    logger.info("로깅 메시지")
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional, Union

# 구조화된 로깅 시스템 임포트 시도
try:
    from src.utils.structured_logger import (
        get_structured_logger,
        ContextLogger,
        StructuredFormatter,
    )

    STRUCTURED_LOGGING_AVAILABLE = True
except ImportError:
    STRUCTURED_LOGGING_AVAILABLE = False
    ContextLogger = logging.Logger  # Fallback 타입


# 전역 로깅 설정이 완료되었는지 추적
_logging_configured = False


def _configure_root_logging() -> None:
    """루트 로거 전역 설정을 수행합니다."""
    global _logging_configured

    if _logging_configured:
        return

    # 환경변수에서 로그 레벨 결정
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # 개발 환경 감지
    is_dev = os.getenv("ENVIRONMENT", "development").lower() in ["dev", "development"]
    is_test = "pytest" in sys.modules

    # 로그 레벨 설정
    if is_test:
        level = logging.WARNING  # 테스트시 경고 이상만 출력
    elif is_dev:
        level = getattr(logging, log_level, logging.DEBUG)
    else:
        level = getattr(logging, log_level, logging.INFO)

    # 로그 포맷 선택 (JSON 또는 텍스트)
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    if log_format == "json" and STRUCTURED_LOGGING_AVAILABLE:
        # JSON 포맷 사용
        formatter = StructuredFormatter()
    else:
        # 기본 텍스트 포맷
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 기존 핸들러 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 콘솔 핸들러 추가: stdout 대신 stderr 사용하여 파이프 종료 시 영향을 최소화
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 파일 로깅 설정 (선택적)
    log_file_path = os.getenv("LOG_FILE_PATH")
    if log_file_path:
        log_dir = Path(log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 로깅 중 emit 예외 상세 출력 억제
    logging.raiseExceptions = False

    _logging_configured = True


def get_logger(name: str) -> Union[logging.Logger, "ContextLogger"]:
    """
    모듈별 로거를 생성하고 반환합니다.

    구조화된 로깅이 가능하면 항상 ContextLogger를 반환하고,
    그렇지 않으면 기본 Logger를 반환합니다.

    Args:
        name: 로거 이름 (일반적으로 __name__ 사용)

    Returns:
        설정된 로거 인스턴스

    Example:
        logger = get_logger(__name__)
        logger.info("애플리케이션이 시작되었습니다")
    """
    if STRUCTURED_LOGGING_AVAILABLE:
        # 구조화된 로깅 항상 사용
        return get_structured_logger(name)

    # 전역 로깅 설정 확인
    _configure_root_logging()

    # 모듈별 로거 반환
    return logging.getLogger(name)


def setup_basic_logging(
    level: Optional[str] = None, format_string: Optional[str] = None
) -> None:
    """
    기본 로깅 설정을 수행합니다 (하위 호환성을 위해 제공).

    Args:
        level: 로그 레벨 (INFO, DEBUG, WARNING, ERROR)
        format_string: 커스텀 포맷 문자열

    Note:
        이 함수는 하위 호환성을 위해 제공되며,
        새로운 코드에서는 get_logger()를 직접 사용하는 것을 권장합니다.
    """
    global _logging_configured

    if level:
        os.environ["LOG_LEVEL"] = level

    if format_string:
        # 커스텀 포맷이 제공된 경우 강제로 재설정
        _logging_configured = False

        _configure_root_logging()

        # 커스텀 포맷 적용
        formatter = logging.Formatter(format_string)
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
    else:
        _configure_root_logging()


def disable_logging_for_module(module_name: str) -> None:
    """
    특정 모듈의 로깅을 비활성화합니다.

    Args:
        module_name: 비활성화할 모듈명

    Example:
        # httpx 모듈의 로깅 비활성화
        disable_logging_for_module('httpx')
    """
    logging.getLogger(module_name).setLevel(logging.WARNING)


def set_module_log_level(module_name: str, level: str) -> None:
    """
    특정 모듈의 로그 레벨을 설정합니다.

    Args:
        module_name: 모듈명
        level: 로그 레벨 (INFO, DEBUG, WARNING, ERROR)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger(module_name).setLevel(log_level)


# 자주 사용되는 써드파티 라이브러리들의 로그 레벨 조정
def configure_third_party_logging():
    """써드파티 라이브러리들의 로깅을 적절한 레벨로 설정합니다."""
    # HTTP 클라이언트 라이브러리들의 상세 로그 비활성화
    for module in ["httpx", "urllib3", "requests", "aiohttp"]:
        set_module_log_level(module, "WARNING")

    # LangChain 관련 로깅 레벨 조정
    for module in ["langchain", "langsmith"]:
        set_module_log_level(module, "INFO")


# 성능 로깅 데코레이터 export
if STRUCTURED_LOGGING_AVAILABLE:
    from src.utils.structured_logger import log_performance
else:
    # Fallback 데코레이터
    def log_performance(logger=None):
        def decorator(func):
            return func

        return decorator


# 모듈 임포트시 자동으로 써드파티 로깅 설정
configure_third_party_logging()
