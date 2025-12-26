"""MCP 도구 기반 서버 에이전트 모듈.

이 모듈은 MCP 도구를 사용하여 질문에 답변하는 서버 에이전트를
구현합니다.

주요 기능:
    - MCP 도구 프롬프트 조회
    - LLM 기반 도구 선택 결정
    - 도구 호출 및 결과 처리
    - 반복적 도구 호출을 통한 질의응답

아키텍처:
    - Jinja2 템플릿으로 LLM 프롬프트 생성
    - MCP 클라이언트로 외부 도구 호출
    - Google Gemini LLM으로 도구 선택 및 응답 생성
"""
import asyncio
import json
import re

from collections.abc import AsyncGenerator, Callable, Generator
from pathlib import Path
from typing import Literal

from google import genai
from jinja2 import Template
from mcp.types import CallToolResult

from no_llm_framework.server.constant import GOOGLE_API_KEY
from no_llm_framework.server.mcp import call_mcp_tool, get_mcp_tool_prompt


# --- Jinja2 템플릿 로드 ---
dir_path = Path(__file__).parent

with Path(dir_path / 'decide.jinja').open('r') as f:
    decide_template = Template(f.read())

with Path(dir_path / 'tool.jinja').open('r') as f:
    tool_template = Template(f.read())

with Path(dir_path / 'called_tools_history.jinja').open('r') as f:
    called_tools_history_template = Template(f.read())


def stream_llm(prompt: str) -> Generator[str, None]:
    """LLM 응답을 스트리밍합니다.

    Args:
        prompt: LLM에 보낼 프롬프트.

    Yields:
        str: LLM 응답 청크.
    """
    client = genai.Client(vertexai=False, api_key=GOOGLE_API_KEY)
    for chunk in client.models.generate_content_stream(
        model='gemini-2.5-flash-lite',
        contents=prompt,
    ):
        yield chunk.text


class Agent:
    """MCP 도구를 사용하여 질문에 답변하는 서버 에이전트.

    LLM을 사용해 어떤 도구를 호출할지 결정하고,
    MCP 프로토콜로 도구를 실행한 후 결과를 기반으로 답변합니다.

    Attributes:
        mode: 실행 모드 ('complete' 또는 'stream').
        token_stream_callback: 토큰 스트리밍 콜백 함수.
        mcp_url: MCP 서버 URL.
    """

    def __init__(
        self,
        mode: Literal['complete', 'stream'] = 'stream',
        token_stream_callback: Callable[[str], None] | None = None,
        mcp_url: str | None = None,
    ):
        self.mode = mode
        self.token_stream_callback = token_stream_callback
        self.mcp_url = mcp_url

    def call_llm(self, prompt: str) -> Generator[str, None]:
        """LLM을 호출하고 응답 제너레이터를 반환합니다.

        Args:
            prompt: LLM에 보낼 프롬프트.

        Returns:
            Generator[str, None]: LLM 응답을 생성하는 제너레이터.
        """
        return stream_llm(prompt)

    async def decide(
        self, question: str, called_tools: list[dict] | None = None
    ) -> Generator[str, None]:
        """질문에 답하기 위해 사용할 도구를 결정합니다.

        Args:
            question: 답변할 질문.
            called_tools: 이미 호출된 도구 목록.

        Returns:
            Generator[str, None]: LLM 응답의 제너레이터.
        """
        if self.mcp_url is None:
            return self.call_llm(question)
        tool_prompt = await get_mcp_tool_prompt(self.mcp_url)
        if called_tools:
            called_tools_prompt = called_tools_history_template.render(
                called_tools=called_tools
            )
        else:
            called_tools_prompt = ''

        prompt = decide_template.render(
            question=question,
            tool_prompt=tool_prompt,
            called_tools=called_tools_prompt,
        )
        return self.call_llm(prompt)

    def extract_tools(self, response: str) -> list[dict]:
        """LLM 응답에서 도구 호출 정보를 추출합니다.

        Args:
            response: LLM 응답 문자열.

        Returns:
            list[dict]: 추출된 도구 호출 정보 목록.
        """
        pattern = r'```json\n(.*?)\n```'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return []

    async def call_tool(self, tools: list[dict]) -> list[CallToolResult]:
        """MCP 도구를 호출합니다.

        Args:
            tools: 호출할 도구 정보 목록.

        Returns:
            list[CallToolResult]: 도구 호출 결과 목록.
        """
        return await asyncio.gather(
            *[
                call_mcp_tool(self.mcp_url, tool['name'], tool['arguments'])
                for tool in tools
            ]
        )

    async def stream(self, question: str) -> AsyncGenerator[str]:
        """질문 답변 과정을 스트리밍합니다 (도구 호출 포함 가능).

        Args:
            question: 답변할 질문.

        Yields:
            dict: 중간 단계와 최종 결과를 포함한 스트리밍 출력.
        """
        called_tools = []
        for i in range(10):
            yield {
                'is_task_complete': False,
                'require_user_input': False,
                'content': f'Step {i}',
            }

            response = ''
            for chunk in await self.decide(question, called_tools):
                response += chunk
                yield {
                    'is_task_complete': False,
                    'require_user_input': False,
                    'content': chunk,
                }
            tools = self.extract_tools(response)
            if not tools:
                break
            results = await self.call_tool(tools)

            called_tools += [
                {
                    'tool': tool['name'],
                    'arguments': tool['arguments'],
                    'isError': result.isError,
                    'result': result.content[0].text,
                }
                for tool, result in zip(tools, results, strict=True)
            ]
            called_tools_history = called_tools_history_template.render(
                called_tools=called_tools, question=question
            )
            yield {
                'is_task_complete': False,
                'require_user_input': False,
                'content': called_tools_history,
            }

        yield {
            'is_task_complete': True,
            'require_user_input': False,
            'content': 'Task completed',
        }


if __name__ == '__main__':
    agent = Agent(
        token_stream_callback=lambda token: print(token, end='', flush=True),
        mcp_url='https://gitmcp.io/google/A2A',
    )

    async def main():
        """서버 에이전트 테스트를 위한 메인 함수."""
        async for chunk in agent.stream('What is A2A Protocol?'):
            print(chunk)

    asyncio.run(main())
