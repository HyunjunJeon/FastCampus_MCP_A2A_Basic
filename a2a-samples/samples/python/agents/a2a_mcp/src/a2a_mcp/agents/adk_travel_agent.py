"""ADK 기반 여행 에이전트 모듈.

이 모듈은 Google ADK(Agent Development Kit)를 사용하여 여행 예약
기능을 제공하는 에이전트를 구현합니다.

주요 기능:
    - MCP 도구셋을 통한 여행 데이터 접근
    - LiteLLM 기반 모델 지원
    - 스트리밍 응답 처리
    - JSON 응답 파싱 및 포맷팅

지원 예약 유형:
    - 항공권 예약 (Air Ticketing)
    - 호텔 예약 (Hotel Booking)
    - 렌터카 예약 (Car Rental)

Note:
    instruction 파라미터는 영문으로 전달됩니다 (LLM 지시사항).
"""
# type: ignore

import json
import logging
import re

from collections.abc import AsyncIterable
from typing import Any

from a2a_mcp.common.agent_runner import AgentRunner
from a2a_mcp.common.base_agent import BaseAgent
from a2a_mcp.common.utils import get_mcp_server_config, init_api_key
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams
from google.genai import types as genai_types


logger = logging.getLogger(__name__)


class TravelAgent(BaseAgent):
    """ADK 기반 여행 에이전트.

    MCP 도구셋을 사용하여 여행 데이터에 접근하고 예약 작업을
    처리합니다. 항공권, 호텔, 렌터카 예약을 지원합니다.

    Attributes:
        instructions: 에이전트 시스템 지시사항.
        agent: ADK Agent 인스턴스.
        runner: AgentRunner 인스턴스.
    """

    def __init__(self, agent_name: str, description: str, instructions: str):
        init_api_key()

        super().__init__(
            agent_name=agent_name,
            description=description,
            content_types=['text', 'text/plain'],
        )

        logger.info(f'Init {self.agent_name}')

        self.instructions = instructions
        self.agent = None

    async def init_agent(self):
        """ADK 에이전트를 초기화합니다.

        MCP 서버에서 도구셋을 로드하고 LiteLLM 모델로
        에이전트를 구성합니다.
        """
        logger.info(f'Initializing {self.agent_name} metadata')
        config = get_mcp_server_config()
        logger.info(f'MCP Server url={config.url}')
        tools = await MCPToolset(
            connection_params=SseServerParams(url=config.url)
        ).get_tools()

        for tool in tools:
            logger.info(f'Loaded tools {tool.name}')
        generate_content_config = genai_types.GenerateContentConfig(
            temperature=0.0
        )
        LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini/gemini-2.0-flash')
        self.agent = Agent(
            name=self.agent_name,
            instruction=self.instructions,
            model=LiteLlm(model=LITELLM_MODEL),
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=generate_content_config,
            tools=tools,
        )
        self.runner = AgentRunner()

    async def invoke(self, query, session_id) -> dict:
        """에이전트를 동기적으로 호출합니다 (미지원).

        Args:
            query: 사용자 질문.
            session_id: 세션 ID.

        Raises:
            NotImplementedError: 스트리밍 함수 사용 필요.
        """
        logger.info(f'Running {self.agent_name} for session {session_id}')

        raise NotImplementedError('Please use the streraming function')

    async def stream(
        self, query, context_id, task_id
    ) -> AsyncIterable[dict[str, Any]]:
        """에이전트를 스트리밍 모드로 실행합니다.

        Args:
            query: 사용자 질문.
            context_id: 컨텍스트 ID.
            task_id: 태스크 ID.

        Yields:
            dict: 중간 처리 상태 또는 최종 응답.

        Raises:
            ValueError: 쿼리가 비어있는 경우.
        """
        logger.info(
            f'Running {self.agent_name} stream for session {context_id} {task_id} - {query}'
        )

        if not query:
            raise ValueError('Query cannot be empty')

        if not self.agent:
            await self.init_agent()
        async for chunk in self.runner.run_stream(
            self.agent, query, context_id
        ):
            logger.info(f'Received chunk {chunk}')
            if isinstance(chunk, dict) and chunk.get('type') == 'final_result':
                response = chunk['response']
                yield self.get_agent_response(response)
            else:
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': f'{self.agent_name}: Processing Request...',
                }

    def format_response(self, chunk):
        """응답에서 JSON 콘텐츠를 추출합니다.

        코드 블록 내의 JSON을 파싱하여 구조화된 데이터로 변환합니다.

        Args:
            chunk: 원본 응답 문자열.

        Returns:
            dict 또는 str: 파싱된 JSON 또는 원본 문자열.
        """
        patterns = [
            r'```\n(.*?)\n```',
            r'```json\s*(.*?)\s*```',
            r'```tool_outputs\s*(.*?)\s*```',
        ]

        for pattern in patterns:
            match = re.search(pattern, chunk, re.DOTALL)
            if match:
                content = match.group(1)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content
        return chunk

    def get_agent_response(self, chunk):
        """에이전트 응답을 A2A 형식으로 변환합니다.

        응답을 파싱하고 태스크 완료 상태와 사용자 입력 필요 여부를
        포함한 표준화된 응답 형식으로 변환합니다.

        Args:
            chunk: 에이전트 원본 응답.

        Returns:
            dict: A2A 형식 응답 (response_type, is_task_complete,
                  require_user_input, content).
        """
        logger.info(f'Response Type {type(chunk)}')
        data = self.format_response(chunk)
        logger.info(f'Formatted Response {data}')
        try:
            if isinstance(data, dict):
                if 'status' in data and data['status'] == 'input_required':
                    return {
                        'response_type': 'text',
                        'is_task_complete': False,
                        'require_user_input': True,
                        'content': data['question'],
                    }
                return {
                    'response_type': 'data',
                    'is_task_complete': True,
                    'require_user_input': False,
                    'content': data,
                }
            return_type = 'data'
            try:
                data = json.loads(data)
                return_type = 'data'
            except Exception as json_e:
                logger.error(f'Json conversion error {json_e}')
                return_type = 'text'
            return {
                'response_type': return_type,
                'is_task_complete': True,
                'require_user_input': False,
                'content': data,
            }
        except Exception as e:
            logger.error(f'Error in get_agent_response: {e}')
            return {
                'response_type': 'text',
                'is_task_complete': True,
                'require_user_input': False,
                'content': 'Could not complete booking / task. Please try again.',
            }
