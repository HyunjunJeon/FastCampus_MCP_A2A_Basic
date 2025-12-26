"""CLI 코드 생성기 A2A 클라이언트.

이 모듈은 AG2의 A2aRemoteAgent를 사용하여 원격 리뷰어 에이전트와
통신하면서 CLI 스크립트를 생성하는 클라이언트를 구현합니다.

워크플로우:
    1. 로컬 CodeGenAgent가 argparse 기반 CLI 스크립트 생성
    2. A2aRemoteAgent를 통해 원격 리뷰어 에이전트에 코드 전송
    3. 리뷰어가 mypy로 타입 검사 수행
    4. 오류가 있으면 CodeGenAgent가 수정하고 다시 제출
    5. 'No issues found.' 메시지가 나올 때까지 반복

주요 특징:
    - Clean Architecture 원칙 적용
    - argparse 전문가 에이전트
    - 단일 파일 스크립트 생성
    - PEP 723 스타일 의존성 명시 지원

실행 방법:
    1. 먼저 리뷰어 서버 실행: python a2a_python_reviewer.py
    2. 클라이언트 실행: python cli_codegen_a2a_client.py

필수 환경 변수:
    - OPENAI_API_KEY: OpenAI API 키

Note:
    system_message는 영문으로 유지됩니다 (LLM 지시사항).
"""
import os

from autogen import ConversableAgent, LLMConfig
from autogen.a2a import A2aRemoteAgent


# LLM 설정 (GPT-4o-mini 모델 사용)
config = LLMConfig(
    {
        'model': 'gpt-4o-mini',
        'api_key': os.getenv('OPENAI_API_KEY'),
    }
)

# CLI 코드 생성 에이전트 생성
# system_message는 영문 유지 (LLM 지시사항)
codegen_agent = ConversableAgent(
    name='CodeGenAgent',
    description='A agent that generates code for the user',
    system_message=(
        'You are specialist in Python with huge Clean Architecture experience. '
        'Also, you are an expert in argparse. '
        'You should create a simple scripts based on user demands. '
        'Generate code in a single file. Do not use any other files. '
        'Do not use any external dependencies if it is possible. '
        'Use [PEP 723](https://peps.python.org/pep-0723/) to specify script dependencies if it is required. '
        'Generate just a code, no other text or comments. '
        'Terminate conversation when reviewer agent has no issues with the code.'
    ),
    # 리뷰어가 'No issues found.'를 반환하면 대화 종료
    is_termination_msg=lambda msg: 'No issues found.' in msg.get('content', ''),
    llm_config=config,
)


# A2A 원격 에이전트 생성 (리뷰어 서버에 연결)
reviewer_agent = A2aRemoteAgent(
    url='http://localhost:8000',  # 리뷰어 서버 주소
    name='ReviewerAgent',
)


async def main() -> str:
    """코드 생성과 리뷰 대화를 실행합니다.

    A2aRemoteAgent를 일반 AG2 에이전트처럼 사용하여
    대화를 시작하고, 리뷰가 통과할 때까지 반복합니다.

    Returns:
        str: 최종 생성된 코드 (리뷰 통과한 버전).
    """
    # A2A 에이전트를 일반 AG2 에이전트처럼 사용
    result = await reviewer_agent.a_initiate_chat(
        codegen_agent,
        message='Please, generate a simple script, allows to transfer USD to EUR using any external API.',
    )
    # 마지막에서 두 번째 메시지가 최종 코드 (마지막은 'No issues found.')
    return result.chat_history[-2]['content']


if __name__ == '__main__':
    import asyncio

    code = asyncio.run(main())
    print(code)
