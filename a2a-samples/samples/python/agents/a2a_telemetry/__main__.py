"""A2A 텔레메트리 에이전트 서버 진입점.

이 모듈은 OpenTelemetry 기반 분산 추적(tracing)을 지원하는 A2A 에이전트 서버를 실행합니다.
Google Search 도구를 사용하여 질문에 답변하는 Q&A 에이전트를 호스팅하며,
모든 요청과 응답을 Jaeger로 추적할 수 있습니다.

주요 기능:
    - OpenTelemetry 기반 분산 추적
    - Jaeger exporter를 통한 트레이스 수집
    - Starlette 애플리케이션 자동 계측
    - Google Search 도구 통합 Q&A 에이전트

실행 방법:
    python -m a2a_telemetry --host localhost --port 10020

환경 변수:
    GOOGLE_API_KEY: Google API 키 (필수)

서버 포트:
    기본 포트: 10020

텔레메트리 설정:
    - 서비스 이름: a2a-telemetry-sample
    - Jaeger 엔드포인트: http://localhost:4317 (gRPC)
"""
import logging
import os

import click
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent_executor import QnAAgentExecutor
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger(__name__)
logging.basicConfig()


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10020)
def main(host: str, port: int) -> None:
    """A2A 텔레메트리 샘플 gRPC 서버를 시작합니다.

    OpenTelemetry 기반 분산 추적을 설정하고 Q&A 에이전트 서버를 실행합니다.
    모든 HTTP 요청은 자동으로 계측되어 Jaeger에서 추적할 수 있습니다.

    Args:
        host: 서버가 바인딩할 호스트 주소. 기본값은 'localhost'.
        port: 서버가 리스닝할 포트 번호. 기본값은 10020.

    Raises:
        ValueError: GOOGLE_API_KEY 환경 변수가 설정되지 않은 경우.
    """
    # Google API 키 확인 (필수)
    if not os.getenv('GOOGLE_API_KEY'):
        raise ValueError('GOOGLE_API_KEY is not set.')

    # 에이전트 스킬 정의: 질문-답변 기능
    skill = AgentSkill(
        id='question_answer',
        name='Q&A Agent',
        description='A helpful assistant agent that can answer questions.',
        tags=['Question-Answer'],
        examples=[
            'Who is leading 2025 F1 Standings?',
            'Where can i find an active volcano?',
        ],
    )

    # 에이전트 실행자 및 카드 설정
    agent_executor = QnAAgentExecutor()
    agent_card = AgentCard(
        name='Q&A Agent',
        description='A helpful assistant agent that can answer questions.',
        url=f'http://{host}:{port}/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor, task_store=InMemoryTaskStore()
    )

    # OpenTelemetry 텔레메트리 설정
    logger.debug('Telemetry Configuration')

    # Jaeger 및 Grafana에서 조회할 수 있도록 서비스 이름 설정
    resource = Resource(
        attributes={
            'service.name': 'a2a-telemetry-sample',
            'service.version': '1.0',
        }
    )

    # TracerProvider 생성 및 등록
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    tracer_provider = trace.get_tracer_provider()

    # Jaeger exporter 생성 및 설정 (gRPC 전송 사용)
    jaeger_exporter = OTLPSpanExporter(
        endpoint='http://localhost:4317', insecure=True
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

    # A2A 서버 애플리케이션 빌드
    server = A2AStarletteApplication(agent_card, request_handler)
    starlette_app = server.build()

    # Starlette 애플리케이션에 자동 계측 적용
    # 모든 HTTP 요청/응답이 자동으로 트레이스됩니다
    StarletteInstrumentor().instrument_app(starlette_app)

    # 서버 실행
    uvicorn.run(starlette_app, host=host, port=port)


if __name__ == '__main__':
    main()
