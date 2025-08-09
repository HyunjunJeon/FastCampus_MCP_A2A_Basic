"""
LangGraph 기반 Deep Research Agent - 심층 연구 시스템

이 모듈은 LangGraph의 상태 그래프를 활용하여 
복잡한 연구 작업을 단계별로 수행하는 멀티 에이전트 시스템입니다.

=== 워크플로우 구조 ===
1. clarify_with_user      : 사용자 질문 명확화 및 추가 정보 요청
2. write_research_brief   : 명확화된 질문을 구체적인 연구 계획으로 변환
3. supervisor            : 연구 작업을 계획하고 researcher들을 조정
4. researcher            : MCP 도구를 사용하여 실제 정보 수집
5. compress_research     : 수집된 정보를 요약하고 중복 제거
6. final_report_generation: 최종 보고서 작성

=== MCP 도구 통합 ===
- Tavily Search MCP Server    : 실시간 웹 검색
- arXiv Papers MCP Server     : 학술 논문 검색
- Serper Google Search MCP    : Google 검색 엔진 활용

=== 상태 관리 ===
- AgentState      : 전체 에이전트 상태 (메시지, 노트, 보고서)
- SupervisorState : 연구 감독자 상태 (연구 반복, 진행 상황)
- ResearcherState : 개별 연구원 상태 (도구 호출, 수집 데이터)

=== 주요 특징 ===
- 병렬 연구 수행으로 효율성 극대화
- MCP 프로토콜을 통한 외부 도구 연동
- 구조화된 출력과 에러 처리
- 설정 가능한 연구 파라미터
"""

# 표준 라이브러리 임포트
from src.utils.logging_config import get_logger  # 로깅 및 디버깅
import time  # 성능 측정용 시간 함수
from typing import Annotated, Optional, Literal  # 타입 힌트

# 프롬프트 모듈 임포트
from src.lg_agents.deep_research.prompts import (
    get_today_str,
    clarify_with_user_instructions,
    transform_messages_into_research_topic_prompt,
    lead_researcher_prompt,
    final_report_generation_prompt,
)

from src.config import ResearchConfig
from src.lg_agents.base.base_graph_state import BaseGraphState

# LangChain 관련 임포트
from langchain.chat_models import init_chat_model
from langchain_core.messages import (  # LangChain 메시지 타입들
    HumanMessage,  # 사용자 메시지
    SystemMessage,  # 시스템 메시지
    AIMessage,  # AI 응답 메시지
    get_buffer_string,  # 메시지 버퍼를 문자열로 변환
)
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig  # 실행 설정 클래스

# LangGraph 관련 임포트
from langgraph.graph import START, END, StateGraph  # 상태 그래프 구성 요소
from langgraph.types import Command  # 노드 간 제어 흐름 명령

from .shared import override_reducer
from .supervisor_graph import build_supervisor_subgraph

# 데이터 모델 및 타입 정의
from pydantic import BaseModel, Field  # 데이터 유효성 검사 및 직렬화
 

# 로깅 설정
logger = get_logger(__name__)


# ==================== 구조화된 출력 모델 정의 ====================
class ClarifyWithUser(BaseModel):
    """
    사용자 질문 명확화를 위한 구조화된 출력 모델

    clarify_with_user 노드에서 사용자의 질문이 모호하거나 추가 정보가
    필요한 경우 명확화 질문을 생성하기 위해 사용됩니다.
    """

    need_clarification: bool = Field(
        description="사용자에게 명확화 질문이 필요한지 여부"
    )
    question: str = Field(description="보고서 범위를 명확히 하기 위한 질문")
    verification: str = Field(
        description="연구를 시작할 준비가 되었음을 확인하는 메시지"
    )


class ResearchQuestion(BaseModel):
    """
    연구 계획을 위한 구조화된 출력 모델

    write_research_brief 노드에서 사용자의 모호한 질문을 구체적이고
    실행 가능한 연구 질문으로 변환할 때 사용됩니다.
    """

    research_brief: str = Field(description="연구를 안내할 상세하고 구체적인 연구 질문")


# ==================== 상태 정의 및 리듀서 ====================
class AgentState(BaseGraphState):
    """
    전체 Deep Research 에이전트의 공유 상태

    모든 노드에서 접근 가능한 전역 상태를 정의합니다.
    LangGraph의 StateGraph에서 사용되며, 각 필드는 특정 리듀서를 가집니다.
    """

    supervisor_messages: Annotated[
        list, override_reducer
    ]  # 감독자 전용 메시지 (오버라이드 가능)
    research_brief: Optional[str]  # 연구 계획서
    raw_notes: Annotated[list[str], override_reducer]  # 원시 연구 노트들
    notes: Annotated[list[str], override_reducer]  # 처리된 연구 노트들
    final_report: str  # 최종 보고서


 
 
# ==================== Utility Functions ====================


# ==================== Helper Functions for Clarification ====================
async def _get_clarification_model(config: RunnableConfig) -> BaseChatModel:
    """명확화를 위한 LLM 모델 생성"""
    configurable = ResearchConfig.from_runnable_config(config)
    return (
        init_chat_model(
            model_provider="openai",
            model=configurable.research_model,
            temperature=0,
        )
        .with_structured_output(ClarifyWithUser)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    )


async def _check_clarification_needed(messages: list, model) -> ClarifyWithUser:
    """사용자 메시지에서 명확화 필요 여부 확인"""
    prompt = clarify_with_user_instructions.format(
        messages=get_buffer_string(messages),
        date=get_today_str()
    )
    return await model.ainvoke([HumanMessage(content=prompt)])


def _create_clarification_response(response: ClarifyWithUser) -> Command:
    """명확화 응답에 따른 Command 생성"""
    if response.need_clarification:
        return Command(
            goto=END, 
            update={"messages": [AIMessage(content=response.question)]}
        )
    else:
        return Command(
            goto="write_research_brief",
            update={"messages": [AIMessage(content=response.verification)]},
        )


# ==================== Main Nodes ====================
async def clarify_with_user(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["write_research_brief", "__end__"]]:
    """사용자에게 이 질문의 구체화가 필요한지 확인
    
    이 함수는 다음 단계로 분리됨:
    1. 명확화 허용 여부 확인
    2. LLM 모델 생성
    3. 명확화 필요성 체크
    4. 적절한 응답 반환
    """
    start_time = time.time()
    logger.info("Starting clarify_with_user")

    configurable = ResearchConfig.from_runnable_config(config)

    # 명확화가 비활성화된 경우 즉시 다음 단계로
    if not configurable.allow_clarification:
        logger.info(
            f"clarify_with_user completed in {time.time() - start_time:.2f}s (skipped)"
        )
        return Command(goto="write_research_brief")

    # 명확화 프로세스 실행
    messages = state["messages"]
    model = await _get_clarification_model(config)
    response = await _check_clarification_needed(messages, model)
    
    logger.info(f"clarify_with_user completed in {time.time() - start_time:.2f}s")
    
    return _create_clarification_response(response)


async def write_research_brief(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["research_supervisor"]]:
    """연구 계획 작성
    
    사용자 메시지를 구체적인 연구 질문으로 변환
    """
    start_time = time.time()
    logger.info("Starting write_research_brief")

    configurable = ResearchConfig.from_runnable_config(config)

    model = (
        init_chat_model(
            model_provider="openai",
            model=configurable.research_model,
            temperature=0,
        )
        .with_structured_output(ResearchQuestion)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    )

    messages = state.get("messages", [])
    
    # 프롬프트 모듈에서 임포트한 템플릿 사용
    transform_prompt = transform_messages_into_research_topic_prompt.format(
        messages=get_buffer_string(messages),
        date=get_today_str()
    )

    response = await model.ainvoke([HumanMessage(content=transform_prompt)])

    logger.info(f"write_research_brief completed in {time.time() - start_time:.2f}s")

    supervisor_prompt = lead_researcher_prompt.format(
        date=get_today_str(),
        max_concurrent_research_units=configurable.max_concurrent_research_units
    )

    return Command(
        goto="research_supervisor",
        update={
            "research_brief": response.research_brief,
            "supervisor_messages": {
                "type": "override",
                "value": [
                    SystemMessage(content=supervisor_prompt),
                    HumanMessage(content=response.research_brief),
                ],
            },
        },
    )


"""Supervisor/Researcher 서브그래프 구현은 별도 모듈로 이동"""


async def final_report_generation(state: AgentState, config: RunnableConfig):
    """최종 보고서 생성
    
    수집된 모든 연구 결과를 종합하여 최종 보고서 작성
    """
    start_time = time.time()
    logger.info("Starting final_report_generation")

    notes = state.get("notes", [])
    cleared_state = {"notes": {"type": "override", "value": []}}
    configurable = ResearchConfig.from_runnable_config(config)

    writer_model = init_chat_model(
        model_provider="openai",
        model=configurable.final_report_model,
        temperature=0,
    )

    findings = "\n".join(notes)
    messages = state.get("messages", [])

    # 프롬프트 모듈에서 임포트한 템플릿 사용
    final_report_prompt = final_report_generation_prompt.format(
        research_brief=state.get("research_brief", ""),
        messages=get_buffer_string(messages),
        date=get_today_str(),
        findings=findings
    )

    try:
        final_report = await writer_model.ainvoke(
            [HumanMessage(content=final_report_prompt)]
        )

        logger.info(f"final_report_generation completed in {time.time() - start_time:.2f}s")

        return {
            "final_report": final_report.content,
            "messages": [final_report],
            **cleared_state,
        }

    except Exception as e:
        logger.error(f"Final report generation error: {e}")
        logger.info(f"final_report_generation failed after {time.time() - start_time:.2f}s")
        return {"final_report": f"Error generating final report: {e}", **cleared_state}


deep_researcher_builder = StateGraph(state_schema=AgentState, config_schema=ResearchConfig)
deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder.add_node("write_research_brief", write_research_brief)
deep_researcher_builder.add_node("research_supervisor", build_supervisor_subgraph())
deep_researcher_builder.add_node("final_report_generation", final_report_generation)
deep_researcher_builder.add_edge(START, "clarify_with_user")
deep_researcher_builder.add_edge("research_supervisor", "final_report_generation")
deep_researcher_builder.add_edge("final_report_generation", END)

deep_research_graph = deep_researcher_builder.compile()
