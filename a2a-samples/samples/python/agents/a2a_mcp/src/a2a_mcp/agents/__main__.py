"""A2A 에이전트 서버 진입점 모듈.

이 모듈은 에이전트 카드 기반으로 적절한 여행 에이전트를 선택하고
A2A 프로토콜 서버를 시작합니다.

주요 기능:
    - 에이전트 카드 파싱 및 에이전트 인스턴스화
    - A2A Starlette 서버 구성
    - Uvicorn 기반 서버 실행

지원 에이전트:
    - Orchestrator Agent: 멀티에이전트 오케스트레이터
    - Langraph Planner Agent: 여행 계획 에이전트
    - Air Ticketing Agent: 항공권 예약 에이전트
    - Hotel Booking Agent: 호텔 예약 에이전트
    - Car Rental Agent: 렌터카 예약 에이전트

실행 예시:
    python -m a2a_mcp.agents --agent-card agent_cards/orchestrator.json
"""
# type: ignore

import json
import logging
import sys

from pathlib import Path

import click
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import AgentCard
from a2a_mcp.common import prompts
from a2a_mcp.common.agent_executor import GenericAgentExecutor
from adk_travel_agent import TravelAgent
from langgraph_planner_agent import LangGraphPlannerAgent
from orchestrator_agent import OrchestratorAgent


logger = logging.getLogger(__name__)


def get_agent(agent_card: AgentCard):
    """에이전트 카드를 기반으로 적절한 에이전트 인스턴스를 반환합니다.

    Args:
        agent_card: 에이전트 메타데이터가 포함된 AgentCard.

    Returns:
        에이전트 인스턴스 (OrchestratorAgent, LangGraphPlannerAgent, TravelAgent 중 하나).

    Raises:
        Exception: 에이전트 초기화 실패 시.
    """
    try:
        if agent_card.name == 'Orchestrator Agent':
            return OrchestratorAgent()
        if agent_card.name == 'Langraph Planner Agent':
            return LangGraphPlannerAgent()
        if agent_card.name == 'Air Ticketing Agent':
            return TravelAgent(
                agent_name='AirTicketingAgent',
                description='Book air tickets given a criteria',
                instructions=prompts.AIRFARE_COT_INSTRUCTIONS,
            )
        if agent_card.name == 'Hotel Booking Agent':
            return TravelAgent(
                agent_name='HotelBookingAgent',
                description='Book hotels given a criteria',
                instructions=prompts.HOTELS_COT_INSTRUCTIONS,
            )
        if agent_card.name == 'Car Rental Agent':
            return TravelAgent(
                agent_name='CarRentalBookingAgent',
                description='Book rental cars given a criteria',
                instructions=prompts.CARS_COT_INSTRUCTIONS,
            )
            # return LangraphCarRentalAgent()
    except Exception as e:
        raise e


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10101)
@click.option('--agent-card', 'agent_card')
def main(host, port, agent_card):
    """에이전트 서버를 시작합니다.

    에이전트 카드 JSON 파일을 읽어 적절한 에이전트를 인스턴스화하고
    A2A 프로토콜 서버를 시작합니다.

    Args:
        host: 서버 바인딩 호스트.
        port: 서버 바인딩 포트.
        agent_card: 에이전트 카드 JSON 파일 경로.

    Raises:
        ValueError: 에이전트 카드가 지정되지 않은 경우.
        FileNotFoundError: 에이전트 카드 파일을 찾을 수 없는 경우.
        JSONDecodeError: JSON 파싱 실패.
    """
    try:
        if not agent_card:
            raise ValueError('Agent card is required')
        with Path.open(agent_card) as file:
            data = json.load(file)
        agent_card = AgentCard(**data)

        client = httpx.AsyncClient()
        push_notification_config_store = InMemoryPushNotificationConfigStore()
        push_notification_sender = BasePushNotificationSender(
            client, config_store=push_notification_config_store
        )

        request_handler = DefaultRequestHandler(
            agent_executor=GenericAgentExecutor(agent=get_agent(agent_card)),
            task_store=InMemoryTaskStore(),
            push_config_store=push_notification_config_store,
            push_sender=push_notification_sender,
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        logger.info(f'Starting server on {host}:{port}')

        uvicorn.run(server.build(), host=host, port=port)
    except FileNotFoundError:
        logger.error(f"Error: File '{agent_card}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Error: File '{agent_card}' contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
