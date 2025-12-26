"""VEO 비디오 생성 에이전트 서버 진입점.

이 모듈은 Google VEO 모델을 사용하여 텍스트 프롬프트로부터
비디오를 생성하는 A2A 에이전트 서버를 실행합니다.

실행 방법:
    python -m veo_video_gen --host localhost --port 10003

서버 포트:
    기본 포트: 10003

필수 환경 변수:
    - GOOGLE_GENAI_USE_VERTEXAI: 'TRUE' 필수
    - GOOGLE_CLOUD_PROJECT: GCP 프로젝트 ID
    - GOOGLE_CLOUD_LOCATION: GCP 리전 (예: us-central1)
    - VIDEO_GEN_GCS_BUCKET: 비디오 저장용 GCS 버킷 이름
    - SIGNER_SERVICE_ACCOUNT_EMAIL: 서명된 URL 생성용 서비스 계정 (선택사항)
"""
import logging
import os

import click

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent import VideoGenerationAgent
from agent_executor import VideoGenerationAgentExecutor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    '--host', default='localhost', help='Hostname to bind the server to.'
)
@click.option(
    '--port', default=10003, help='Port to bind the server to.'
)
def main(host: str, port: int) -> None:
    """VEO 비디오 생성 에이전트 서버를 시작합니다.

    Google VEO 모델을 사용하여 텍스트에서 비디오를 생성하는
    에이전트 서버를 실행합니다. Vertex AI와 GCS가 필수입니다.

    Args:
        host: 서버 바인딩 호스트 주소.
        port: 서버 리스닝 포트 번호.
    """
    try:
        # Vertex AI 사용 여부 확인
        use_vertex_ai = (
            os.getenv('GOOGLE_GENAI_USE_VERTEXAI', 'FALSE').upper() == 'TRUE'
        )

        if use_vertex_ai:
            # Vertex AI 필수 환경 변수 검증
            if not os.getenv('GOOGLE_CLOUD_PROJECT'):
                raise Exception(
                    'GOOGLE_CLOUD_PROJECT environment variable not set, but GOOGLE_GENAI_USE_VERTEXAI is TRUE. '
                    'Vertex AI requires a project ID.'
                )
            if not os.getenv('GOOGLE_CLOUD_LOCATION'):
                raise Exception(
                    'GOOGLE_CLOUD_LOCATION environment variable not set, but GOOGLE_GENAI_USE_VERTEXAI is TRUE. '
                    'Vertex AI requires a location (e.g., us-central1).'
                )
            logger.info(
                f'Using Vertex AI with project: {os.getenv("GOOGLE_CLOUD_PROJECT")} and location: {os.getenv("GOOGLE_CLOUD_LOCATION")}'
            )
        else:
            # Vertex AI가 필수임을 알림
            logger.error(
                'Vertex AI is required for this agent. Please set GOOGLE_GENAI_USE_VERTEXAI to TRUE and configure GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION.'
            )

        # GCS 버킷 이름 확인 (비디오 출력에 필수)
        if not os.getenv(VideoGenerationAgent.GCS_BUCKET_NAME_ENV_VAR):
            raise Exception(
                f'{VideoGenerationAgent.GCS_BUCKET_NAME_ENV_VAR} environment variable not set. '
                'This is required for storing generated videos.'
            )
        logger.info(
            f'Using GCS bucket: {os.getenv(VideoGenerationAgent.GCS_BUCKET_NAME_ENV_VAR)}'
        )

        # 서명된 URL 생성용 서비스 계정 확인 (선택사항)
        if os.getenv(VideoGenerationAgent.SIGNER_SERVICE_ACCOUNT_EMAIL_ENV_VAR):
            logger.info(
                f'Using signer service account: {os.getenv(VideoGenerationAgent.SIGNER_SERVICE_ACCOUNT_EMAIL_ENV_VAR)} for GCS signed URLs.'
            )
        else:
            logger.info(
                'No SIGNER_SERVICE_ACCOUNT_EMAIL set. Ambient credentials will be used for GCS signed URLs. '
                "Ensure the runtime identity has 'Service Account Token Creator' role on itself or the target SA if impersonation is intended via ADC."
            )

        # AgentCard 설정
        # 스트리밍 업데이트를 지원하여 진행률을 실시간으로 전송
        capabilities = AgentCapabilities(streaming=True)

        # 비디오 생성 스킬 정의
        skill = AgentSkill(
            id='generate_video_from_prompt',
            name='Generate Video from Text Prompt (VEO)',
            description='Generates a video based on a textual description using VEO. '
            'Provides progress updates and a link to the final video.',
            tags=['video', 'generation', 'multimodal', 'veo'],
            examples=[
                'Create a video of a futuristic cityscape at sunset.',
                'Generate a short clip of a cat playing with a yarn ball in a sunny room.',
            ],
        )

        agent_card = AgentCard(
            name='VEO Video Generation Agent',
            description="This agent uses Google's VEO model to generate videos from text prompts and provides a GCS link to the output.",
            url=f'http://{host}:{port}/',
            version='1.0.0',
            default_input_modes=VideoGenerationAgent.SUPPORTED_INPUT_CONTENT_TYPES,
            default_output_modes=VideoGenerationAgent.SUPPORTED_OUTPUT_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # 요청 핸들러 설정
        request_handler = DefaultRequestHandler(
            agent_executor=VideoGenerationAgentExecutor(),
            task_store=InMemoryTaskStore(),
        )

        # A2A 서버 애플리케이션 생성
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        logger.info(
            f'Starting VEO Video Generation Agent server on http://{host}:{port}'
        )

        import uvicorn

        uvicorn.run(server.build(), host=host, port=port)

    except ImportError as e:
        logger.error(
            f"Import Error: {e}. Please ensure all dependencies like 'google-cloud-storage' and 'google-generativeai' are installed."
        )
        exit(1)
    except Exception as e:
        logger.error(
            f'An unexpected error occurred during server startup: {e}',
            exc_info=True,
        )
        exit(1)


if __name__ == '__main__':
    main()
