"""MCP 클라이언트 유틸리티 모듈.

이 모듈은 MCP(Model Context Protocol) 서버와 통신하기 위한
헬퍼 함수들을 제공합니다.

주요 기능:
    - MCP 도구 프롬프트 조회
    - MCP 도구 호출

MCP 서버 연결:
    SSE(Server-Sent Events) 프로토콜을 사용하여 MCP 서버와 통신합니다.
"""
import asyncio

from pathlib import Path

from jinja2 import Template
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.types import CallToolResult, TextContent

# --- Jinja2 템플릿 로드 ---
dir_path = Path(__file__).parent

with Path(dir_path / 'tool.jinja').open('r') as f:
    template = Template(f.read())


async def get_mcp_tool_prompt(url: str) -> str:
    """주어진 URL의 MCP 도구 프롬프트를 조회합니다.

    MCP 서버에 연결하여 사용 가능한 도구 목록을 가져오고,
    Jinja2 템플릿으로 프롬프트를 렌더링합니다.

    Args:
        url: MCP 서버 URL.

    Returns:
        str: 렌더링된 MCP 도구 프롬프트.
    """
    async with (
        sse_client(url) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        resources = await session.list_tools()
        return template.render(tools=resources.tools)


async def call_mcp_tool(
    url: str, tool_name: str, arguments: dict | None = None
) -> CallToolResult:
    """MCP 도구를 호출합니다.

    MCP 서버에 연결하여 지정된 도구를 실행하고 결과를 반환합니다.

    Args:
        url: MCP 서버 URL.
        tool_name: 호출할 도구 이름.
        arguments: 도구에 전달할 인자. 기본값은 None.

    Returns:
        CallToolResult: 도구 호출 결과.
    """
    async with (
        sse_client(
            url=url,
        ) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        return await session.call_tool(tool_name, arguments=arguments)


if __name__ == '__main__':
    print(asyncio.run(get_mcp_tool_prompt('https://gitmcp.io/google/A2A')))
    result = asyncio.run(
        call_mcp_tool('https://gitmcp.io/google/A2A', 'fetch_A2A_documentation')
    )
    for content in result.content:
        if isinstance(content, TextContent):
            print(content.text)
