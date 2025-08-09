"""
A2A (Agent-to-Agent) 통합 모듈
LangGraph Agent를 A2A 프로토콜로 래핑하여 에이전트 간 통신 지원
"""

from .a2a_lg_utils import (
    to_a2a_starlette_server,
    to_a2a_run_uvicorn,
    create_agent_card,
)

__all__ = [
    "to_a2a_starlette_server",
    "to_a2a_run_uvicorn",
    "create_agent_card",
]