"""날씨 에이전트 정의 모듈.

이 모듈은 Google ADK LlmAgent를 사용하여 날씨 정보를 제공하는
에이전트를 정의합니다.

주요 특징:
    - LiteLLM 모델 사용 (기본: gemini-2.5-flash)
    - MCP 도구를 통한 NWS API 연동
    - Markdown 형식 응답

Note:
    instruction은 영문으로 유지됩니다 (LLM 지시사항).
"""
import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioServerParameters,
)


def create_weather_agent() -> LlmAgent:
    """ADK 날씨 에이전트를 생성합니다.

    Returns:
        LlmAgent: 날씨 정보 제공 에이전트.
    """
    LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini-2.5-flash')
    return LlmAgent(
        model=LiteLlm(model=LITELLM_MODEL),
        name='weather_agent',
        description='An agent that can help questions about weather',
        instruction="""You are a specialized weather forecast assistant. Your primary function is to utilize the provided tools to retrieve and relay weather information in response to user queries. You must rely exclusively on these tools for data and refrain from inventing information. Ensure that all responses include the detailed output from the tools used and are formatted in Markdown""",
        tools=[
            MCPToolset(
                connection_params=StdioServerParameters(
                    command='python',
                    args=['./weather_mcp.py'],
                ),
            )
        ],
    )
