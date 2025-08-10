"""
Deep Research LangGraph + HITL 승인 루프 통합 그래프

이 모듈은 기존 `deep_research_agent.py`의 그래프에
최종 보고서에 대한 Human-In-The-Loop(HITL) 승인/개정 루프를 결합한
새로운 그래프를 정의합니다. (Step 4 전용)

목표:
- 최종 보고서 생성 이후 사람 승인 요청 → 승인/거부에 따른 분기
- 거부 시 피드백을 반영하여 보고서를 개정하고 재승인 요청
- 반복 횟수 한도(`max_revision_loops`)를 초과하면 안전 종료

주의:
- Step 3는 기존 `deep_research_graph`를 그대로 사용합니다.
- 본 모듈은 Step 4에서만 임포트하여 사용하세요.
"""

from __future__ import annotations

from typing import Optional, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command

from src.utils.logging_config import get_logger
from src.config import ResearchConfig
from src.hitl.manager import hitl_manager
from src.hitl.models import ApprovalType, ApprovalStatus

# 기존 Deep Research 구성 요소 재사용
from .deep_research_agent import (
    AgentState,
    write_research_brief,
    final_report_generation,
)
from .supervisor_a2a_graph import build_supervisor_a2a_graph
from .shared import override_reducer  # noqa: F401


logger = get_logger(__name__)


class HITLAgentState(AgentState):
    """HITL 확장 상태 스키마 (AgentState 상위 호환)

    - revision_count: 개정 루프 횟수
    - human_feedback: 사람이 남긴 피드백(거부 사유 등)
    """

    revision_count: int
    human_feedback: Optional[str]


async def hitl_final_approval(
    state: HITLAgentState, config: RunnableConfig
) -> Command[Literal["__end__", "revise_final_report"]]:
    """최종 보고서에 대한 사람 승인 요청 및 대기

    승인되면 종료, 거부되면 피드백을 상태에 저장하고 개정 노드로 이동합니다.
    """
    # Config은 현재 노드에서 직접 사용하지 않음(향후 확장 대비)
    ResearchConfig.from_runnable_config(config)

    # 최종 보고서 내용 (상세보기에서 표시할 수 있도록 컨텍스트에 포함)
    final_report_text: str = state.get("final_report", "")
    research_brief: str = state.get("research_brief", "")
    notes = state.get("notes", [])

    # 승인 요청 생성 (연구 자동 실행 트리거 방지: 제목/설명에 '연구' 키워드 피함)
    request = await hitl_manager.request_approval(
        agent_id="deep_research_graph_hitl",
        approval_type=ApprovalType.FINAL_REPORT,
        title="최종 보고서 승인 요청",
        description="최종 보고서에 대한 검토 및 승인 요청입니다.",
        context={
            "task_id": state.get("task_id", "deep_research_task"),
            "research_brief": research_brief,
            "notes_count": len(notes) if isinstance(notes, list) else 0,
            "final_report": final_report_text,
        },
        options=["승인", "거부"],
        timeout_seconds=600,
        priority="high",
    )

    approved = await hitl_manager.wait_for_approval(
        request.request_id, auto_approve_on_timeout=False
    )

    if approved.status in (ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED):
        # 승인됨 → 종료
        logger.info("HITL 최종 승인 완료")
        return Command(goto=END, update={"approval_decision": approved.decision})

    if approved.status == ApprovalStatus.REJECTED:
        # 거부 → 피드백 반영 개정 단계로 이동
        feedback = approved.decision_reason or "개선 요청사항을 반영해주세요."
        logger.info("HITL 거부: 개정 단계로 이동")
        return Command(
            goto="revise_final_report",
            update={"human_feedback": feedback},
        )

    # 타임아웃 등 → 종료 처리
    logger.warning("HITL 승인 대기 중 타임아웃/기타 상태 발생, 종료합니다.")
    return Command(goto=END)


async def revise_final_report(state: HITLAgentState, config: RunnableConfig):
    """사람 피드백을 반영하여 최종 보고서를 개정

    - revision_count를 증가시키고, 한도를 초과하면 종료
    - 개정된 보고서를 생성 후 다시 승인 요청 단계로 이동
    """
    configurable = ResearchConfig.from_runnable_config(config)
    max_loops = getattr(configurable, "max_revision_loops", 2)

    current_count = int(state.get("revision_count", 0))
    if current_count >= max_loops:
        logger.warning("개정 한도 초과, 종료합니다.")
        return {"revision_count": current_count, "final_report": state.get("final_report", "")}

    feedback = state.get("human_feedback") or ""
    final_report = state.get("final_report", "")

    # 피드백 기반 개정 프롬프트
    system_prompt = (
        "아래의 사람 피드백을 면밀히 반영하여 보고서를 개선하세요."
        " 명확성, 근거, 구조, 출처 표기를 강화하고, 과장 표현을 자제합니다."
    )
    human_prompt = f"사람 피드백:\n{feedback}\n\n기존 보고서:\n{final_report}"

    model_cfg = configurable.get_llm_config("final_report")
    model = init_chat_model(
        model_provider="openai",
        model=model_cfg["model"],
        temperature=model_cfg.get("temperature", 0.1),
    )

    try:
        response = await model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        )
        improved_report = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(f"보고서 개정 중 오류: {e}")
        improved_report = final_report  # 실패 시 기존 보고서 유지

    return Command(
        goto="hitl_final_approval",
        update={
            "final_report": improved_report,
            "revision_count": current_count + 1,
        },
    )


# 그래프 구성: 기존 파이프라인 + HITL 루프
_builder = StateGraph(state_schema=HITLAgentState, config_schema=ResearchConfig)
_builder.add_node("write_research_brief", write_research_brief)
_builder.add_node("research_supervisor", build_supervisor_a2a_graph())
_builder.add_node("final_report_generation", final_report_generation)
_builder.add_node("hitl_final_approval", hitl_final_approval)
_builder.add_node("revise_final_report", revise_final_report)

_builder.add_edge(START, "write_research_brief")
_builder.add_edge("research_supervisor", "final_report_generation")
_builder.add_edge("final_report_generation", "hitl_final_approval")
_builder.add_edge("revise_final_report", "hitl_final_approval")
_builder.add_edge("hitl_final_approval", END)

deep_research_graph_with_hitl = _builder.compile()


