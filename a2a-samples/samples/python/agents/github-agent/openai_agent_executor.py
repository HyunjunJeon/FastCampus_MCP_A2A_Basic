"""OpenAI 기반 AgentExecutor 모듈.

이 모듈은 OpenAI API (OpenRouter 경유)를 사용하여 도구 호출을
처리하는 AgentExecutor 구현을 제공합니다. Claude 3.5 Sonnet 모델을
사용하여 GitHub API 도구와 상호작용합니다.

주요 기능:
    - OpenAI 함수 호출 형식으로 도구 스키마 자동 생성
    - 반복적인 도구 호출 루프 처리
    - Pydantic 모델 직렬화 지원
"""
import json
import logging

from typing import Any

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCard,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError
from openai import AsyncOpenAI


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class OpenAIAgentExecutor(AgentExecutor):
    """OpenAI 기반 에이전트를 실행하는 AgentExecutor.

    OpenRouter를 통해 Claude 3.5 Sonnet 모델을 사용하며,
    Python 함수에서 OpenAI 함수 호출 스키마를 자동으로 생성합니다.

    Attributes:
        _card: AgentCard 인스턴스. 에이전트 메타데이터.
        tools: 도구 이름을 키로, 도구 인스턴스를 값으로 하는 딕셔너리.
        client: AsyncOpenAI 클라이언트. OpenRouter API 사용.
        model: 사용할 모델 ID (기본값: 'anthropic/claude-3.5-sonnet').
        system_prompt: 에이전트 동작을 정의하는 시스템 프롬프트.
    """

    def __init__(
        self,
        card: AgentCard,
        tools: dict[str, Any],
        api_key: str,
        system_prompt: str,
    ) -> None:
        """OpenAIAgentExecutor 인스턴스를 초기화합니다.

        Args:
            card: AgentCard 인스턴스.
            tools: 도구 딕셔너리.
            api_key: OpenRouter API 키.
            system_prompt: 시스템 프롬프트.
        """
        self._card = card
        self.tools = tools
        # OpenRouter API를 통해 OpenAI 클라이언트 초기화
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url='https://openrouter.ai/api/v1',
            default_headers={
                'HTTP-Referer': 'http://localhost:10007',
                'X-Title': 'GitHub Agent',
            },
        )
        self.model = 'anthropic/claude-3.5-sonnet'
        self.system_prompt = system_prompt

    async def _process_request(
        self,
        message_text: str,
        context: RequestContext,
        task_updater: TaskUpdater,
    ) -> None:
        """사용자 요청을 처리하고 도구 호출 루프를 실행합니다.

        최대 10번의 반복까지 도구 호출을 처리하며,
        최종 응답이 생성되면 아티팩트로 저장합니다.

        Args:
            message_text: 사용자 메시지 텍스트.
            context: 요청 컨텍스트.
            task_updater: 태스크 상태 업데이터.
        """
        # 대화 히스토리 초기화
        messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': message_text},
        ]

        # 도구를 OpenAI 함수 호출 형식으로 변환
        openai_tools = []
        for tool_name, tool_instance in self.tools.items():
            if hasattr(tool_instance, tool_name):
                func = getattr(tool_instance, tool_name)
                # 메서드에서 함수 스키마 추출
                schema = self._extract_function_schema(func)
                openai_tools.append({'type': 'function', 'function': schema})

        max_iterations = 10
        iteration = 0

        # 도구 호출 루프 (최대 10회 반복)
        while iteration < max_iterations:
            iteration += 1

            try:
                # OpenAI API 호출
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                    tool_choice='auto' if openai_tools else None,
                    temperature=0.1,
                    max_tokens=4000,
                )

                message = response.choices[0].message

                # 어시스턴트 응답을 메시지에 추가
                messages.append(
                    {
                        'role': 'assistant',
                        'content': message.content,
                        'tool_calls': message.tool_calls,
                    }
                )

                # 도구 호출이 있는지 확인
                if message.tool_calls:
                    # 도구 호출 실행
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        logger.debug(
                            f'Calling function: {function_name} with args: {function_args}'
                        )

                        # 함수 실행
                        if function_name in self.tools:
                            tool_instance = self.tools[function_name]
                            # 인스턴스에서 메서드 가져오기
                            if hasattr(tool_instance, function_name):
                                method = getattr(tool_instance, function_name)
                                result = method(**function_args)
                            else:
                                result = {
                                    'error': f'Method {function_name} not found on tool instance'
                                }
                        else:
                            result = {
                                'error': f'Function {function_name} not found'
                            }

                        # 결과 직렬화 - Pydantic 모델 처리
                        if hasattr(result, 'model_dump'):
                            # Pydantic 모델: model_dump()로 딕셔너리 변환
                            result_json = json.dumps(result.model_dump())
                        elif isinstance(result, dict):
                            # 일반 딕셔너리
                            result_json = json.dumps(result)
                        else:
                            # 폴백: 문자열로 변환
                            result_json = str(result)

                        # 도구 결과를 메시지에 추가
                        messages.append(
                            {
                                'role': 'tool',
                                'tool_call_id': tool_call.id,
                                'content': result_json,
                            }
                        )

                    # 처리 중 상태 업데이트 전송
                    await task_updater.update_status(
                        TaskState.working,
                        message=task_updater.new_agent_message(
                            [TextPart(text='Processing tool calls...')]
                        ),
                    )

                    # 최종 응답을 얻기 위해 루프 계속
                    continue

                # 더 이상 도구 호출 없음: 최종 응답
                if message.content:
                    parts = [TextPart(text=message.content)]
                    logger.debug(f'Yielding final response: {parts}')
                    await task_updater.add_artifact(parts)
                    await task_updater.complete()
                break

            except Exception as e:
                logger.error(f'Error in OpenAI API call: {e}')
                error_parts = [
                    TextPart(
                        text=f'Sorry, an error occurred while processing the request: {e!s}'
                    )
                ]
                await task_updater.add_artifact(error_parts)
                await task_updater.complete()
                break

        # 최대 반복 횟수 초과
        if iteration >= max_iterations:
            error_parts = [
                TextPart(
                    text='Sorry, the request has exceeded the maximum number of iterations.'
                )
            ]
            await task_updater.add_artifact(error_parts)
            await task_updater.complete()

    def _extract_function_schema(self, func) -> dict:
        """Python 함수에서 OpenAI 함수 스키마를 추출합니다.

        함수의 시그니처와 docstring을 분석하여 OpenAI 함수 호출
        형식의 스키마를 생성합니다.

        Args:
            func: 스키마를 추출할 Python 함수.

        Returns:
            dict: OpenAI 함수 호출 형식의 스키마.
        """
        import inspect

        # 함수 시그니처 가져오기
        sig = inspect.signature(func)

        # docstring 가져오기
        docstring = inspect.getdoc(func) or ''

        # docstring에서 설명과 파라미터 정보 추출
        lines = docstring.split('\n')
        description = lines[0] if lines else func.__name__

        # 파라미터 스키마 구성
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            param_type = 'string'  # 기본 타입
            param_description = f'Parameter {param_name}'

            # 어노테이션에서 타입 추론
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = 'integer'
                elif param.annotation == float:
                    param_type = 'number'
                elif param.annotation == bool:
                    param_type = 'boolean'
                elif param.annotation == list:
                    param_type = 'array'
                elif param.annotation == dict:
                    param_type = 'object'

            # 기본값이 없으면 필수 파라미터
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

            properties[param_name] = {
                'type': param_type,
                'description': param_description,
            }

        return {
            'name': func.__name__,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required,
            },
        }

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """사용자 요청을 처리합니다.

        태스크를 제출하고 작업을 시작한 후, 메시지 텍스트를 추출하여
        요청 처리 루프를 실행합니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.
        """
        # 완료될 때까지 에이전트 실행
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # 태스크 제출 즉시 알림
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        # 메시지 파트에서 텍스트 추출
        message_text = ''
        for part in context.message.parts:
            if isinstance(part.root, TextPart):
                message_text += part.root.text

        await self._process_request(message_text, context, updater)
        logger.debug('[GitHub Agent] execute exiting')

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """태스크 취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.

        Args:
            context: 요청 컨텍스트.
            event_queue: 이벤트 큐.

        Raises:
            ServerError: UnsupportedOperationError와 함께 발생.
        """
        raise ServerError(error=UnsupportedOperationError())
