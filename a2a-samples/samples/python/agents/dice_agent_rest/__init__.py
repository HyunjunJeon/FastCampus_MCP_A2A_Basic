"""주사위 에이전트 REST API 패키지.

이 패키지는 Google ADK를 사용하여 주사위 굴리기와 소수 판별 기능을 제공하는
A2A 에이전트를 구현합니다. REST/JSON 프로토콜을 사용하여 통신합니다.

주요 구성요소:
    - agent: DiceAgent 클래스 - 주사위 굴리기 및 소수 판별 로직
    - agent_executor: DiceAgentExecutor 클래스 - A2A 프로토콜 연결
    - __main__: A2A REST 서버 실행 진입점

기능:
    - 임의의 N면 주사위 굴리기 (기본값: 6면)
    - 숫자 목록에서 소수 판별
"""
