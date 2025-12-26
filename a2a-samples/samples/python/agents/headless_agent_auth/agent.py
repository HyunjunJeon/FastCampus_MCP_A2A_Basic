"""HR 에이전트 구현 모듈.

이 모듈은 LangGraph와 Auth0를 사용하여 직원 재직 상태를
확인하는 HR(인사) 에이전트를 구현합니다.

주요 기능:
    - 직원 ID 또는 이메일로 재직 상태 확인
    - Auth0 CIBA를 통한 비동기 사용자 인증
    - LangGraph ReAct 에이전트 패턴
    - 스트리밍 응답 지원

인증 흐름:
    1. 클라이언트가 직원 정보 요청
    2. 에이전트가 is_active_employee 도구 호출
    3. Auth0 CIBA로 해당 직원에게 승인 요청
    4. 승인 시 HR API에서 재직 상태 조회

Note:
    SYSTEM_INSTRUCTION과 RESPONSE_FORMAT_INSTRUCTION은
    영문으로 유지됩니다 (LLM 지시사항).
"""
import os

from collections.abc import AsyncIterable
from typing import Any, Literal

import httpx

from auth0.authentication.get_token import GetToken
from auth0.management import Auth0
from auth0_ai_langchain.auth0_ai import Auth0AI
from auth0_ai_langchain.ciba import get_ciba_credentials
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel


# Auth0 AI 클라이언트 초기화
auth0_ai = Auth0AI(
    auth0={
        'domain': os.getenv('HR_AUTH0_DOMAIN'),
        'client_id': os.getenv('HR_AGENT_AUTH0_CLIENT_ID'),
        'client_secret': os.getenv('HR_AGENT_AUTH0_CLIENT_SECRET'),
    }
)


# CIBA (Client Initiated Backchannel Authentication) 설정
# 직원에게 비동기적으로 승인 요청을 보냄
with_async_user_confirmation = auth0_ai.with_async_user_confirmation(
    binding_message='Approve sharing your employment details with an external party.',
    scopes=['read:employee'],
    user_id=lambda employee_id, **__: employee_id,
    audience=os.getenv('HR_API_AUTH0_AUDIENCE'),
    on_authorization_request='block',  # 데모용: 승인될 때까지 블록
)


# Auth0 토큰 발급 클라이언트
get_token = GetToken(
    domain=os.getenv('HR_AUTH0_DOMAIN'),
    client_id=os.getenv('HR_AGENT_AUTH0_CLIENT_ID'),
    client_secret=os.getenv('HR_AGENT_AUTH0_CLIENT_SECRET'),
)


@tool
async def is_active_employee(employee_id: str) -> dict[str, Any]:
    """직원의 재직 상태를 확인합니다.

    HR API를 호출하여 해당 직원이 현재 재직 중인지 확인합니다.
    CIBA를 통해 얻은 인증 정보를 사용합니다.

    Args:
        employee_id: 직원 식별자.

    Returns:
        dict: 재직 상태 정보.
            - active (bool): 재직 중 여부
            - error (str): 오류 발생 시 오류 메시지
    """
    try:
        credentials = get_ciba_credentials()
        response = await httpx.AsyncClient().get(
            f'{os.getenv("HR_API_BASE_URL", "http://localhost:10051")}/employees/{employee_id}',
            headers={
                'Authorization': f'{credentials["token_type"]} {credentials["access_token"]}',
                'Content-Type': 'application/json',
            },
        )

        if response.status_code == 404:
            return {'active': False}
        if response.status_code == 200:
            return {'active': True}
        response.raise_for_status()
    except httpx.HTTPError as e:
        return {'error': f'HR API request failed: {e}'}
    except Exception:
        return {'error': 'Unexpected response from HR API.'}


@tool
def get_employee_id_by_email(work_email: str) -> dict[str, Any] | None:
    """이메일로 직원 ID를 조회합니다.

    Auth0 Management API를 사용하여 이메일 주소로
    해당 직원의 user_id를 검색합니다.

    Args:
        work_email: 직원의 업무용 이메일 주소.

    Returns:
        dict: 직원 ID 정보.
            - employee_id (str): 직원 식별자
            - error (str): 오류 발생 시 오류 메시지
        None: 직원을 찾을 수 없는 경우
    """
    try:
        user = Auth0(
            domain=get_token.domain,
            token=get_token.client_credentials(
                f'https://{os.getenv("HR_AUTH0_DOMAIN")}/api/v2/'
            )['access_token'],
        ).users_by_email.search_users_by_email(
            email=work_email, fields=['user_id']
        )[0]

        return {'employee_id': user['user_id']} if user else None
    except Exception:
        return {'error': 'Unexpected response from Auth0 Management API.'}


class ResponseFormat(BaseModel):
    """에이전트 응답 형식 모델.

    LangGraph ReAct 에이전트의 구조화된 응답 형식을 정의합니다.

    Attributes:
        status: 태스크 상태.
            - completed: 요청 처리 완료
            - input-required: 추가 입력 필요
            - rejected: 사용자가 인증 거부
            - failed: 처리 실패
        message: 사용자에게 전달할 메시지.
    """

    status: Literal['completed', 'input-required', 'rejected', 'failed'] = (
        'failed'
    )
    message: str


class HRAgent:
    """HR 에이전트 클래스.

    LangGraph ReAct 패턴을 사용하여 직원 재직 상태 확인
    요청을 처리합니다. Auth0를 통한 인증이 필요합니다.

    Attributes:
        SUPPORTED_CONTENT_TYPES: 지원하는 콘텐츠 타입.
        SYSTEM_INSTRUCTION: 에이전트 시스템 프롬프트 (영문 유지).
        RESPONSE_FORMAT_INSTRUCTION: 응답 형식 지시사항 (영문 유지).
        model: Gemini 2.0 Flash 모델.
        tools: 사용 가능한 도구 목록.
        graph: LangGraph ReAct 에이전트 그래프.
    """

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    # 시스템 프롬프트 (영문 유지 - LLM 지시사항)
    SYSTEM_INSTRUCTION: str = (
        'You are an agent who handles external verification requests about Staff0 employees made by third parties.'
        'Do not attempt to answer unrelated questions or use tools for other purposes.'
        "If you are asked about a person's employee status using their employee ID, use the `is_active_employee` tool."
        'If they provide a work email instead, first call the `get_employee_id_by_email` tool to get the employee ID, and then use `is_active_employee`.'
    )

    # 응답 형식 지시사항 (영문 유지 - LLM 지시사항)
    RESPONSE_FORMAT_INSTRUCTION: str = (
        'Set the status to "completed" if the request has been fully processed.'
        'Set the status to "input-required" if the tool response indicates that user input is needed to proceed.'
        'If the tool response contains an AccessDeniedInterrupt error, set the message to "The user denied the authorization request", and set the status to "rejected".'
        'For any other tool error, set the status to "failed".'
    )

    def __init__(self) -> None:
        """HRAgent 인스턴스를 초기화합니다.

        Gemini 모델과 도구를 설정하고 LangGraph ReAct
        에이전트 그래프를 생성합니다.
        """
        self.model = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
        self.tools = [
            get_employee_id_by_email,
            with_async_user_confirmation(is_active_employee),
        ]

        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=MemorySaver(),  # 대화 상태 메모리 저장
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=(self.RESPONSE_FORMAT_INSTRUCTION, ResponseFormat),
        )

    async def invoke(self, query: str, context_id: str) -> dict[str, Any]:
        """에이전트를 호출하여 쿼리를 처리합니다.

        Args:
            query: 사용자 쿼리 문자열.
            context_id: 대화 컨텍스트 ID.

        Returns:
            dict: 에이전트 응답. is_task_complete, task_state, content 포함.
        """
        config: RunnableConfig = {'configurable': {'thread_id': context_id}}
        await self.graph.ainvoke({'messages': [('user', query)]}, config)
        return self.get_agent_response(config)

    async def stream(
        self, query: str, context_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """에이전트 응답을 스트리밍합니다.

        쿼리 처리 중 진행 상황을 실시간으로 yield하고,
        완료 시 최종 응답을 반환합니다.

        Args:
            query: 사용자 쿼리 문자열.
            context_id: 대화 컨텍스트 ID.

        Yields:
            dict: 진행 상황 또는 최종 응답.
                - is_task_complete (bool): 완료 여부
                - task_state (str): 태스크 상태
                - content (str): 메시지 내용
        """
        inputs: dict[str, Any] = {'messages': [('user', query)]}
        config: RunnableConfig = {'configurable': {'thread_id': context_id}}

        async for item in self.graph.astream(
            inputs, config, stream_mode='values'
        ):
            message = item['messages'][-1] if 'messages' in item else None
            if message:
                if (
                    isinstance(message, AIMessage)
                    and message.tool_calls
                    and len(message.tool_calls) > 0
                ):
                    # 도구 호출 중
                    yield {
                        'is_task_complete': False,
                        'task_state': 'working',
                        'content': 'Looking up the employment status...',
                    }
                elif isinstance(message, ToolMessage):
                    # 도구 응답 처리 중
                    yield {
                        'is_task_complete': False,
                        'task_state': 'working',
                        'content': 'Processing the employment status...',
                    }

        # 최종 응답 반환
        yield self.get_agent_response(config)

    def get_agent_response(self, config: RunnableConfig) -> dict[str, Any]:
        """구조화된 에이전트 응답을 가져옵니다.

        LangGraph 상태에서 structured_response를 추출하여
        표준 응답 형식으로 변환합니다.

        Args:
            config: LangGraph 실행 설정.

        Returns:
            dict: 표준화된 에이전트 응답.
        """
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get('structured_response')

        if structured_response and isinstance(
            structured_response, ResponseFormat
        ):
            return {
                'is_task_complete': structured_response.status == 'completed',
                'task_state': structured_response.status,
                'content': structured_response.message,
            }

        # 기본 응답 (구조화된 응답 없음)
        return {
            'is_task_complete': False,
            'task_state': 'unknown',
            'content': 'We are unable to process your request at the moment. Please try again.',
        }
