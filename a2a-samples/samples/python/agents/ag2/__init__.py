"""AG2 Python 코드 리뷰어 에이전트 패키지.

이 패키지는 AutoGen 2 (AG2) 프레임워크를 사용하여 Python 코드를
리뷰하고 mypy 타입 검사를 수행하는 A2A 에이전트를 제공합니다.

주요 구성요소:
    - a2a_python_reviewer: mypy 도구가 통합된 AG2 리뷰어 서버
    - cli_codegen_a2a_client: CLI 스크립트 생성 클라이언트 (argparse)
    - fastapi_codegen_a2a_client: FastAPI 애플리케이션 생성 클라이언트

아키텍처:
    이 예제는 AG2의 A2A 통합을 보여줍니다:
    1. ConversableAgent를 A2aAgentServer로 래핑하여 A2A 서버 생성
    2. A2aRemoteAgent로 원격 A2A 에이전트에 연결
    3. 로컬 AG2 에이전트와 원격 A2A 에이전트 간 대화 수행

주요 기능:
    - 엄격한 타입 검사 기반 코드 리뷰
    - mypy 도구를 통한 정적 분석
    - 코드 생성과 리뷰의 자동화된 반복
    - Clean Architecture 원칙 적용

서버 포트:
    기본 포트: 8000 (리뷰어 에이전트)
"""
