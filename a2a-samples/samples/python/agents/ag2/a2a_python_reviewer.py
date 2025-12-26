"""AG2 Python 코드 리뷰어 에이전트 서버.

이 모듈은 AutoGen 2 (AG2) 프레임워크의 ConversableAgent를 사용하여
Python 코드를 리뷰하는 A2A 에이전트 서버를 구현합니다.

주요 기능:
    - mypy 도구를 통한 정적 타입 검사
    - 엄격한 타입 검사 중심의 코드 리뷰
    - A2A 프로토콜을 통한 원격 에이전트 통신

AG2 A2A 통합:
    - A2aAgentServer: ConversableAgent를 A2A 서버로 래핑
    - LLM 도구 등록: @register_for_llm 데코레이터로 mypy 도구 연결
    - ASGI 서버: uvicorn으로 서비스 제공

실행 방법:
    python a2a_python_reviewer.py

서버 포트:
    기본 포트: 8000

필수 환경 변수:
    - OPENAI_API_KEY: OpenAI API 키

Note:
    system_message는 영문으로 유지됩니다 (LLM 지시사항).
"""
import os
import tempfile

from typing import Annotated

from autogen import ConversableAgent, LLMConfig
from autogen.a2a import A2aAgentServer
from mypy import api


# AG2 에이전트 설정 (GPT-4o-mini 모델 사용)
config = LLMConfig(
    {
        'model': 'gpt-4o-mini',
        'api_key': os.getenv('OPENAI_API_KEY'),
    }
)

# 코드 리뷰어 에이전트 생성
# system_message는 영문 유지 (LLM 지시사항)
reviewer_agent = ConversableAgent(
    name='ReviewerAgent',
    description='An agent that reviews the code for the user',
    system_message=(
        'You are an expert in code review pretty strict and focused on typing. '
        'Please, use mypy tool to validate the code.'
        'If mypy has no issues with the code, return "No issues found."'
    ),
    llm_config=config,
    human_input_mode='NEVER',  # 사람 입력 비활성화 (완전 자동화)
)


# mypy 도구를 LLM에 등록하여 코드 검증 수행
@reviewer_agent.register_for_llm(
    name='mypy-checker',
    description='Check the code with mypy tool',
)
def review_code_with_mypy(
    code: Annotated[
        str,
        'Raw code content to review. Code should be formatted as single file.',
    ],
) -> str:
    """mypy를 사용하여 Python 코드의 타입을 검사합니다.

    임시 파일에 코드를 저장하고 mypy API를 호출하여
    정적 타입 검사를 수행합니다.

    Args:
        code: 검사할 Python 코드 문자열. 단일 파일 형식이어야 합니다.

    Returns:
        str: mypy 검사 결과.
            - 오류가 있는 경우: 오류 메시지 (stderr)
            - 오류가 없는 경우: 성공 메시지 (stdout) 또는 'No issues found.'
    """
    # 임시 파일에 코드 저장 후 mypy 실행
    with tempfile.NamedTemporaryFile('w', suffix='.py') as tmp:
        tmp.write(code)
        stdout, stderr, exit_status = api.run([tmp.name])
    if exit_status != 0:
        return stderr
    return stdout or 'No issues found.'


# AG2 에이전트를 A2A 서버로 래핑
# A2aAgentServer가 A2A 프로토콜 호환 ASGI 앱을 생성
server = A2aAgentServer(reviewer_agent).build()

if __name__ == '__main__':
    # uvicorn으로 ASGI 서버 실행
    import uvicorn

    uvicorn.run(server, host='0.0.0.0', port=8000)
