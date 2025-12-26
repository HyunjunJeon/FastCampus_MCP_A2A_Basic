"""LangGraph 통화 변환 에이전트 서버 진입점.

이 모듈은 LangGraph 기반 통화 변환 A2A 에이전트 서버를 실행합니다.
환율 조회, 멀티턴 대화, 스트리밍, 푸시 알림 기능을 지원합니다.

주요 기능:
    - 실시간 환율 조회 (frankfurter.app API 사용)
    - 멀티턴 대화 (컨텍스트 유지)
    - 스트리밍 응답 지원
    - 푸시 알림 지원

실행 방법:
    python -m app --host localhost --port 10000

환경 변수:
    model_source: 모델 소스 선택 ('google' 또는 기타). 기본값: 'google'
    GOOGLE_API_KEY: Google AI API 키 (model_source='google'인 경우 필수)
    TOOL_LLM_URL: 커스텀 LLM 서버 URL (model_source!='google'인 경우 필수)
    TOOL_LLM_NAME: 커스텀 LLM 모델 이름 (model_source!='google'인 경우 필수)

서버 포트:
    기본 포트: 10000
"""
import logging
import os
import sys

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
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from dotenv import load_dotenv

from app.agent import CurrencyAgent
from app.agent_executor import CurrencyAgentExecutor


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """API 키 누락 시 발생하는 예외.

    필수 환경 변수(API 키 또는 LLM URL)가 설정되지 않았을 때 발생합니다.
    """


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10000)
def main(host: str, port: int) -> None:
    """통화 변환 에이전트 서버를 시작합니다.

    환경 변수를 확인하고 A2A 서버를 구성한 후 uvicorn으로 실행합니다.
    푸시 알림을 위한 설정도 함께 초기화합니다.

    Args:
        host: 서버가 바인딩할 호스트 주소. 기본값은 'localhost'.
        port: 서버가 리스닝할 포트 번호. 기본값은 10000.

    Raises:
        MissingAPIKeyError: 필수 환경 변수가 설정되지 않은 경우.
    """
    try:
        # 모델 소스에 따른 필수 환경 변수 확인
        if os.getenv('model_source', 'google') == 'google':
            if not os.getenv('GOOGLE_API_KEY'):
                raise MissingAPIKeyError(
                    'GOOGLE_API_KEY environment variable not set.'
                )
        else:
            # 커스텀 LLM 서버 사용 시 필수 환경 변수 확인
            if not os.getenv('TOOL_LLM_URL'):
                raise MissingAPIKeyError(
                    'TOOL_LLM_URL environment variable not set.'
                )
            if not os.getenv('TOOL_LLM_NAME'):
                raise MissingAPIKeyError(
                    'TOOL_LLM_NAME environment not variable not set.'
                )

        # 에이전트 기능 설정: 스트리밍 및 푸시 알림 지원
        capabilities = AgentCapabilities(streaming=True, push_notifications=True)

        # 에이전트 스킬 정의: 통화 환율 변환
        skill = AgentSkill(
            id='convert_currency',
            name='Currency Exchange Rates Tool',
            description='Helps with exchange values between various currencies',
            tags=['currency conversion', 'currency exchange'],
            examples=['What is exchange rate between USD and GBP?'],
        )

        # AgentCard 설정
        agent_card = AgentCard(
            name='Currency Agent',
            description='Helps with exchange rates for currencies',
            url=f'http://{host}:{port}/',
            version='1.0.0',
            default_input_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
            default_output_modes=CurrencyAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )


        # --8<-- [start:DefaultRequestHandler]
        # 푸시 알림을 위한 HTTP 클라이언트 및 설정 저장소 초기화
        httpx_client = httpx.AsyncClient()
        push_config_store = InMemoryPushNotificationConfigStore()
        push_sender = BasePushNotificationSender(httpx_client=httpx_client,
                        config_store=push_config_store)

        # 요청 핸들러 설정: 에이전트 실행자, 태스크 저장소, 푸시 알림 설정
        request_handler = DefaultRequestHandler(
            agent_executor=CurrencyAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_config_store=push_config_store,
            push_sender=push_sender
        )

        # A2A 서버 애플리케이션 생성
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # uvicorn으로 서버 실행
        uvicorn.run(server.build(), host=host, port=port)
        # --8<-- [end:DefaultRequestHandler]

    except MissingAPIKeyError as e:
        logger.error(f'오류: {e}')
        sys.exit(1)
    except Exception as e:
        logger.error(f'서버 시작 중 오류 발생: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
