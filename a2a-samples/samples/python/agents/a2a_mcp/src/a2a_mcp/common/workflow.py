"""워크플로우 그래프 모듈.

이 모듈은 멀티에이전트 오케스트레이션을 위한 워크플로우 그래프를
구현합니다.

주요 기능:
    - NetworkX 기반 DAG 워크플로우 관리
    - MCP 리소스를 통한 에이전트 검색
    - A2A 클라이언트를 통한 에이전트 호출
    - 워크플로우 일시정지/재개 지원

아키텍처:
    - WorkflowNode: 개별 태스크 노드
    - WorkflowGraph: DAG 기반 워크플로우 관리자
"""
import json
import logging
import uuid

from collections.abc import AsyncIterable
from enum import Enum
from uuid import uuid4

import httpx
import networkx as nx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendStreamingMessageRequest,
    SendStreamingMessageSuccessResponse,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from a2a_mcp.common.utils import get_mcp_server_config
from a2a_mcp.mcp import client


logger = logging.getLogger(__name__)


class Status(Enum):
    """워크플로우 및 노드 상태.

    Attributes:
        READY: 실행 준비 완료.
        RUNNING: 실행 중.
        COMPLETED: 완료.
        PAUSED: 일시정지 (사용자 입력 대기).
        INITIALIZED: 초기화 완료.
    """

    READY = 'READY'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    PAUSED = 'PAUSED'
    INITIALIZED = 'INITIALIZED'


class WorkflowNode:
    """워크플로우 그래프의 단일 노드.

    각 노드는 에이전트 검색 또는 에이전트 기능 호출과 같은 특정 태스크를
    캡슐화합니다. 자체 상태(READY, RUNNING, COMPLETED, PAUSED)를 관리하고
    할당된 태스크를 실행할 수 있습니다.

    Attributes:
        id: 노드 고유 ID.
        node_key: 노드 키 (예: 'planner').
        node_label: 노드 레이블.
        task: 실행할 태스크 설명.
        results: 노드 실행 결과.
        state: 현재 노드 상태.
    """

    def __init__(
        self,
        task: str,
        node_key: str | None = None,
        node_label: str | None = None,
    ):
        self.id = str(uuid.uuid4())
        self.node_key = node_key
        self.node_label = node_label
        self.task = task
        self.results = None
        self.state = Status.READY

    async def get_planner_resource(self) -> AgentCard | None:
        """MCP 리소스에서 플래너 에이전트 카드를 조회합니다.

        Returns:
            AgentCard: 플래너 에이전트 카드.
        """
        logger.info(f'Getting resource for node {self.id}')
        config = get_mcp_server_config()
        async with client.init_session(
            config.host, config.port, config.transport
        ) as session:
            response = await client.find_resource(
                session, 'resource://agent_cards/planner_agent'
            )
            data = json.loads(response.contents[0].text)
            return AgentCard(**data['agent_card'][0])

    async def find_agent_for_task(self) -> AgentCard | None:
        """태스크에 적합한 에이전트를 MCP에서 검색합니다.

        Returns:
            AgentCard: 검색된 에이전트 카드.
        """
        logger.info(f'Find agent for task - {self.task}')
        config = get_mcp_server_config()
        async with client.init_session(
            config.host, config.port, config.transport
        ) as session:
            result = await client.find_agent(session, self.task)
            agent_card_json = json.loads(result.content[0].text)
            logger.debug(f'Found agent {agent_card_json} for task {self.task}')
            return AgentCard(**agent_card_json)

    async def run_node(
        self,
        query: str,
        task_id: str,
        context_id: str,
    ) -> AsyncIterable[dict[str, any]]:
        """노드를 실행하고 결과를 스트리밍합니다.

        Args:
            query: 실행할 쿼리.
            task_id: 태스크 ID.
            context_id: 컨텍스트 ID.

        Yields:
            A2A 스트리밍 응답.
        """
        logger.info(f'Executing node {self.id}')
        agent_card = None
        if self.node_key == 'planner':
            agent_card = await self.get_planner_resource()
        else:
            agent_card = await self.find_agent_for_task()
        async with httpx.AsyncClient() as httpx_client:
            client = A2AClient(httpx_client, agent_card)

            payload: dict[str, any] = {
                'message': {
                    'role': 'user',
                    'parts': [{'kind': 'text', 'text': query}],
                    'messageId': uuid4().hex,
                    'taskId': task_id,
                    'contextId': context_id,
                },
            }
            request = SendStreamingMessageRequest(
                id=str(uuid4()), params=MessageSendParams(**payload)
            )
            response_stream = client.send_message_streaming(request)
            async for chunk in response_stream:
                # Save the artifact as a result of the node
                if isinstance(
                    chunk.root, SendStreamingMessageSuccessResponse
                ) and (isinstance(chunk.root.result, TaskArtifactUpdateEvent)):
                    artifact = chunk.root.result.artifact
                    self.results = artifact
                yield chunk


class WorkflowGraph:
    """워크플로우 노드 그래프.

    NetworkX DiGraph를 사용하여 워크플로우 DAG를 관리합니다.
    토폴로지 정렬 순서로 노드를 실행하고 일시정지/재개를 지원합니다.

    Attributes:
        graph: NetworkX 방향 그래프.
        nodes: 노드 ID와 WorkflowNode 매핑.
        latest_node: 마지막으로 추가된 노드 ID.
        state: 워크플로우 상태.
        paused_node_id: 일시정지된 노드 ID.
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.nodes = {}
        self.latest_node = None
        self.node_type = None
        self.state = Status.INITIALIZED
        self.paused_node_id = None

    def add_node(self, node) -> None:
        """워크플로우에 노드를 추가합니다.

        Args:
            node: 추가할 WorkflowNode.
        """
        logger.info(f'Adding node {node.id}')
        self.graph.add_node(node.id, query=node.task)
        self.nodes[node.id] = node
        self.latest_node = node.id

    def add_edge(self, from_node_id: str, to_node_id: str) -> None:
        """노드 간 엣지를 추가합니다.

        Args:
            from_node_id: 시작 노드 ID.
            to_node_id: 도착 노드 ID.

        Raises:
            ValueError: 잘못된 노드 ID.
        """
        if from_node_id not in self.nodes or to_node_id not in self.nodes:
            raise ValueError('Invalid node IDs')

        self.graph.add_edge(from_node_id, to_node_id)

    async def run_workflow(
        self, start_node_id: str | None = None
    ) -> AsyncIterable[dict[str, any]]:
        """워크플로우를 실행합니다.

        시작 노드부터 토폴로지 순서로 노드를 실행하고 결과를 스트리밍합니다.
        사용자 입력이 필요한 경우 워크플로우가 일시정지됩니다.

        Args:
            start_node_id: 시작할 노드 ID. None이면 루트 노드부터 시작.

        Yields:
            A2A 스트리밍 응답.
        """
        logger.info('Executing workflow graph')
        if not start_node_id or start_node_id not in self.nodes:
            start_nodes = [n for n, d in self.graph.in_degree() if d == 0]
        else:
            start_nodes = [self.nodes[start_node_id].id]

        applicable_graph = set()

        for node_id in start_nodes:
            applicable_graph.add(node_id)
            applicable_graph.update(nx.descendants(self.graph, node_id))

        complete_graph = list(nx.topological_sort(self.graph))
        sub_graph = [n for n in complete_graph if n in applicable_graph]
        logger.info(f'Sub graph {sub_graph} size {len(sub_graph)}')
        self.state = Status.RUNNING
        # Alternative is to loop over all nodes, but we only need the connected nodes.
        for node_id in sub_graph:
            node = self.nodes[node_id]
            node.state = Status.RUNNING
            query = self.graph.nodes[node_id].get('query')
            task_id = self.graph.nodes[node_id].get('task_id')
            context_id = self.graph.nodes[node_id].get('context_id')
            async for chunk in node.run_node(query, task_id, context_id):
                # When the workflow node is paused, do not yield any chunks
                # but, let the loop complete.
                if node.state != Status.PAUSED:
                    if isinstance(
                        chunk.root, SendStreamingMessageSuccessResponse
                    ) and (
                        isinstance(chunk.root.result, TaskStatusUpdateEvent)
                    ):
                        task_status_event = chunk.root.result
                        context_id = task_status_event.context_id
                        if (
                            task_status_event.status.state
                            == TaskState.input_required
                            and context_id
                        ):
                            node.state = Status.PAUSED
                            self.state = Status.PAUSED
                            self.paused_node_id = node.id
                    yield chunk
            if self.state == Status.PAUSED:
                break
            if node.state == Status.RUNNING:
                node.state = Status.COMPLETED
        if self.state == Status.RUNNING:
            self.state = Status.COMPLETED

    def set_node_attribute(self, node_id, attribute, value) -> None:
        """단일 노드 속성을 설정합니다."""
        nx.set_node_attributes(self.graph, {node_id: value}, attribute)

    def set_node_attributes(self, node_id, attr_val) -> None:
        """여러 노드 속성을 한 번에 설정합니다."""
        nx.set_node_attributes(self.graph, {node_id: attr_val})

    def is_empty(self) -> bool:
        """워크플로우가 비어있는지 확인합니다."""
        return self.graph.number_of_nodes() == 0
