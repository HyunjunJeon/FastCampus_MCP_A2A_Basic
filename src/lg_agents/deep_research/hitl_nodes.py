"""
HITL(Human-In-The-Loop) 노드 및 상태

기존 `deep_research_agent_hitl.py`에서 사용하던 HITL 상태/노드를
공용으로 재배치하여 A2A 그래프 내부에서 재사용할 수 있도록 제공합니다.
"""

from __future__ import annotations

from typing import Optional, Literal

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from src.utils.logging_config import get_logger
from src.config import ResearchConfig
from src.hitl.manager import hitl_manager
from src.hitl.models import ApprovalType, ApprovalStatus

from .deep_research_agent import (
    AgentState,
    final_report_generation,
)


logger = get_logger(__name__)


class HITLAgentState(AgentState):
    """HITL 확장 상태 스키마 (AgentState 상위 호환)

    - revision_count: 개정 루프 횟수
    - human_feedback: 사람이 남긴 피드백(거부 사유 등)
    """

    endpoints: list[str]
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
        logger.info("HITL 최종 승인 완료")
        return Command(goto=END, update={"approval_decision": approved.decision})

    if approved.status == ApprovalStatus.REJECTED:
        feedback = approved.decision_reason or "개선 요청사항을 반영해주세요."
        logger.info("HITL 거부: 개정 단계로 이동")
        return Command(
            goto="revise_final_report",
            update={"human_feedback": feedback},
        )

    logger.warning("HITL 승인 대기 중 타임아웃/기타 상태 발생, 종료합니다.")
    return Command(goto=END)


async def revise_final_report(state: HITLAgentState, config: RunnableConfig):
    """사람 피드백을 반영하여 최종 보고서를 개정

    - revision_count를 증가시키고, 한도를 초과하면 종료
    - 개정된 보고서를 생성 후 다시 승인 요청 단계로 이동
    - 최종 보고서 생성 로직은 기존 `final_report_generation`과 동일 경로를 사용해
      프롬프트 및 모델 구성을 일관화합니다.
    """
    configurable = ResearchConfig.from_runnable_config(config)
    max_loops = getattr(configurable, "max_revision_loops", 2)

    current_count = int(state.get("revision_count", 0))
    if current_count >= max_loops:
        logger.warning("개정 한도 초과, 종료합니다.")
        return {"revision_count": current_count, "final_report": state.get("final_report", "")}

    feedback = state.get("human_feedback") or ""

    prev_messages = state.get("messages", [])
    feedback_msg = HumanMessage(
        content=(
            "[HITL 피드백] "
            + feedback
            + "\n\n위 피드백을 반영해 전체 보고서를 개선해 주세요."
        )
    )

    existing_notes = state.get("notes", []) or []
    provisional_notes = existing_notes if existing_notes else [state.get("final_report", "")]

    temp_state = dict(state)
    temp_state["messages"] = list(prev_messages) + [feedback_msg]
    temp_state["notes"] = provisional_notes

    improved_update = await final_report_generation(temp_state, config)

    combined_messages = [feedback_msg] + improved_update.get("messages", [])

    return Command(
        goto="hitl_final_approval",
        update={
            **{k: v for k, v in improved_update.items() if k != "messages"},
            "messages": combined_messages,
            "revision_count": current_count + 1,
        },
    )


