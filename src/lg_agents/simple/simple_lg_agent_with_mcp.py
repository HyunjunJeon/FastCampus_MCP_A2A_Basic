"""
Step 1-2: MCP 도구를 사용하는 LangGraph 에이전트 (BaseGraphAgent 기반)

단일 노드로 `create_react_agent`를 사용하여 MCP 도구(search_web 등)를 호출하는
아주 간단한 ReAct 패턴 LangGraph 에이전트 구현.
"""

from __future__ import annotations
from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.store.base import BaseStore

from src.utils.logging_config import get_logger
from src.lg_agents.base.base_graph_agent import BaseGraphAgent


logger = get_logger(__name__)


class SimpleLangGraphWithMCPAgent(BaseGraphAgent):
    """
    MCP(Model Context Protocol) 도구를 사용하는 ReAct 에이전트.
    """

    NODE_NAMES: ClassVar[dict[str, str]] = {"REACT": "react_agent"}

    def __init__(
        self,
        model: BaseChatModel | None = None,
        state_schema: type | None = None,
        config_schema: type | None = None,
        input_state: type | None = None,
        output_state: type | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None = None,
        max_retry_attempts: int = 2,
        agent_name: str | None = None,
        is_debug: bool = True,
    ) -> None:
        super().__init__(
            model=model,
            state_schema=state_schema,
            config_schema=config_schema,
            input_state=input_state,
            output_state=output_state,
            checkpointer=checkpointer,
            store=store,
            max_retry_attempts=max_retry_attempts,
            agent_name=agent_name,
            is_debug=is_debug,
            auto_build=False, # NOTE: Key point!
        )

        self.llm = model
        self.mcp_server_url = "http://localhost:3001/mcp/"
        self.mcp_server_config = {"transport": "streamable_http"}
        self.mcp_client = MultiServerMCPClient(
            {"tavily-search": {"url": self.mcp_server_url, **self.mcp_server_config}}
        )
        self.tools = []

    @classmethod
    async def create(
        cls,
        model: BaseChatModel | None = None,
        state_schema: type | None = None,
        config_schema: type | None = None,
        input_state: type | None = None,
        output_state: type | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        store: BaseStore | None = None,
        max_retry_attempts: int = 2,
        agent_name: str | None = None,
        is_debug: bool = True,
    ) -> "SimpleLangGraphWithMCPAgent":
        """
        비동기 초기화 팩토리. 
        MCP 도구를 await로 로딩한 뒤 그래프를 빌드한다.
        """
        self = cls(
            model=model,
            state_schema=state_schema,
            config_schema=config_schema,
            input_state=input_state,
            output_state=output_state,
            checkpointer=checkpointer,
            store=store,
            max_retry_attempts=max_retry_attempts,
            agent_name=agent_name,
            is_debug=is_debug,
        )
        self.tools = await self.mcp_client.get_tools() # NOTE: Key point!
        self.build_graph() # NOTE: 여기서는 자식 그래프에서 호출함.
        return self

    def init_nodes(self, graph: StateGraph) -> None:
        graph.add_node(self.get_node_name("REACT"), create_react_agent(
            model=self.llm,
            tools=self.tools or [],
            prompt="""
                당신은 웹 도구를 가지고 있는 검색 전문가입니다. 
                필요 시 가진 도구를 사용해 답변하세요.
                - search_web(query): 일반 웹 검색
                - search_news(query, time_range='week'): 뉴스 검색
                결과가 부족하면 모른다고 답하면 되고 도구의 결과를 활용하여 출처를 꼭 제공하세요.
                """,
            ),
        )

    def init_edges(self, graph: StateGraph) -> None:
        graph.set_entry_point(self.get_node_name("REACT"))
        graph.set_finish_point(self.get_node_name("REACT"))
