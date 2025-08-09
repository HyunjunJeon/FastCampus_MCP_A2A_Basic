"""
표준화된 에러 처리 시스템

이 모듈은 프로젝트 전체에서 일관된 에러 처리와 응답 형식을 제공합니다.

주요 기능:
- StandardResponse 패턴 구현
- 일관된 에러 메시지 형식
- 에러 복구 전략
- 구조화된 에러 로깅
"""

import sys
import traceback
from typing import Any, Dict, Optional, Type, Union, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import json
import asyncio
from functools import wraps

from pydantic import BaseModel
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class ErrorSeverity(Enum):
    """에러 심각도 레벨"""
    LOW = "low"        # 경고 수준, 계속 진행 가능
    MEDIUM = "medium"  # 일부 기능 제한, 대체 경로 사용
    HIGH = "high"      # 주요 기능 실패, 복구 시도 필요
    CRITICAL = "critical"  # 시스템 중단 필요


class ErrorCategory(Enum):
    """에러 카테고리 분류"""
    VALIDATION = "validation"      # 입력 검증 오류
    AUTHENTICATION = "auth"        # 인증/권한 오류
    NETWORK = "network"           # 네트워크 관련 오류
    EXTERNAL_API = "external_api" # 외부 API 호출 오류
    CONFIGURATION = "config"       # 설정 관련 오류
    RESOURCE = "resource"         # 리소스 부족 (메모리, 디스크 등)
    BUSINESS_LOGIC = "business"    # 비즈니스 로직 오류
    SYSTEM = "system"             # 시스템 레벨 오류
    UNKNOWN = "unknown"           # 분류되지 않은 오류


@dataclass
class ErrorContext:
    """에러 컨텍스트 정보"""
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    component: Optional[str] = None
    operation: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


class StandardError(Exception):
    """
    표준화된 에러 클래스
    
    모든 커스텀 예외의 기본 클래스로, 일관된 에러 정보를 제공합니다.
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        recovery_suggestion: Optional[str] = None
    ):
        """
        StandardError 초기화
        
        Args:
            message: 에러 메시지
            error_code: 에러 코드 (예: "E001", "API_KEY_INVALID")
            category: 에러 카테고리
            severity: 에러 심각도
            context: 에러 발생 컨텍스트
            cause: 원인이 된 예외
            recovery_suggestion: 복구 방법 제안
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self._generate_error_code(category)
        self.category = category
        self.severity = severity
        self.context = context or ErrorContext()
        self.cause = cause
        self.recovery_suggestion = recovery_suggestion
        
        # 스택 트레이스 캡처
        self.traceback = traceback.format_exc() if sys.exc_info()[0] else None
    
    def _generate_error_code(self, category: ErrorCategory) -> str:
        """에러 코드 자동 생성"""
        prefix_map = {
            ErrorCategory.VALIDATION: "VAL",
            ErrorCategory.AUTHENTICATION: "AUTH",
            ErrorCategory.NETWORK: "NET",
            ErrorCategory.EXTERNAL_API: "API",
            ErrorCategory.CONFIGURATION: "CFG",
            ErrorCategory.RESOURCE: "RES",
            ErrorCategory.BUSINESS_LOGIC: "BIZ",
            ErrorCategory.SYSTEM: "SYS",
            ErrorCategory.UNKNOWN: "UNK"
        }
        prefix = prefix_map.get(category, "ERR")
        # 타임스탬프 기반 고유 ID
        unique_id = int(datetime.now().timestamp() * 1000) % 10000
        return f"{prefix}{unique_id:04d}"
    
    def to_dict(self) -> Dict[str, Any]:
        """에러 정보를 딕셔너리로 변환"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "timestamp": self.context.timestamp.isoformat(),
            "component": self.context.component,
            "operation": self.context.operation,
            "recovery_suggestion": self.recovery_suggestion,
            "cause": str(self.cause) if self.cause else None,
            "traceback": self.traceback if logger.level <= 10 else None  # DEBUG 레벨에서만
        }


class StandardResponse(BaseModel):
    """
    표준화된 응답 형식
    
    API 응답, 내부 통신 등 모든 응답에서 사용되는 표준 형식입니다.
    """
    
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def success_response(
        cls,
        data: Any,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "StandardResponse":
        """성공 응답 생성"""
        meta = metadata or {}
        if message:
            meta["message"] = message
        return cls(
            success=True,
            data=data,
            error=None,
            metadata=meta
        )
    
    @classmethod
    def error_response(
        cls,
        error: Union[StandardError, Exception, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> "StandardResponse":
        """에러 응답 생성"""
        if isinstance(error, StandardError):
            error_dict = error.to_dict()
        elif isinstance(error, Exception):
            error_dict = {
                "message": str(error),
                "type": error.__class__.__name__
            }
        else:
            error_dict = {"message": str(error)}
        
        return cls(
            success=False,
            data=None,
            error=error_dict,
            metadata=metadata or {}
        )


class ErrorHandler:
    """
    중앙화된 에러 처리기
    
    에러 처리, 로깅, 복구 전략을 관리하는 싱글톤 클래스입니다.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.error_handlers: Dict[Type[Exception], Callable] = {}
            self.recovery_strategies: Dict[ErrorCategory, Callable] = {}
            self.error_stats: Dict[str, int] = {}
            self.initialized = True
    
    def register_handler(
        self,
        exception_type: Type[Exception],
        handler: Callable[[Exception], Optional[Any]]
    ):
        """특정 예외 타입에 대한 핸들러 등록"""
        self.error_handlers[exception_type] = handler
        logger.debug(f"Registered handler for {exception_type.__name__}")
    
    def register_recovery_strategy(
        self,
        category: ErrorCategory,
        strategy: Callable[[StandardError], Optional[Any]]
    ):
        """에러 카테고리별 복구 전략 등록"""
        self.recovery_strategies[category] = strategy
        logger.debug(f"Registered recovery strategy for {category.value}")
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[ErrorContext] = None,
        raise_after_handling: bool = False
    ) -> StandardResponse:
        """
        에러 처리 메인 메서드
        
        Args:
            error: 처리할 예외
            context: 에러 발생 컨텍스트
            raise_after_handling: 처리 후 예외 재발생 여부
            
        Returns:
            StandardResponse 객체
        """
        # StandardError로 변환
        if not isinstance(error, StandardError):
            std_error = self._convert_to_standard_error(error, context)
        else:
            std_error = error
            if context:
                std_error.context = context
        
        # 에러 통계 업데이트
        self._update_error_stats(std_error)
        
        # 로깅
        self._log_error(std_error)
        
        # 특정 핸들러 실행
        handler_result = self._execute_handler(error)
        if handler_result is not None:
            return StandardResponse.success_response(
                data=handler_result,
                message="Error handled successfully"
            )
        
        # 복구 전략 실행
        recovery_result = self._execute_recovery_strategy(std_error)
        if recovery_result is not None:
            return StandardResponse.success_response(
                data=recovery_result,
                message="Error recovered successfully"
            )
        
        # 표준 에러 응답 반환
        response = StandardResponse.error_response(std_error)
        
        if raise_after_handling:
            raise std_error
        
        return response
    
    def _convert_to_standard_error(
        self,
        error: Exception,
        context: Optional[ErrorContext] = None
    ) -> StandardError:
        """일반 예외를 StandardError로 변환"""
        # 예외 타입별 카테고리 매핑
        category_map = {
            ValueError: ErrorCategory.VALIDATION,
            KeyError: ErrorCategory.VALIDATION,
            TypeError: ErrorCategory.VALIDATION,
            ConnectionError: ErrorCategory.NETWORK,
            TimeoutError: ErrorCategory.NETWORK,
            PermissionError: ErrorCategory.AUTHENTICATION,
            MemoryError: ErrorCategory.RESOURCE,
            OSError: ErrorCategory.SYSTEM,
        }
        
        error_type = type(error)
        category = category_map.get(error_type, ErrorCategory.UNKNOWN)
        
        # 심각도 결정
        severity = self._determine_severity(error, category)
        
        return StandardError(
            message=str(error),
            category=category,
            severity=severity,
            context=context,
            cause=error
        )
    
    def _determine_severity(
        self,
        error: Exception,
        category: ErrorCategory
    ) -> ErrorSeverity:
        """에러 심각도 자동 결정"""
        # 카테고리별 기본 심각도
        severity_map = {
            ErrorCategory.VALIDATION: ErrorSeverity.LOW,
            ErrorCategory.AUTHENTICATION: ErrorSeverity.HIGH,
            ErrorCategory.NETWORK: ErrorSeverity.MEDIUM,
            ErrorCategory.EXTERNAL_API: ErrorSeverity.MEDIUM,
            ErrorCategory.CONFIGURATION: ErrorSeverity.HIGH,
            ErrorCategory.RESOURCE: ErrorSeverity.CRITICAL,
            ErrorCategory.BUSINESS_LOGIC: ErrorSeverity.MEDIUM,
            ErrorCategory.SYSTEM: ErrorSeverity.CRITICAL,
            ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM,
        }
        
        return severity_map.get(category, ErrorSeverity.MEDIUM)
    
    def _update_error_stats(self, error: StandardError):
        """에러 통계 업데이트"""
        key = f"{error.category.value}:{error.error_code}"
        self.error_stats[key] = self.error_stats.get(key, 0) + 1
    
    def _log_error(self, error: StandardError):
        """에러 로깅"""
        log_message = (
            f"[{error.error_code}] {error.message} | "
            f"Category: {error.category.value} | "
            f"Severity: {error.severity.value}"
        )
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # DEBUG 레벨에서 상세 정보 로깅
        if logger.level <= 10:
            logger.debug(f"Error details: {json.dumps(error.to_dict(), indent=2)}")
    
    def _execute_handler(self, error: Exception) -> Optional[Any]:
        """등록된 핸들러 실행"""
        handler = self.error_handlers.get(type(error))
        if handler:
            try:
                return handler(error)
            except Exception as e:
                logger.error(f"Error in handler: {e}")
        return None
    
    def _execute_recovery_strategy(self, error: StandardError) -> Optional[Any]:
        """복구 전략 실행"""
        strategy = self.recovery_strategies.get(error.category)
        if strategy:
            try:
                return strategy(error)
            except Exception as e:
                logger.error(f"Error in recovery strategy: {e}")
        return None
    
    def get_error_stats(self) -> Dict[str, Any]:
        """에러 통계 반환"""
        return {
            "total_errors": sum(self.error_stats.values()),
            "by_category": self.error_stats,
            "most_common": max(self.error_stats, key=self.error_stats.get)
            if self.error_stats else None
        }


# 글로벌 에러 핸들러 인스턴스
error_handler = ErrorHandler()


# 데코레이터 함수들
def handle_errors(
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    raise_after: bool = False
):
    """
    에러 처리 데코레이터
    
    함수에서 발생하는 예외를 자동으로 처리합니다.
    
    Usage:
        @handle_errors(category=ErrorCategory.EXTERNAL_API)
        async def call_api():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=func.__module__,
                    operation=func.__name__
                )
                response = error_handler.handle_error(
                    e, context, raise_after_handling=raise_after
                )
                return response
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=func.__module__,
                    operation=func.__name__
                )
                response = error_handler.handle_error(
                    e, context, raise_after_handling=raise_after
                )
                return response
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def retry_on_error(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    재시도 데코레이터
    
    특정 예외 발생 시 자동으로 재시도합니다.
    
    Args:
        max_attempts: 최대 시도 횟수
        delay: 초기 대기 시간
        backoff: 대기 시간 증가 배수
        exceptions: 재시도할 예외 타입들
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {current_delay}s delay. Error: {e}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    
                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {current_delay}s delay. Error: {e}"
                    )
                    import time
                    time.sleep(current_delay)
                    current_delay *= backoff
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 일반적인 에러 클래스들
class ValidationError(StandardError):
    """입력 검증 에러"""
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            **kwargs
        )
        self.field = field


class AuthenticationError(StandardError):
    """인증/권한 에러"""
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            recovery_suggestion="Please check your credentials and try again",
            **kwargs
        )


class ExternalAPIError(StandardError):
    """외부 API 호출 에러"""
    def __init__(self, message: str, api_name: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )
        self.api_name = api_name
        self.status_code = status_code


class ConfigurationError(StandardError):
    """설정 에러"""
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            recovery_suggestion="Please check your configuration settings",
            **kwargs
        )
        self.config_key = config_key


# 기본 복구 전략 등록
def network_recovery_strategy(error: StandardError) -> Optional[Dict[str, Any]]:
    """네트워크 에러 복구 전략"""
    return {
        "fallback": "offline_mode",
        "message": "Switched to offline mode due to network issues"
    }


def api_recovery_strategy(error: StandardError) -> Optional[Dict[str, Any]]:
    """API 에러 복구 전략"""
    return {
        "fallback": "cached_data",
        "message": "Using cached data due to API issues"
    }


# 기본 전략 등록
error_handler.register_recovery_strategy(ErrorCategory.NETWORK, network_recovery_strategy)
error_handler.register_recovery_strategy(ErrorCategory.EXTERNAL_API, api_recovery_strategy)