"""공통 유틸리티 모듈.

이 모듈은 A2A-MCP 시스템에서 사용되는 공유 유틸리티 함수들을 제공합니다.

주요 기능:
    - Google API 키 초기화
    - 로깅 설정
    - MCP 서버 설정 조회
"""
# type: ignore
import logging
import os

import google.generativeai as genai

from a2a_mcp.common.types import ServerConfig


logger = logging.getLogger(__name__)


def init_api_key():
    """Google Generative AI API 키를 초기화합니다.

    Raises:
        ValueError: GOOGLE_API_KEY 환경 변수가 설정되지 않은 경우.
    """
    if not os.getenv('GOOGLE_API_KEY'):
        logger.error('GOOGLE_API_KEY is not set')
        raise ValueError('GOOGLE_API_KEY is not set')

    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))


def config_logging():
    """기본 로깅을 설정합니다.

    A2A_LOG_LEVEL 또는 FASTMCP_LOG_LEVEL 환경 변수를 사용합니다.
    """
    log_level = (
        os.getenv('A2A_LOG_LEVEL') or os.getenv('FASTMCP_LOG_LEVEL') or 'INFO'
    ).upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))


def config_logger(logger):
    """특정 로거를 설정합니다.

    모든 로깅을 활성화할 때 발생하는 혼잡을 방지합니다.
    """
    # 환경 변수로 대체 예정
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def get_mcp_server_config() -> ServerConfig:
    """MCP 서버 설정을 반환합니다.

    Returns:
        ServerConfig: 기본 MCP 서버 설정.
    """
    return ServerConfig(
        host='localhost',
        port=10100,
        transport='sse',
        url='http://localhost:10100/sse',
    )
