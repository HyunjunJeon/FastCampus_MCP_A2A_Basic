"""LangGraph 기반 통화 변환 에이전트 모듈.

이 모듈은 LangGraph를 사용하여 환율 조회 기능을 제공하는 에이전트를 구현합니다.
Frankfurter API를 통해 실시간 환율 정보를 조회하고, 구조화된 응답 형식을
사용하여 대화 상태를 관리합니다.

주요 기능:
    - 실시간 환율 조회 (frankfurter.app API)
    - 구조화된 응답 형식 (completed, input_required, error)
    - 멀티턴 대화 지원 (MemorySaver를 통한 상태 유지)

클래스:
    ResponseFormat: 에이전트 응답의 구조화된 형식
    CurrencyAgent: 통화 변환 기능을 제공하는 LangGraph 에이전트

함수:
    get_exchange_rate: 환율을 조회하는 도구 함수
"""
import os

from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel


# 멀티턴 대화를 위한 메모리 저장소
memory = MemorySaver()


@tool
def get_exchange_rate(
    currency_from: str = 'USD',
    currency_to: str = 'EUR',
    currency_date: str = 'latest',
) -> dict[str, Any]:
    """현재 환율을 조회하는 도구입니다.

    Frankfurter API를 사용하여 두 통화 간의 환율을 조회합니다.
    이 함수는 LLM 에이전트의 도구로 등록되어 사용자의 환율 조회
    요청을 처리합니다.

    Args:
        currency_from: 변환 원본 통화 코드 (예: "USD"). 기본값: "USD".
        currency_to: 변환 대상 통화 코드 (예: "EUR"). 기본값: "EUR".
        currency_date: 환율 조회 날짜 또는 "latest". 기본값: "latest".

    Returns:
        dict[str, Any]: 환율 데이터가 포함된 딕셔너리. 오류 발생 시
            'error' 키가 포함된 딕셔너리를 반환합니다.

    Examples:
        >>> get_exchange_rate("USD", "EUR")
        {'amount': 1.0, 'base': 'USD', 'date': '2024-01-15', 'rates': {'EUR': 0.92}}
    """
    try:
        response = httpx.get(
            f'https://api.frankfurter.app/{currency_date}',
            params={'from': currency_from, 'to': currency_to},
        )
        response.raise_for_status()

        data = response.json()
        if 'rates' not in data:
            return {'error': 'Invalid API response format.'}
        return data
    except httpx.HTTPError as e:
        return {'error': f'API request failed: {e}'}
    except ValueError:
        return {'error': 'Invalid JSON response from API.'}


class ResponseFormat(BaseModel):
    """에이전트 응답의 구조화된 형식.

    LLM이 이 형식에 맞춰 응답을 생성하도록 강제합니다.
    상태(status)에 따라 대화 흐름을 제어합니다.

    Attributes:
        status: 응답 상태. 다음 중 하나:
            - 'input_required': 사용자로부터 추가 정보가 필요함
            - 'completed': 요청이 완료됨
            - 'error': 오류 발생
        message: 사용자에게 표시할 메시지.
    """

    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str


class CurrencyAgent:
    """통화 변환을 위한 특화된 어시스턴트 에이전트.

    LangGraph를 사용하여 환율 조회 도구를 갖춘 ReAct 에이전트를 구현합니다.
    통화 관련 주제 외의 질문에는 응답하지 않으며, 구조화된 응답 형식을
    사용하여 대화 상태를 관리합니다.

    Attributes:
        SYSTEM_INSTRUCTION: 에이전트의 동작을 정의하는 시스템 프롬프트.
        FORMAT_INSTRUCTION: 응답 형식을 정의하는 지시사항.
        model: LLM 모델 인스턴스 (Google Generative AI 또는 OpenAI).
        tools: 에이전트가 사용할 수 있는 도구 목록.
        graph: LangGraph로 생성된 ReAct 에이전트 그래프.
        SUPPORTED_CONTENT_TYPES: 지원되는 콘텐츠 타입 목록.
    """

    # 시스템 프롬프트 - 영문 유지 (LLM 지시사항)
    SYSTEM_INSTRUCTION = (
        'You are a specialized assistant for currency conversions. '
        "Your sole purpose is to use the 'get_exchange_rate' tool to answer questions about currency exchange rates. "
        'If the user asks about anything other than currency conversion or exchange rates, '
        'politely state that you cannot help with that topic and can only assist with currency-related queries. '
        'Do not attempt to answer unrelated questions or use tools for other purposes.'
    )

    # 응답 형식 지시사항 - 영문 유지 (LLM 지시사항)
    FORMAT_INSTRUCTION = (
        'Set response status to input_required if the user needs to provide more information to complete the request.'
        'Set response status to error if there is an error while processing the request.'
        'Set response status to completed if the request is complete.'
    )

    def __init__(self) -> None:
        """CurrencyAgent 인스턴스를 초기화합니다.

        환경 변수에 따라 Google Generative AI 또는 OpenAI 모델을 선택하고,
        get_exchange_rate 도구를 장착한 ReAct 에이전트를 생성합니다.
        """
        # 모델 소스 결정: 기본값은 Google
        model_source = os.getenv('model_source', 'google')
        if model_source == 'google':
            self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        else:
            # OpenAI 호환 커스텀 LLM 서버 사용
            self.model = ChatOpenAI(
                model=os.getenv('TOOL_LLM_NAME'),
                openai_api_key=os.getenv('API_KEY', 'EMPTY'),
                openai_api_base=os.getenv('TOOL_LLM_URL'),
                temperature=0,
            )
        self.tools = [get_exchange_rate]

        # LangGraph ReAct 에이전트 생성
        # - checkpointer: 멀티턴 대화를 위한 메모리 저장소
        # - prompt: 시스템 지시사항
        # - response_format: 구조화된 응답 형식
        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.FORMAT_INSTRUCTION, ResponseFormat),
        )

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        """사용자 쿼리를 처리하고 스트리밍 응답을 생성합니다.

        LangGraph 에이전트를 실행하고 중간 상태(도구 호출, 도구 결과)와
        최종 응답을 스트리밍합니다.

        Args:
            query: 사용자가 입력한 질문.
            context_id: 대화 컨텍스트를 식별하는 고유 ID (thread_id로 사용).

        Yields:
            dict[str, Any]: 다음 키를 포함하는 응답 딕셔너리:
                - is_task_complete: 태스크 완료 여부
                - require_user_input: 사용자 입력 필요 여부
                - content: 사용자에게 표시할 메시지

        Note:
            중간 상태에서는 'Looking up the exchange rates...'와
            'Processing the exchange rates..' 메시지를 반환합니다.
        """
        inputs = {'messages': [('user', query)]}
        config = {'configurable': {'thread_id': context_id}}

        # LangGraph 에이전트 실행 및 스트리밍
        for item in self.graph.stream(inputs, config, stream_mode='values'):
            message = item['messages'][-1]

            # 도구 호출 중인 경우
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Looking up the exchange rates...',
                }
            # 도구 결과가 반환된 경우
            elif isinstance(message, ToolMessage):
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': 'Processing the exchange rates..',
                }

        # 최종 응답 반환
        yield self.get_agent_response(config)

    def get_agent_response(self, config: dict[str, Any]) -> dict[str, Any]:
        """에이전트의 현재 상태에서 응답을 추출합니다.

        LangGraph의 상태에서 구조화된 응답(ResponseFormat)을 가져와
        A2A 프로토콜에 맞는 형식으로 변환합니다.

        Args:
            config: LangGraph 설정 딕셔너리 (thread_id 포함).

        Returns:
            dict[str, Any]: 다음 키를 포함하는 응답 딕셔너리:
                - is_task_complete: 태스크 완료 여부
                - require_user_input: 사용자 입력 필요 여부
                - content: 사용자에게 표시할 메시지
        """
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')

        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            # 'input_required': 사용자 입력 필요
            if structured_response.status == 'input_required':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            # 'error': 오류 발생
            if structured_response.status == 'error':
                return {
                    'is_task_complete': False,
                    'require_user_input': True,
                    'content': structured_response.message,
                }
            # 'completed': 태스크 완료
            if structured_response.status == 'completed':
                return {
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': structured_response.message,
                }

        # 구조화된 응답이 없는 경우 기본 오류 메시지
        return {
            'is_task_complete': False,
            'require_user_input': True,
            'content': (
                'We are unable to process your request at the moment. '
                'Please try again.'
            ),
        }

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']
