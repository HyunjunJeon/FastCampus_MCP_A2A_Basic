from typing import ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import RetryPolicy


class BaseGraphAgent:
    """
    LangGraph의 그래프 에이전트를 위한 기본 클래스.
    Sub-Graph와 Main-Graph를 객체지향적으로 구성할 수 있도록 공통 기능을 제공합니다.
    """

    # 노드 이름을 클래스 속성으로 정의하여 문자열 오타를 방지
    NODE_NAMES: ClassVar[dict[str, str]] = {}

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
        auto_build: bool = True,
    ) -> None:
        """
        베이스 그래프 에이전트 초기화.

        Args:
            model: 사용할 LLM 모델
            state_schema: 상태 스키마 타입
            config_schema: 설정 스키마 타입
            input_state: 입력 상태 타입
            output_state: 출력 상태 타입
            checkpointer: 체크포인터 객체
            store: 저장소 객체
            max_retry_attempts: 최대 재시도 횟수
            agent_name: 에이전트 이름
            is_debug: 디버그 여부

        """
        self.model = model
        self.checkpointer = checkpointer
        self.store = store
        self.state_schema = state_schema
        self.config_schema = config_schema
        self.input_state = input_state
        self.output_state = output_state
        self.max_retry_attempts = max_retry_attempts
        _retry_policy = RetryPolicy(
            max_attempts=self.max_retry_attempts,
        ) if self.max_retry_attempts > 0 else None
        self.retry_policy = _retry_policy
        self.agent_name = agent_name
        self.is_debug = is_debug
        # 그래프 자동 빌드 여부 (비동기 초기화가 필요한 서브클래스에서 지연 빌드 용도)
        if auto_build:
            self.build_graph()

    def get_node_name(self, key="DEFAULT"):
        """
        노드 이름을 가져오는 메소드.

        Args:
            key: 노드 이름 키

        Returns:
            해당 키에 대한 노드 이름

        """
        if key not in self.NODE_NAMES:
            raise ValueError(f"노드 이름 키 '{key}'가 정의되어 있지 않습니다.")
        return self.NODE_NAMES.get(key)

    def build_graph(self):
        """그래프를 구축하는 메소드."""
        _graph = StateGraph(
            state_schema=self.state_schema,
            config_schema=self.config_schema,
            input_schema=self.input_state,
            output_schema=self.output_state,
        )

        self.init_nodes(_graph)
        self.init_edges(_graph)

        self.graph = _graph.compile(
            checkpointer=self.checkpointer,
            store=self.store,
            name=f"{self.agent_name or self.__class__.__name__}",
            debug=self.is_debug,
        )

    def init_nodes(self, graph: StateGraph):
        """
        그래프의 노드를 초기화하는 메소드.

        Args:
            graph: 초기화할 StateGraph 객체

        """
        raise NotImplementedError("Subclasses must implement init_nodes method")

    def init_edges(self, graph: StateGraph):
        """
        그래프의 엣지를 초기화하는 메소드.

        Args:
            graph: 초기화할 StateGraph 객체

        """
        raise NotImplementedError("Subclasses must implement init_edges method")