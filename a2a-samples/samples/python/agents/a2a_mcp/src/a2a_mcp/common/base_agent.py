"""에이전트 기본 클래스 모듈.

이 모듈은 모든 여행 에이전트의 기본 클래스를 정의합니다.

주요 기능:
    - Pydantic 기반 에이전트 설정 검증
    - ABC를 통한 추상 메서드 정의
    - 공통 에이전트 속성 제공
"""
# type: ignore
from abc import ABC

from pydantic import BaseModel, Field


class BaseAgent(BaseModel, ABC):
    """모든 여행 에이전트의 기본 클래스.

    Pydantic BaseModel과 ABC를 상속하여 설정 검증과
    추상 메서드 정의를 지원합니다.

    Attributes:
        agent_name: 에이전트 이름.
        description: 에이전트 목적 설명.
        content_types: 지원하는 콘텐츠 유형 목록.
    """

    model_config = {
        'arbitrary_types_allowed': True,
        'extra': 'allow',
    }

    agent_name: str = Field(
        description='The name of the agent.',
    )

    description: str = Field(
        description="A brief description of the agent's purpose.",
    )

    content_types: list[str] = Field(description='Supported content types.')
