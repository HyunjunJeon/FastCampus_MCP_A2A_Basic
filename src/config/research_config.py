"""
Deep Research 에이전트 공통 설정 모듈

LangGraph와 A2A 버전 모두에서 사용되는 중앙화된 설정 클래스입니다.

주요 기능:
1. 실행 파라미터 설정 (재시도 횟수, 동시 실행 제한 등)
2. LLM 모델 설정 (연구, 압축, 보고서 생성용)
3. MCP 서버 엔드포인트 관리
4. 에이전트 간 통신 설정
5. 환경 변수 통합 관리

사용 예:
    from src.config import ResearchConfig

    # 기본 설정 사용
    config = ResearchConfig()

    # 커스텀 설정
    config = ResearchConfig(
        research_model="gpt-4o-turbo",
        max_researcher_iterations=5,
        allow_clarification=False
    )

    # LangGraph RunnableConfig에서 생성
    config = ResearchConfig.from_runnable_config(runnable_config)

    # A2A 에이전트 설정에서 생성
    config = ResearchConfig.from_a2a_config(a2a_config_dict)
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig

# 환경 변수 검증 시스템 사용
from src.utils.env_validator import get_optional_env, validate_environment


class ResearchConfig(BaseModel):
    """
    Deep Research 에이전트의 전체 설정을 관리하는 클래스

    LangGraph와 A2A 버전 모두에서 공통으로 사용되는 설정값들을 정의합니다.
    """

    # === 일반 실행 설정 ===
    max_structured_output_retries: int = Field(
        default=3, description="구조화된 출력 재시도 최대 횟수"
    )
    allow_clarification: bool = Field(
        default_factory=lambda: (
            (get_optional_env("ALLOW_CLARIFICATION", "true") or "true").strip().lower()
            in {"1", "true", "yes", "y"}
        ),
        description="사용자 질문 명확화 허용 여부 (ENV ALLOW_CLARIFICATION 로 오버라이드 가능)",
    )
    max_concurrent_research_units: int = Field(
        default=3, description="동시 연구 작업 최대 개수"
    )

    # === 연구 프로세스 설정 ===
    max_researcher_iterations: int = Field(default=3, description="연구 반복 최대 횟수")
    max_react_tool_calls: int = Field(
        default=5, description="ReAct 도구 호출 최대 횟수"
    )
    supervisor_research_grace_seconds: float = Field(
        default=0.0, description="Supervisor가 병렬 연구 실행 후 진행 전 대기할 유예 시간(초)"
    )
    supervisor_force_conduct_research_enabled: bool = Field(
        default_factory=lambda: (
            (get_optional_env("SUPERVISOR_FORCE_CONDUCT_RESEARCH_ENABLED", "true") or "true").strip().lower()
            in {"1", "true", "yes", "y"}
        ),
        description=(
            "Supervisor가 초기 반복에서 툴콜이 없으면 research_brief로 ConductResearch 1회를 강제할지 여부"
        ),
    )
    supervisor_force_conduct_research_until_iteration: int = Field(
        default_factory=lambda: int(get_optional_env("SUPERVISOR_FORCE_CONDUCT_RESEARCH_UNTIL", "1")),
        description=(
            "Supervisor 강제 ConductResearch 적용 임계 반복 수 (research_iterations <= 임계에서만 적용)"
        ),
    )
    researcher_min_iterations_before_compress: int = Field(
        default_factory=lambda: int(get_optional_env("RESEARCHER_MIN_ITERATIONS_BEFORE_COMPRESS", "1")),
        description=(
            "Researcher 단계에서 첫 응답에 tool_calls가 없을 때, 최소 몇 번 researcher 루프를 더 돌지 설정"
        ),
    )
    # === HITL 설정 ===
    max_revision_loops: int = Field(
        default=2, description="HITL 거부 시 보고서 개정 루프 최대 횟수"
    )

    # === LLM 모델 설정===
    research_model: str = Field(
        default_factory=lambda: get_optional_env("MODEL_NAME", "gpt-4.1"),
        description="연구용 메인 모델",
    )
    compression_model: str = Field(
        default_factory=lambda: get_optional_env("COMPRESSION_MODEL", "gpt-4o-2024-11-20"),
        description="압축용 경량 모델",
    )
    final_report_model: str = Field(
        default_factory=lambda: get_optional_env(
            "FINAL_REPORT_MODEL", 
            get_optional_env("MODEL_NAME", "gpt-4.1")
        ),
        description="최종 보고서용 모델",
    )

    # === 온도 설정 ===
    temperature: float = Field(
        default_factory=lambda: float(get_optional_env("TEMPERATURE", "0.1")),
        description="LLM 온도 설정",
    )

    # === MCP 서버 엔드포인트 설정 ===
    mcp_servers: Dict[str, str] = Field(
        default_factory=lambda: {
            "arxiv": get_optional_env("ARXIV_MCP_URL", "http://localhost:3000/mcp"),
            "tavily": get_optional_env("TAVILY_MCP_URL", "http://localhost:3001/mcp"),
            "serper": get_optional_env("SERPER_MCP_URL", "http://localhost:3002/mcp"),
        },
        description="MCP 서버 엔드포인트 매핑",
    )

    # === A2A 멀티 에이전트 설정 ===
    a2a_agent_endpoints: Dict[str, str] = Field(
        default_factory=lambda: {
            "planner": "http://localhost:8090",
            "researcher": "http://localhost:8091",
            "analysis": "http://localhost:8092",
            "writer": "http://localhost:8093",
        },
        description="A2A 멀티 에이전트 엔드포인트",
    )

    max_concurrent_research: int = Field(
        default=3, description="A2A 동시 연구 작업 최대 개수"
    )

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "ResearchConfig":
        """
        LangGraph의 RunnableConfig에서 ResearchConfig 인스턴스 생성

        LangGraph 실행 시 전달되는 config 매개변수에서 'configurable' 섹션을
        추출하여 ResearchConfig 객체로 변환합니다.

        Args:
            config (RunnableConfig, optional): LangGraph 실행 설정

        Returns:
            ResearchConfig: 설정 인스턴스
        """
        configurable = config.get("configurable", {}) if config else {}
        return cls(**{k: v for k, v in configurable.items() if v is not None})

    @classmethod
    def from_a2a_config(
        cls, config_dict: Optional[Dict[str, Any]] = None
    ) -> "ResearchConfig":
        """
        A2A 에이전트 설정 딕셔너리에서 ResearchConfig 인스턴스 생성

        A2A 에이전트의 config 딕셔너리를 ResearchConfig 객체로 변환합니다.

        Args:
            config_dict (dict, optional): A2A 에이전트 설정 딕셔너리

        Returns:
            ResearchConfig: 설정 인스턴스
        """
        if not config_dict:
            return cls()

        # A2A 설정 키 매핑 (필요시)
        mapped_config = {
            "allow_clarification": config_dict.get("allow_clarification", True),
            "max_researcher_iterations": config_dict.get(
                "max_researcher_iterations", 3
            ),
            "max_concurrent_research": config_dict.get("max_concurrent_research", 3),
            "max_concurrent_research_units": config_dict.get(
                "max_concurrent_research_units", 3
            ),
        }

        # 기타 설정 병합
        for key, value in config_dict.items():
            if key not in mapped_config and hasattr(cls, key):
                mapped_config[key] = value

        return cls(**mapped_config)

    def to_a2a_config(self) -> Dict[str, Any]:
        """
        ResearchConfig를 A2A 에이전트용 설정 딕셔너리로 변환

        Returns:
            dict: A2A 에이전트 설정 딕셔너리
        """
        return {
            "allow_clarification": self.allow_clarification,
            "max_researcher_iterations": self.max_researcher_iterations,
            "max_concurrent_research": self.max_concurrent_research
            or self.max_concurrent_research_units,
        }

    def to_langgraph_configurable(self) -> Dict[str, Any]:
        """
        ResearchConfig를 LangGraph configurable 딕셔너리로 변환

        Returns:
            dict: LangGraph configurable 설정
        """
        return self.model_dump(exclude_none=True)

    def get_llm_config(self, model_type: str = "research") -> Dict[str, Any]:
        """
        특정 용도의 LLM 설정 반환

        Args:
            model_type (str): "research", "compression", "final_report" 중 하나

        Returns:
            dict: LLM 모델명과 최대 토큰 수를 포함한 설정
        """
        if model_type == "research":
            return {
                "model": self.research_model,
                "temperature": self.temperature,
            }
        elif model_type == "compression":
            return {
                "model": self.compression_model,
                "temperature": 0,
            }
        elif model_type == "final_report":
            return {
                "model": self.final_report_model,
                "temperature": self.temperature,
            }
        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def get_mcp_endpoint(self, server_name: str) -> str | None:
        """
        특정 MCP 서버의 엔드포인트 반환

        Args:
            server_name (str): MCP 서버 이름 (tavily, arxiv, serper 등)

        Returns:
            str or None: 서버 엔드포인트 URL
        """
        return self.mcp_servers.get(server_name)

    def get_a2a_endpoint(self, agent_role: str) -> str | None:
        """
        특정 A2A 에이전트의 엔드포인트 반환

        Args:
            agent_role (str): 에이전트 역할 (planner, researcher, writer 등)

        Returns:
            str or None: 에이전트 엔드포인트 URL
        """
        return self.a2a_agent_endpoints.get(agent_role)

    @classmethod
    def validate_environment(cls) -> bool:
        """
        환경 변수 검증

        Returns:
            bool: 검증 성공 여부
        """
        return validate_environment(raise_on_error=False)

    def __init__(self, **data):
        """
        ResearchConfig 초기화 시 환경 변수 검증
        """
        # 환경 변수 검증 (경고)
        if not self.validate_environment():
            import warnings

            warnings.warn(
                "일부 환경 변수가 설정되지 않았습니다. "
                "src.utils.env_validator.print_env_report()를 실행하여 상세 정보를 확인하세요."
            )
        super().__init__(**data)
