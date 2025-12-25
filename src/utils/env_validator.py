"""
환경 변수 검증 및 보안 관리 유틸리티

이 모듈은 프로젝트 전체에서 사용되는 환경 변수의 검증과
API 키 관리를 담당합니다.

주요 기능:
- 필수 환경 변수 검증
- API 키 마스킹 및 보안 로깅
- 환경별 설정 관리
- 설정 검증 리포트 생성
"""

import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

# 로거 지연 초기화 (순환 임포트 방지)
_logger = None


def _get_logger():
    """로거 지연 초기화 - 순환 임포트 방지"""
    global _logger
    if _logger is None:
        from src.utils.logging_config import get_logger

        _logger = get_logger(__name__)
    return _logger


def logger():
    """로거 함수 - 첫 접근 시 초기화"""
    return _get_logger()


class EnvVarType(Enum):
    """환경 변수 타입 정의"""

    REQUIRED = "required"  # 필수 변수
    OPTIONAL = "optional"  # 선택적 변수
    CONDITIONAL = "conditional"  # 조건부 필수 (다른 변수에 의존)


@dataclass
class EnvVarSpec:
    """환경 변수 명세"""

    name: str
    var_type: EnvVarType
    description: str
    default: Optional[str] = None
    validator: Optional[callable] = None
    sensitive: bool = False  # API 키 등 민감 정보 여부
    depends_on: Optional[List[str]] = None  # 의존 관계


class EnvironmentValidator:
    """
    환경 변수 검증 및 관리 클래스

    Design Pattern:
        - Singleton Pattern: 애플리케이션 전체에서 하나의 인스턴스만 사용
        - Validator Pattern: 각 변수별 커스텀 검증 로직
        - Security by Design: 민감 정보 자동 마스킹
    """

    _instance = None

    def __new__(cls):
        """Singleton 패턴 구현"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """환경 변수 명세 초기화"""
        if not hasattr(self, "initialized"):
            self.env_specs = self._define_env_specs()
            self.validated = False
            self.validation_report = {}
            self.initialized = True

            # .env 파일 자동 로드
            self._load_env_files()

    def _load_env_files(self):
        """환경 파일 로드 (.env, .env.local 등)"""
        env_files = [".env", ".env.local"]
        for env_file in env_files:
            env_path = Path(env_file)
            if env_path.exists():
                load_dotenv(env_path)
                logger().debug(f"Loaded environment from {env_file}")

    def _define_env_specs(self) -> Dict[str, EnvVarSpec]:
        """환경 변수 명세 정의"""
        return {
            # 필수 API 키
            "OPENAI_API_KEY": EnvVarSpec(
                name="OPENAI_API_KEY",
                var_type=EnvVarType.REQUIRED,
                description="OpenAI API key for LLM operations",
                sensitive=True,
                validator=self._validate_openai_key,
            ),
            # 검색 서비스 API 키 (최소 하나 필수)
            "TAVILY_API_KEY": EnvVarSpec(
                name="TAVILY_API_KEY",
                var_type=EnvVarType.CONDITIONAL,
                description="Tavily search API key",
                sensitive=True,
                validator=self._validate_tavily_key,
                depends_on=["SERPER_API_KEY"],  # 둘 중 하나는 필수
            ),
            "SERPER_API_KEY": EnvVarSpec(
                name="SERPER_API_KEY",
                var_type=EnvVarType.CONDITIONAL,
                description="Serper.dev API key",
                sensitive=True,
                validator=self._validate_serper_key,
                depends_on=["TAVILY_API_KEY"],  # 둘 중 하나는 필수
            ),
            # 선택적 API 키
            "ANTHROPIC_API_KEY": EnvVarSpec(
                name="ANTHROPIC_API_KEY",
                var_type=EnvVarType.OPTIONAL,
                description="Anthropic Claude API key",
                sensitive=True,
                validator=self._validate_anthropic_key,
            ),
            # 모델 설정
            "MODEL_NAME": EnvVarSpec(
                name="MODEL_NAME",
                var_type=EnvVarType.OPTIONAL,
                description="Default LLM model name",
                default="gpt-4o-mini",
            ),
            "TEMPERATURE": EnvVarSpec(
                name="TEMPERATURE",
                var_type=EnvVarType.OPTIONAL,
                description="LLM temperature setting",
                default="0.7",
                validator=self._validate_temperature,
            ),
            "MAX_TOKENS": EnvVarSpec(
                name="MAX_TOKENS",
                var_type=EnvVarType.OPTIONAL,
                description="Maximum tokens for LLM response",
                default="4000",
                validator=self._validate_max_tokens,
            ),
            # 환경 설정
            "ENV": EnvVarSpec(
                name="ENV",
                var_type=EnvVarType.OPTIONAL,
                description="Environment (development/staging/production)",
                default="development",
                validator=self._validate_environment,
            ),
            "LOG_LEVEL": EnvVarSpec(
                name="LOG_LEVEL",
                var_type=EnvVarType.OPTIONAL,
                description="Logging level",
                default="INFO",
                validator=self._validate_log_level,
            ),
            # 서비스 URL
            "REDIS_URL": EnvVarSpec(
                name="REDIS_URL",
                var_type=EnvVarType.OPTIONAL,
                description="Redis connection URL",
                default="redis://localhost:6379",
            ),
            "HITL_WEB_PORT": EnvVarSpec(
                name="HITL_WEB_PORT",
                var_type=EnvVarType.OPTIONAL,
                description="HITL web interface port",
                default="8000",
                validator=self._validate_port,
            ),
        }

    # 검증 함수들
    def _validate_openai_key(self, value: str) -> bool:
        """OpenAI API 키 형식 검증"""
        return value.startswith(("sk-", "sk-proj-")) and len(value) > 20

    def _validate_tavily_key(self, value: str) -> bool:
        """Tavily API 키 형식 검증"""
        return value.startswith("tvly-") and len(value) > 10

    def _validate_serper_key(self, value: str) -> bool:
        """Serper API 키 형식 검증"""
        return len(value) > 10  # Serper는 특별한 접두사가 없음

    def _validate_anthropic_key(self, value: str) -> bool:
        """Anthropic API 키 형식 검증"""
        return value.startswith("sk-ant-") and len(value) > 20

    def _validate_temperature(self, value: str) -> bool:
        """Temperature 값 검증 (0.0 ~ 2.0)"""
        try:
            temp = float(value)
            return 0.0 <= temp <= 2.0
        except ValueError:
            return False

    def _validate_max_tokens(self, value: str) -> bool:
        """Max tokens 값 검증"""
        try:
            tokens = int(value)
            return 1 <= tokens <= 128000  # GPT-4 최대값
        except ValueError:
            return False

    def _validate_environment(self, value: str) -> bool:
        """환경 값 검증"""
        return value in ["development", "staging", "production", "test"]

    def _validate_log_level(self, value: str) -> bool:
        """로그 레벨 검증"""
        return value.upper() in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def _validate_port(self, value: str) -> bool:
        """포트 번호 검증"""
        try:
            port = int(value)
            return 1 <= port <= 65535
        except ValueError:
            return False

    def _mask_sensitive(self, value: str) -> str:
        """민감한 정보 마스킹"""
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"

    def validate(self, raise_on_error: bool = True) -> bool:
        """
        모든 환경 변수 검증

        Args:
            raise_on_error: 오류 시 예외 발생 여부

        Returns:
            검증 성공 여부
        """
        errors = []
        warnings = []
        self.validation_report = {
            "errors": [],
            "warnings": [],
            "validated_vars": {},
            "missing_required": [],
            "invalid_format": [],
        }

        # 필수 변수 검증
        for name, spec in self.env_specs.items():
            value = os.getenv(name, spec.default)

            if spec.var_type == EnvVarType.REQUIRED:
                if not value:
                    errors.append(f"필수 환경 변수 누락: {name} - {spec.description}")
                    self.validation_report["missing_required"].append(name)
                elif spec.validator and not spec.validator(value):
                    errors.append(f"잘못된 형식: {name}")
                    self.validation_report["invalid_format"].append(name)
                else:
                    self.validation_report["validated_vars"][name] = "[OK]"

            elif spec.var_type == EnvVarType.OPTIONAL:
                if value and spec.validator and not spec.validator(value):
                    warnings.append(f"잘못된 형식 (선택적): {name}")
                    self.validation_report["validated_vars"][name] = "[WARN]"
                else:
                    self.validation_report["validated_vars"][name] = "[OK]"

        # 조건부 필수 변수 검증 (검색 API 키)
        search_keys = ["TAVILY_API_KEY", "SERPER_API_KEY"]
        has_search_key = any(os.getenv(key) for key in search_keys)

        if not has_search_key:
            errors.append(
                "검색 API 키가 최소 하나 필요합니다 (TAVILY_API_KEY 또는 SERPER_API_KEY)"
            )

        # 리포트 업데이트
        self.validation_report["errors"] = errors
        self.validation_report["warnings"] = warnings

        # 검증 결과 로깅
        if errors:
            for error in errors:
                logger().error(f"환경 검증 실패: {error}")
            if raise_on_error:
                raise ValueError("환경 변수 검증 실패:\n" + "\n".join(errors))

        if warnings:
            for warning in warnings:
                logger().warning(f"환경 검증 경고: {warning}")

        self.validated = len(errors) == 0
        return self.validated

    def get_required_env(self, key: str) -> str:
        """
        필수 환경 변수 가져오기

        Args:
            key: 환경 변수 이름

        Returns:
            환경 변수 값

        Raises:
            ValueError: 환경 변수가 설정되지 않은 경우
        """
        value = os.getenv(key)
        if not value:
            raise ValueError(f"필수 환경 변수가 설정되지 않음: {key}")

        # 민감한 정보는 로그에 마스킹
        if key in self.env_specs and self.env_specs[key].sensitive:
            logger().debug(f"환경 변수 접근: {key}={self._mask_sensitive(value)}")
        else:
            logger().debug(f"환경 변수 접근: {key}={value}")

        return value

    def get_optional_env(
        self, key: str, default: Optional[str] = None
    ) -> Optional[str]:
        """
        선택적 환경 변수 가져오기

        Args:
            key: 환경 변수 이름
            default: 기본값

        Returns:
            환경 변수 값 또는 기본값
        """
        value = os.getenv(key, default)

        if key in self.env_specs and self.env_specs[key].default and not value:
            value = self.env_specs[key].default

        return value

    def get_config_summary(self) -> Dict[str, Any]:
        """
        현재 설정 요약 반환 (민감 정보 마스킹)

        Returns:
            설정 요약 딕셔너리
        """
        summary = {
            "environment": self.get_optional_env("ENV", "development"),
            "validated": self.validated,
            "api_keys": {},
            "model_config": {},
            "service_config": {},
        }

        # API 키 상태
        for key in [
            "OPENAI_API_KEY",
            "TAVILY_API_KEY",
            "SERPER_API_KEY",
            "ANTHROPIC_API_KEY",
        ]:
            value = os.getenv(key)
            if value:
                summary["api_keys"][key] = "[OK] 설정됨 " + self._mask_sensitive(value)
            else:
                summary["api_keys"][key] = "[X] 미설정"

        # 모델 설정
        summary["model_config"] = {
            "model": self.get_optional_env("MODEL_NAME", "gpt-4o-mini"),
            "temperature": self.get_optional_env("TEMPERATURE", "0.7"),
            "max_tokens": self.get_optional_env("MAX_TOKENS", "4000"),
        }

        # 서비스 설정
        summary["service_config"] = {
            "hitl_port": self.get_optional_env("HITL_WEB_PORT", "8000"),
            "redis_url": self.get_optional_env("REDIS_URL", "redis://localhost:6379"),
            "log_level": self.get_optional_env("LOG_LEVEL", "INFO"),
        }

        return summary

    def print_validation_report(self):
        """검증 리포트 출력"""
        print("\n" + "=" * 60)
        print("[INFO] 환경 변수 검증 리포트")
        print("=" * 60)

        summary = self.get_config_summary()

        print(f"\n[INFO] 환경: {summary['environment']}")
        print(f"[SUCCESS] 검증 상태: {'통과' if summary['validated'] else '실패'}")

        print("\n[INFO] API 키 상태:")
        for key, status in summary["api_keys"].items():
            print(f"  {key}: {status}")

        print("\n[INFO] 모델 설정:")
        for key, value in summary["model_config"].items():
            print(f"  {key}: {value}")

        if self.validation_report.get("errors"):
            print("\n[ERROR] 오류:")
            for error in self.validation_report["errors"]:
                print(f"  - {error}")

        if self.validation_report.get("warnings"):
            print("\n[WARNING] 경고:")
            for warning in self.validation_report["warnings"]:
                print(f"  - {warning}")

        print("\n" + "=" * 60)


# 글로벌 인스턴스 생성
env_validator = EnvironmentValidator()


# 편의 함수들
def validate_environment(raise_on_error: bool = True) -> bool:
    """환경 변수 검증"""
    return env_validator.validate(raise_on_error)


def get_required_env(key: str) -> str:
    """필수 환경 변수 가져오기"""
    return env_validator.get_required_env(key)


def get_optional_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """선택적 환경 변수 가져오기"""
    return env_validator.get_optional_env(key, default)


def print_env_report():
    """환경 검증 리포트 출력"""
    env_validator.print_validation_report()


# 모듈 임포트 시 자동 검증 (경고만)
if __name__ != "__main__":
    try:
        env_validator.validate(raise_on_error=False)
    except Exception as e:
        logger().warning(f"환경 변수 초기 검증 경고: {e}")
