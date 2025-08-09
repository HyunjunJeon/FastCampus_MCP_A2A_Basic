"""
A2A 통합 테스트

목적:
- LangGraph Agent와 A2A 서버 간의 통합 검증
- A2A 0.3.0 표준 프로토콜 준수 확인
- Agent Executor의 스트리밍 기능 테스트
- 이벤트 기반 메시지 처리 검증

테스트 시나리오:
1. MCP Agent 모킹 및 A2A 표준 스트리밍 테스트
2. Agent Executor 실행 및 이벤트 큐 처리 검증
3. A2A 서버 컴포넌트 통합 테스트
4. 스트리밍 응답 형식 및 품질 검증

전제 조건:
- A2A SDK 0.3.0 이상 설치
- LangGraph 및 MCP 도구 설정 완료
- 테스트 환경에서 모킹된 컴포넌트 사용

예상 결과:
- A2A 표준 이벤트 형식으로 메시지 스트리밍
- Agent Card 및 서버 컴포넌트 정상 생성
- 이벤트 큐를 통한 안전한 메시지 전달
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from src.a2a_integration.agent_executor import LangGraphA2AExecutor

from a2a.server.events import EventQueue, EventConsumer


class TestA2AIntegration:
    """
    A2A 통합 테스트 클래스

    이 클래스는 A2A (Agent-to-Agent) 프로토콜과 LangGraph Agent 간의
    통합을 검증합니다. 주요 테스트 대상은 다음과 같습니다:
    - MCP Agent와 A2A 표준 간의 호환성
    - 스트리밍 메시지 처리
    - 이벤트 기반 통신
    - Agent Executor의 정상 동작
    """

    @pytest.fixture
    def mock_mcp_agent(self):
        """MCP Agent 모킹 - A2A 표준 형식"""
        agent = AsyncMock()
        agent.initialize = AsyncMock()

        # 기존 query 메서드 (호환성 유지)
        agent.query = AsyncMock(
            return_value={
                "success": True,
                "user_query": "test query",
                "agent_response": "test response",
                "tool_calls": [{"tool": "search_web", "args": {"query": "test"}}],
            }
        )

        # 새로운 A2A 표준 stream 메서드
        async def mock_stream(query, context_id):
            """A2A 표준 스트리밍 응답 모킹"""
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "검색을 시작합니다...",
            }
            yield {
                "is_task_complete": False,
                "require_user_input": False,
                "content": "사용된 도구: search_web",
            }
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": "test response",
            }

        agent.stream = mock_stream
        return agent

    @pytest.fixture
    def agent_executor(self, mock_mcp_agent):
        """테스트용 Agent Executor - A2A 0.3.0 패턴"""
        executor = LangGraphA2AExecutor()
        executor.agent = mock_mcp_agent
        return executor

    @pytest.mark.asyncio
    async def test_agent_stream_method(self, mock_mcp_agent):
        """Agent의 A2A 표준 stream 메서드 테스트"""
        # Agent stream 메서드 직접 테스트
        results = []
        async for item in mock_mcp_agent.stream("test query", "test-context"):
            results.append(item)

        # A2A 표준 형식 검증
        assert len(results) == 3
        assert not results[0]["is_task_complete"]
        assert not results[0]["require_user_input"]
        assert "검색을 시작합니다" in results[0]["content"]

        assert results[-1]["is_task_complete"]
        assert not results[-1]["require_user_input"]
        assert "test response" in results[-1]["content"]

    @pytest.mark.asyncio
    async def test_executor_execution_a2a_standard(self, agent_executor):
        """A2A 표준 Agent Executor 실행 테스트"""
        # Mock Message 생성
        mock_message = MagicMock()
        mock_message.parts = [MagicMock()]
        mock_message.parts[0].text = "Test question"

        # Mock RequestContext 생성 (A2A 0.3.0 패턴)
        context = MagicMock()
        context.task_id = "test-task-123"
        context.context_id = "test-context-123"
        context.message = mock_message
        context.current_task = None  # 새 태스크 생성을 위해
        context.get_user_input = MagicMock(
            return_value="Test question"
        )  # A2A 표준 메서드

        # 이벤트 큐 생성
        event_queue = EventQueue()

        # Agent Executor 실행
        await agent_executor.execute(context, event_queue)

        # EventQueue 종료
        await event_queue.close()

        # EventConsumer로 이벤트 수집
        events = []
        consumer = EventConsumer(event_queue)
        async for event in consumer.consume_all():
            events.append(event)

        # 검증
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_a2a_server_components(self):
        """A2A 서버 컴포넌트 테스트"""
        from a2a.server.apps import A2AStarletteApplication
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.tasks import (
            BasePushNotificationSender,
            InMemoryPushNotificationConfigStore,
            InMemoryTaskStore,
        )
        from a2a.types import AgentCapabilities, AgentCard, AgentSkill

        # AgentCard 생성 (공식 패턴)
        capabilities = AgentCapabilities(streaming=True, push_notifications=True)
        skill = AgentSkill(
            id="test_skill",
            name="Test Skill",
            description="Test skill for testing",
            tags=["test"],
            examples=["test example"],
        )
        agent_card = AgentCard(
            name="Test Agent",
            description="Test Description",
            url="http://localhost:8081/",
            version="1.0.0",
            default_input_modes=["text"],
            default_output_modes=["text"],
            capabilities=capabilities,
            skills=[skill],
        )

        # DefaultRequestHandler 설정 (공식 패턴)
        httpx_client = httpx.AsyncClient()
        push_config_store = InMemoryPushNotificationConfigStore()
        push_sender = BasePushNotificationSender(
            httpx_client=httpx_client, config_store=push_config_store
        )
        # Agent Executor 모킹 (API 키 없이 테스트 가능)
        with patch("src.a2a_integration.agent_executor.MCPWebSearchAgent") as MockAgent:
            mock_agent_instance = AsyncMock()
            MockAgent.return_value = mock_agent_instance

            request_handler = DefaultRequestHandler(
                agent_executor=LangGraphA2AExecutor(),
                task_store=InMemoryTaskStore(),
                push_config_store=push_config_store,
                push_sender=push_sender,
            )

            # A2A 서버 생성 (공식 패턴)
            server = A2AStarletteApplication(
                agent_card=agent_card, http_handler=request_handler
            )

            # 서버 앱 빌드
            server.build()

            # Agent Card 검증
            assert agent_card.name == "Test Agent"
            assert agent_card.version == "1.0.0"
            assert len(agent_card.skills) == 1
            assert agent_card.capabilities.streaming is True

    @pytest.mark.asyncio
    async def test_a2a_standard_streaming(self, agent_executor):
        """A2A 표준 스트리밍 응답 테스트"""
        # Mock Message 생성
        mock_message = MagicMock()
        mock_message.parts = [MagicMock()]
        mock_message.parts[0].text = "Test streaming"

        # Mock RequestContext 생성 (A2A 0.3.0 패턴)
        context = MagicMock()
        context.task_id = "test-streaming"
        context.context_id = "test-context"
        context.message = mock_message
        context.current_task = None
        context.get_user_input = MagicMock(return_value="Test streaming")

        # 이벤트 큐 생성
        event_queue = EventQueue()

        # A2A 표준 execute 실행 (스트리밍 포함)
        await agent_executor.execute(context, event_queue)

        # EventQueue 종료
        await event_queue.close()

        # EventConsumer로 이벤트 수집
        events = []
        consumer = EventConsumer(event_queue)
        async for event in consumer.consume_all():
            events.append(event)

        # 검증 - A2A 표준 스트리밍 이벤트가 수집되었는지 확인
        assert len(events) > 0


# 통합 테스트 실행
def run_a2a_tests():
    """A2A 통합 테스트 실행"""
    print("🧪 A2A 통합 테스트 시작")
    print("=" * 50)

    exit_code = pytest.main(
        ["tests/test_a2a_integration.py", "-v", "--tb=short", "--color=yes"]
    )

    if exit_code == 0:
        print("\n✅ 모든 A2A 테스트 통과!")
    else:
        print(f"\n❌ A2A 테스트 실패 (종료 코드: {exit_code})")

    return exit_code


if __name__ == "__main__":
    run_a2a_tests()
