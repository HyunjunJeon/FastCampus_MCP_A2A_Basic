"""
구조화된 로깅 시스템

JSON 형식의 구조화된 로깅과 레벨별 세분화를 제공합니다.

주요 기능:
- JSON 형식 로그 출력
- 컨텍스트 정보 자동 포함
- 성능 메트릭 추적
- 모듈별 로그 레벨 제어
"""

import json
import logging
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional
import traceback
from contextlib import contextmanager
from functools import wraps

# 환경 변수 가져오기
from src.utils.env_validator import get_optional_env


class StructuredFormatter(logging.Formatter):
    """
    JSON 형식의 구조화된 로그 포매터

    모든 로그를 JSON 형식으로 변환하여 파싱과 분석을 용이하게 합니다.
    """

    def __init__(self, include_traceback: bool = True):
        """
        초기화

        Args:
            include_traceback: 예외 발생 시 트레이스백 포함 여부
        """
        super().__init__()
        self.include_traceback = include_traceback
        self.hostname = self._get_hostname()

    def _get_hostname(self) -> str:
        """호스트명 가져오기"""
        import socket

        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def format(self, record: logging.LogRecord) -> str:
        """
        로그 레코드를 JSON 형식으로 포맷

        Args:
            record: 로그 레코드

        Returns:
            JSON 형식의 로그 문자열
        """
        # 기본 로그 정보
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.thread,
            "thread_name": record.threadName,
            "process": record.process,
            "hostname": self.hostname,
        }

        # 추가 컨텍스트 정보
        if hasattr(record, "context"):
            log_data["context"] = record.context

        # 성능 메트릭
        if hasattr(record, "duration"):
            log_data["duration_ms"] = record.duration

        # 사용자 정의 필드
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # 예외 정보
        if record.exc_info and self.include_traceback:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # JSON 직렬화
        try:
            return json.dumps(log_data, ensure_ascii=False, default=str)
        except Exception as e:
            # 직렬화 실패 시 기본 포맷 사용
            return f'{{"error": "Failed to serialize log: {e}", "message": "{record.getMessage()}"}}'


class ContextLogger(logging.LoggerAdapter):
    """
    컨텍스트 정보를 포함하는 로거

    각 로그에 자동으로 컨텍스트 정보를 추가합니다.
    """

    def __init__(self, logger: logging.Logger, context: Dict[str, Any] = None):
        """
        초기화

        Args:
            logger: 기본 로거
            context: 컨텍스트 정보
        """
        self.context = context or {}
        super().__init__(logger, self.context)

    def process(self, msg, kwargs):
        """
        로그 메시지 처리

        컨텍스트 정보를 extra 필드에 추가합니다.
        """
        extra = kwargs.get("extra", {})
        extra["context"] = self.context
        kwargs["extra"] = extra
        return msg, kwargs

    def add_context(self, **kwargs):
        """컨텍스트 추가"""
        self.context.update(kwargs)

    def remove_context(self, *keys):
        """컨텍스트 제거"""
        for key in keys:
            self.context.pop(key, None)

    @contextmanager
    def temp_context(self, **kwargs):
        """
        임시 컨텍스트 관리

        Usage:
            with logger.temp_context(request_id="123"):
                logger.info("Processing request")
        """
        old_context = self.context.copy()
        self.context.update(kwargs)
        try:
            yield self
        finally:
            self.context = old_context


class StructuredLogger:
    """
    구조화된 로깅 시스템

    애플리케이션 전체의 로깅을 관리하는 싱글톤 클래스입니다.
    """

    _instance = None
    _loggers: Dict[str, ContextLogger] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.setup_logging()
            self.initialized = True

    def setup_logging(self):
        """로깅 시스템 설정"""
        # 환경 변수에서 설정 읽기
        log_level = get_optional_env("LOG_LEVEL", "INFO").upper()
        log_format = get_optional_env("LOG_FORMAT", "json")  # json 또는 text
        log_file = get_optional_env("LOG_FILE", None)

        # 루트 로거 설정
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level, logging.INFO))

        # 기존 핸들러 제거
        root_logger.handlers.clear()

        # 포매터 선택
        if log_format == "json":
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        # 콘솔 핸들러: stdout 대신 stderr 사용 (파이프 종료 시 BrokenPipe 영향 최소화)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 파일 핸들러 (옵션)
        if log_file:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        # 로깅 중 핸들러 emit 예외로 애플리케이션이 노이즈를 출력하지 않도록 설정
        logging.raiseExceptions = False

    def get_logger(
        self,
        name: str,
        level: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ContextLogger:
        """
        로거 인스턴스 가져오기

        Args:
            name: 로거 이름 (보통 __name__)
            level: 로그 레벨 (옵션)
            context: 초기 컨텍스트

        Returns:
            ContextLogger 인스턴스
        """
        if name not in self._loggers:
            base_logger = logging.getLogger(name)

            # 레벨 설정
            if level:
                base_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

            # ContextLogger 생성
            self._loggers[name] = ContextLogger(base_logger, context or {})

        return self._loggers[name]

    def set_module_level(self, module_pattern: str, level: str):
        """
        특정 모듈의 로그 레벨 설정

        Args:
            module_pattern: 모듈 패턴 (예: "src.lg_agents")
            level: 로그 레벨
        """
        for name, logger in self._loggers.items():
            if name.startswith(module_pattern):
                logger.logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        # 향후 생성될 로거를 위해 저장
        logging.getLogger(module_pattern).setLevel(
            getattr(logging, level.upper(), logging.INFO)
        )


# 글로벌 로깅 시스템 인스턴스
structured_logger = StructuredLogger()


def get_structured_logger(name: str, **context) -> ContextLogger:
    """
    구조화된 로거 가져오기

    Args:
        name: 로거 이름
        **context: 초기 컨텍스트

    Returns:
        ContextLogger 인스턴스
    """
    return structured_logger.get_logger(name, context=context)


# 성능 추적 데코레이터
def log_performance(logger: Optional[ContextLogger] = None):
    """
    함수 실행 시간을 로깅하는 데코레이터

    Usage:
        @log_performance()
        async def slow_function():
            ...
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_structured_logger(func.__module__)

            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000  # ms

                logger.info(
                    f"{func.__name__} completed",
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(duration, 2),
                            "status": "success",
                        }
                    },
                )
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"{func.__name__} failed",
                    exc_info=True,
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(duration, 2),
                            "status": "error",
                            "error": str(e),
                        }
                    },
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_structured_logger(func.__module__)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                logger.info(
                    f"{func.__name__} completed",
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(duration, 2),
                            "status": "success",
                        }
                    },
                )
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"{func.__name__} failed",
                    exc_info=True,
                    extra={
                        "extra_fields": {
                            "function": func.__name__,
                            "duration_ms": round(duration, 2),
                            "status": "error",
                            "error": str(e),
                        }
                    },
                )
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# 로그 레벨 동적 변경
def set_log_level(level: str, module: Optional[str] = None):
    """
    로그 레벨 동적 변경

    Args:
        level: 새 로그 레벨
        module: 특정 모듈 (None이면 전체)
    """
    if module:
        structured_logger.set_module_level(module, level)
    else:
        logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))


# 로그 통계
class LogStats:
    """로그 통계 수집"""

    def __init__(self):
        self.counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        self.last_reset = datetime.now()

    def increment(self, level: str):
        """카운트 증가"""
        self.counts[level] = self.counts.get(level, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        total = sum(self.counts.values())
        duration = (datetime.now() - self.last_reset).total_seconds()

        return {
            "counts": self.counts,
            "total": total,
            "duration_seconds": duration,
            "rate_per_minute": (total / duration * 60) if duration > 0 else 0,
            "error_rate": (self.counts["ERROR"] + self.counts["CRITICAL"]) / total
            if total > 0
            else 0,
        }

    def reset(self):
        """통계 초기화"""
        self.counts = {k: 0 for k in self.counts}
        self.last_reset = datetime.now()


# 글로벌 로그 통계
log_stats = LogStats()


# 기존 로깅 모듈과의 호환성을 위한 래퍼
def get_logger(name: str) -> ContextLogger:
    """
    기존 get_logger 함수와의 호환성 유지

    Args:
        name: 로거 이름

    Returns:
        ContextLogger 인스턴스
    """
    # 환경에서 설정 확인
    env = get_optional_env("ENV", "development")

    # 환경별 기본 컨텍스트
    context = {"environment": env, "service": "fc_mcp_a2a"}

    return get_structured_logger(name, **context)
