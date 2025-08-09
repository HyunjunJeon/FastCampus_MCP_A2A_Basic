"""
새로운 LangGraph 에이전트를 만들기 위한 템플릿 - Copy 후 사용
"""

from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.store.base import BaseStore
from src.utils.logging_config import get_logger
from src.lg_agents.base.base_graph_agent import BaseGraphAgent
from src.lg_agents.base.base_graph_state import BaseGraphState

logger = get_logger(__name__)

class NewAgentTemplate(BaseGraphAgent): 
    NODE_NAMES: ClassVar[dict[str, str]] = {
        "DEFAULT": "new_node_function",
    }

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
    ):
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
        )

    def init_nodes(self, graph: StateGraph):
        graph.add_node(self.get_node_name("DEFAULT"), self.new_node_function)

    def init_edges(self, graph: StateGraph):
        graph.set_entry_point(self.get_node_name("DEFAULT"))
        graph.set_finish_point(self.get_node_name("DEFAULT"))   

    async def new_node_function(self, state: BaseGraphState, config: RunnableConfig):
        """새로운 노드 함수 정의(Async)"""
        try:
            pass
        except Exception as e:
            raise Exception(f"{self.__class__.__name__}: Error during LLM execution: {e!s}") from e

    def new_conditional_edge(self, state: BaseGraphState):
        """새로운 조건부 Edge 정의"""
        pass
