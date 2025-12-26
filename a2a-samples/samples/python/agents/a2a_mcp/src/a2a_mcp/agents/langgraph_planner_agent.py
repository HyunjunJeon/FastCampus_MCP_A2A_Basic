"""LangGraph 기반 여행 계획 에이전트 모듈.

이 모듈은 LangGraph ReAct 에이전트를 사용하여 사용자의 여행 요청을
분석하고 실행 가능한 태스크 목록으로 분해합니다.

주요 기능:
    - 체인오브쏘트 기반 정보 수집
    - 구조화된 응답 형식 (ResponseFormat)
    - 세션 기반 대화 기록 관리
    - 멀티턴 대화 지원

생성 태스크:
    1. 항공권 예약
    2. 호텔 예약
    3. 렌터카 예약

Note:
    PLANNER_COT_INSTRUCTIONS는 영문으로 유지됩니다 (LLM 지시사항).
"""
# type: ignore

import logging

from collections.abc import AsyncIterable
from typing import Any, Literal

from a2a_mcp.common import prompts
from a2a_mcp.common.base_agent import BaseAgent
from a2a_mcp.common.types import TaskList
from a2a_mcp.common.utils import init_api_key
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field


memory = MemorySaver()
logger = logging.getLogger(__name__)


class ResponseFormat(BaseModel):
    """에이전트 응답 형식.

    Attributes:
        status: 응답 상태 (input_required, completed, error).
        question: 계획 생성을 위해 사용자에게 필요한 입력.
        content: 계획 생성 시 태스크 목록.
    """

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    question: str = Field(
        description='Input needed from the user to generate the plan'
    )
    content: TaskList = Field(
        description='List of tasks when the plan is generated'
    )


class LangGraphPlannerAgent(BaseAgent):
    """LangGraph 기반 여행 계획 에이전트.

    사용자 요청을 분석하고 실행 가능한 여행 태스크로 분해합니다.
    Gemini 모델과 MemorySaver 체크포인터를 사용합니다.

    Attributes:
        model: ChatGoogleGenerativeAI 모델.
        graph: LangGraph ReAct 에이전트 그래프.
    """

    def __init__(self):
        init_api_key()

        logger.info('Initializing LanggraphPlannerAgent')

        super().__init__(
            agent_name='PlannerAgent',
            description='Breakdown the user request into executable tasks',
            content_types=['text', 'text/plain'],
        )

        self.model = ChatGoogleGenerativeAI(
            model='gemini-2.0-flash', temperature=0.0
        )

        self.graph = create_react_agent(
            self.model,
            checkpointer=memory,
            prompt=prompts.PLANNER_COT_INSTRUCTIONS,
            # prompt=prompts.TRIP_PLANNER_INSTRUCTIONS_1,
            response_format=ResponseFormat,
            tools=[],
        )

    def invoke(self, query, sessionId) -> str:
        """에이전트를 동기적으로 호출합니다.

        Args:
            query: 사용자 질문.
            sessionId: 세션 ID.

        Returns:
            str: 에이전트 응답.
        """
        config = {'configurable': {'thread_id': sessionId}}
        self.graph.invoke({'messages': [('user', query)]}, config)
        return self.get_agent_response(config)

    async def stream(
        self, query, sessionId, task_id
    ) -> AsyncIterable[dict[str, Any]]:
        """계획 생성 과정을 스트리밍합니다.

        Args:
            query: 사용자 질문.
            sessionId: 세션 ID.
            task_id: 태스크 ID.

        Yields:
            dict: 중간 응답 및 최종 계획.
        """
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': sessionId}}

        logger.info(
            f'Running LanggraphPlannerAgent stream for session {sessionId} {task_id} with input {query}'
        )

        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]
            if isinstance(message, AIMessage):
                yield {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': message.content,
                }
        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        """그래프 상태에서 응답을 추출하고 형식화합니다.

        Args:
            config: LangGraph 설정 (thread_id 포함).

        Returns:
            dict: A2A 형식 응답.
        """
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')
        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            if (
                structured_response.status == 'input_required'
                # and structured_response.content.tasks
            ):
                return {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.question,
                }
            if structured_response.status == 'error':
                return {
                    'response_type': 'text',
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.question,
                }
            if structured_response.status == 'completed':
                return {
                    'response_type': 'data',
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.content.model_dump(),
                }
        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': 'We are unable to process your request at the moment. Please try again.',
        }
