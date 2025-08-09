# ruff: noqa: E402
"""
MCP + LangGraph 통합 테스트

이 모듈은 MCP와 LangGraph의 통합 기능을 pytest 프레임워크로 테스트합니다.

실행 방법:
    # 전체 테스트 실행
    pytest tests/integration_test.py -v
    
    # 특정 테스트만 실행
    pytest tests/integration_test.py::TestMCPIntegration::test_mcp_server_health_check -v
    
    # Python으로 직접 실행
    python tests/integration_test.py

전제 조건:
    - MCP 서버가 localhost:3000에서 실행 중
    - Docker Compose로 서비스 실행: docker-compose up -d
    - .env 파일에 OPENAI_API_KEY 설정
    
테스트 범위:
    1. MCP 서버 헬스체크
    2. MCP 클라이언트 연결 테스트
    3. 검색 도구 직접 실행 테스트
    4. Agent 초기화 테스트 (모킹)
    5. Agent 질의 처리 테스트 (모킹)
    6. Agent 도구 테스트 기능

모킹 전략:
    - OpenAI LLM 호출 모킹으로 비용 절약
    - create_react_agent 모킹으로 안정적 테스트
    - 실제 MCP 서버 연결은 그대로 유지

디버깅:
    - verbose 모드로 상세한 테스트 로그 출력
    - 실패 시 간략한 스택 트레이스
    - 서버 연결 실패 시 자동 스킵 처리
"""

import pytest
import os
import httpx
import sys
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, patch

# LangGraph deprecation warning 무시
warnings.filterwarnings(
    "ignore", message=".*config_type.*is deprecated.*", category=DeprecationWarning
)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lg_agents.retriever_agent import MCPWebSearchAgent
from langchain_mcp_adapters.client import MultiServerMCPClient


class TestMCPIntegration:
    """MCP 통합 테스트"""

    @pytest.fixture
    def mock_openai_key(self, monkeypatch):
        """OpenAI API 키 실제 키 사용"""
        from dotenv import load_dotenv

        load_dotenv()
        monkeypatch.setenv("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))

    @pytest.mark.asyncio
    async def test_mcp_server_health_check(self):
        """MCP 서버 헬스체크 테스트"""
        try:
            async with httpx.AsyncClient() as client:
                # FastMCP custom_route로 추가된 헬스체크 엔드포인트 사용
                response = await client.get("http://localhost:3000/health", timeout=5.0)
                assert response.status_code == 200, (
                    f"MCP 서버가 응답하지 않습니다. 상태 코드: {response.status_code}"
                )

                # 응답 내용 확인
                data = response.json()
                assert data["status"] == "healthy", "서버 상태가 healthy가 아닙니다"
                assert data["service"] == "MCP Tavily Web Search", (
                    "서비스 이름이 올바르지 않습니다"
                )
                assert "tools_available" in data, "도구 목록이 없습니다"
        except httpx.ConnectError:
            pytest.skip(
                "MCP 서버가 실행되지 않았습니다. docker-compose up -d로 서버를 시작하세요."
            )

    @pytest.mark.asyncio
    async def test_mcp_client_connection(self):
        """MCP 클라이언트 연결 테스트"""
        client = MultiServerMCPClient(
            {
                "test_server": {
                    "transport": "streamable_http",
                    "url": "http://localhost:3000/mcp/",
                }
            }
        )

        try:
            # 도구 목록 가져오기 테스트
            tools = await client.get_tools(server_name="test_server")
            assert len(tools) > 0, "MCP 서버에서 도구를 로드할 수 없습니다"

            # search_web 도구 확인
            tool_names = [tool.name for tool in tools]
            assert "search_web" in tool_names, "search_web 도구가 없습니다"

        except Exception as e:
            pytest.fail(f"MCP 클라이언트 연결 실패: {e}")

    @pytest.mark.asyncio
    async def test_search_tool_execution(self):
        """검색 도구 직접 실행 테스트"""
        client = MultiServerMCPClient(
            {
                "test_server": {
                    "transport": "streamable_http",
                    "url": "http://localhost:3000/mcp/",
                }
            }
        )

        try:
            tools = await client.get_tools(server_name="test_server")
            search_tool = next(
                (tool for tool in tools if tool.name == "search_web"), None
            )
            assert search_tool is not None, "search_web 도구를 찾을 수 없습니다"

            # 도구 실행
            result = await search_tool.ainvoke({"query": "Python 3.12 new features"})
            assert result is not None, "검색 결과가 None입니다"

            # 결과가 JSON 문자열인 경우 파싱
            if isinstance(result, str):
                import json

                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    pass

            assert isinstance(result, (list, dict)), (
                f"검색 결과 형식이 올바르지 않습니다. 타입: {type(result)}, 값: {result}"
            )

        except Exception as e:
            pytest.fail(f"검색 도구 실행 실패: {e}")

    @pytest.mark.asyncio
    @patch("langchain_openai.ChatOpenAI")
    async def test_agent_initialization(self, mock_llm, mock_openai_key):
        """Agent 초기화 테스트"""
        # LLM 모킹
        mock_llm_instance = AsyncMock()
        mock_llm.return_value = mock_llm_instance

        try:
            agent = MCPWebSearchAgent()
            await agent.initialize()

            assert agent.tools is not None, "도구가 로드되지 않았습니다"
            assert len(agent.tools) > 0, "도구 목록이 비어있습니다"
            assert agent.agent is not None, "Agent가 생성되지 않았습니다"

        except Exception as e:
            if "MCP 서버" in str(e) or "연결" in str(e):
                pytest.skip("MCP 서버 연결 실패. 서버가 실행 중인지 확인하세요.")
            else:
                pytest.fail(f"Agent 초기화 실패: {e}")

    @pytest.mark.asyncio
    @patch("langchain_openai.ChatOpenAI")
    async def test_agent_query_handling(self, mock_llm, mock_openai_key):
        """Agent 질의 처리 테스트"""
        # LLM 응답 모킹
        mock_llm_instance = AsyncMock()
        mock_response = {
            "messages": [
                AsyncMock(
                    content="FastMCP는 Model Context Protocol을 쉽게 구현할 수 있는 라이브러리입니다."
                )
            ]
        }
        mock_llm_instance.bind_tools.return_value.ainvoke.return_value = mock_response
        mock_llm.return_value = mock_llm_instance

        # create_react_agent 모킹
        with patch(
            "src.lg_agents.retriever_agent.create_react_agent"
        ) as mock_create_agent:
            mock_agent = AsyncMock()
            mock_agent.ainvoke.return_value = mock_response
            mock_create_agent.return_value = mock_agent

            try:
                agent = MCPWebSearchAgent()
                await agent.initialize()

                result = await agent.query(
                    "Python 3.12의 새로운 기능에 대해 알려주세요"
                )

                assert result["success"], "질의 처리가 실패했습니다"
                assert (
                    result["user_query"]
                    == "Python 3.12의 새로운 기능에 대해 알려주세요"
                )
                assert len(result["agent_response"]) > 0, "응답이 비어있습니다"

            except Exception as e:
                if "MCP 서버" in str(e):
                    pytest.skip("MCP 서버 연결 실패")
                else:
                    pytest.fail(f"Agent 질의 처리 실패: {e}")

    @pytest.mark.asyncio
    async def test_agent_tool_testing(self):
        """Agent 도구 테스트 기능 테스트"""
        try:
            agent = MCPWebSearchAgent()
            await agent.initialize()

            # 도구 직접 테스트 (test_tools 메서드 대신)
            if not agent.tools:
                pytest.fail("도구가 로드되지 않았습니다")

            # search_web 도구 테스트
            search_tool = next(
                (tool for tool in agent.tools if tool.name == "search_web"), None
            )
            if search_tool:
                result = await search_tool.ainvoke(
                    {"query": "Python 3.12 new features"}
                )
                assert result is not None, "검색 결과가 None입니다"
            else:
                pytest.skip("search_web 도구를 찾을 수 없습니다")

        except Exception as e:
            if "MCP 서버" in str(e):
                pytest.skip("MCP 서버 연결 실패")
            else:
                pytest.fail(f"도구 테스트 실패: {e}")


# 테스트 실행을 위한 헬퍼 함수
def run_integration_tests():
    """통합 테스트 실행"""
    print("🧪 MCP + LangGraph 통합 테스트 시작")
    print("=" * 50)

    # pytest 실행
    exit_code = pytest.main(
        ["tests/integration_test.py", "-v", "--tb=short", "--color=yes"]
    )

    if exit_code == 0:
        print("\n✅ 모든 테스트 통과!")
    else:
        print(f"\n❌ 테스트 실패 (종료 코드: {exit_code})")

    return exit_code


if __name__ == "__main__":
    run_integration_tests()
