"""
LangGraph State 실제 통합 테스트

실제 LangGraph의 BaseGraphState와 다양한 State 패턴에서
_get_graph_input_field_names()와 _build_graph_input_from_payload()가
올바르게 동작하는지 검증합니다.
"""
import os
import sys
import pytest

# tests가 repo 루트에서 실행될 때 src 패키지 경로를 포함하도록 설정
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.a2a_integration.a2a_lg_agent_executor import LangGraphWrappedA2AExecutor
from src.lg_agents.base.base_graph_state import BaseGraphState

try:
    from typing import TypedDict, Annotated
except ImportError:
    from typing_extensions import TypedDict, Annotated


def _make_executor_with_graph_state(state_schema):
    """실제 LangGraph StateGraph처럼 동작하는 더미 그래프 생성."""
    class DummyCompiledGraph:
        def __init__(self, schema):
            self.schema = schema

        def get_input_schema(self):
            return self.schema

        async def astream(self, input_data, config=None):
            # 더미 스트림 (실제로는 사용 안 함)
            yield {"messages": []}

    return LangGraphWrappedA2AExecutor(graph=DummyCompiledGraph(state_schema))


class TestBaseGraphStateIntegration:
    """BaseGraphState를 사용하는 실제 케이스 테스트"""

    def test_base_graph_state(self):
        """BaseGraphState를 상속한 State가 messages 필드를 인식."""
        from langchain_core.messages import BaseMessage

        class MyAgentState(BaseGraphState):
            additional_field: str

        ex = _make_executor_with_graph_state(MyAgentState)
        result = ex._get_graph_input_field_names()

        # BaseGraphState는 messages 필드를 가지고 있어야 함
        assert "messages" in result, f"Expected 'messages' in {result}"


class TestTypedDictStateWithAnnotated:
    """LangGraph에서 자주 사용되는 Annotated 필드 패턴"""

    def test_typedict_with_annotated_reducer(self):
        """Annotated를 사용한 리듀서 패턴이 정상 작동."""
        def add_messages(left, right):
            return left + right

        class StateWithReducer(TypedDict):
            messages: Annotated[list, add_messages]
            notes: Annotated[list[str], add_messages]

        ex = _make_executor_with_graph_state(StateWithReducer)
        result = ex._get_graph_input_field_names()

        assert result == {"messages", "notes"}, f"Expected {{'messages', 'notes'}}, got {result}"


class TestBuildGraphInputIntegration:
    """_build_graph_input_from_payload() 통합 테스트"""

    def test_build_input_with_typedict_state(self):
        """TypedDict State에 맞춰 payload를 변환."""
        class SimpleTDState(TypedDict):
            messages: list
            user_id: str

        ex = _make_executor_with_graph_state(SimpleTDState)

        # 스키마 필드명 추출 확인
        fields = ex._get_graph_input_field_names()
        assert fields == {"messages", "user_id"}

        # payload를 그래프 입력으로 변환
        payload = {"user_id": "test_user", "extra_field": "extra_value"}
        graph_input = ex._build_graph_input_from_payload(payload, query="Hello")

        # user_id가 포함되고, messages가 HumanMessage로 생성됨
        assert "user_id" in graph_input
        assert graph_input["user_id"] == "test_user"
        assert "messages" in graph_input
        assert len(graph_input["messages"]) == 1

        # extra_field도 보존됨 (스키마 외 키)
        assert "extra_field" in graph_input


    def test_build_input_with_existing_messages(self):
        """payload에 이미 messages가 있는 경우 LangChain 메시지로 변환."""
        class StateWithMessages(TypedDict):
            messages: list

        ex = _make_executor_with_graph_state(StateWithMessages)

        # OpenAI 포맷의 메시지 리스트
        payload = {
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"}
            ]
        }

        graph_input = ex._build_graph_input_from_payload(payload, query=None)

        # messages가 LangChain Message 객체로 변환되었는지 확인
        assert "messages" in graph_input
        messages = graph_input["messages"]
        assert len(messages) == 2

        # LangChain 메시지 타입 확인
        from langchain_core.messages import BaseMessage
        assert all(isinstance(msg, BaseMessage) for msg in messages)


class TestLookupMessagesField:
    """_looks_like_messages_field() 메서드 테스트"""

    def test_looks_like_messages_field(self):
        """messages 관련 필드명을 올바르게 감지."""
        class DummyGraph:
            def get_input_schema(self):
                return None

        ex = LangGraphWrappedA2AExecutor(graph=DummyGraph())

        assert ex._looks_like_messages_field("messages") is True
        assert ex._looks_like_messages_field("Messages") is True
        assert ex._looks_like_messages_field("chat_messages") is True
        assert ex._looks_like_messages_field("user_id") is False
        assert ex._looks_like_messages_field("notes") is False


class TestRealWorldAgentState:
    """실제 프로젝트에서 사용되는 AgentState 패턴 테스트"""

    def test_deep_research_agent_state_pattern(self):
        """Deep Research Agent의 State 구조를 시뮬레이션."""
        from typing import Optional

        def override_reducer(left, right):
            return right if right is not None else left

        class DeepResearchState(TypedDict):
            messages: Annotated[list, override_reducer]
            supervisor_messages: Annotated[list, override_reducer]
            research_brief: Optional[str]
            raw_notes: Annotated[list[str], override_reducer]
            notes: Annotated[list[str], override_reducer]
            final_report: str

        ex = _make_executor_with_graph_state(DeepResearchState)
        result = ex._get_graph_input_field_names()

        expected = {
            "messages", "supervisor_messages", "research_brief",
            "raw_notes", "notes", "final_report"
        }
        assert result == expected, f"Expected {expected}, got {result}"


if __name__ == "__main__":
    # 개별 실행 시 pytest 호출
    pytest.main([__file__, "-v"])
