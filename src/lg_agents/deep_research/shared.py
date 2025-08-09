"""
Deep Research 공용 유틸 및 스키마

이 모듈은 연구 서브그래프들 간에 공유되는 헬퍼와 도구 스키마를 제공합니다.
"""

from __future__ import annotations

import operator

from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field


def override_reducer(current_value, new_value):
    """상태 업데이트용 오버라이드 리듀서"""
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)


def get_notes_from_tool_calls(messages: list) -> list[str]:
    """도구 호출 메시지에서 노트 추출"""
    notes: list[str] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            notes.append(msg.content)
    return notes


class ConductResearch(BaseModel):
    """연구 수행을 위한 구조화된 출력 도구 스키마"""

    research_topic: str = Field(
        description="연구할 주제. 단일 주제여야 하며 최소 한 문단 이상으로 상세히 기술"
    )


class ResearchComplete(BaseModel):
    """연구 완료 신호 도구 스키마"""

    pass


