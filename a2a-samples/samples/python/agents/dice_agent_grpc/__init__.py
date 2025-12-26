"""주사위 에이전트 gRPC 패키지.

이 패키지는 gRPC 전송 프로토콜을 사용하는 A2A 주사위 에이전트를 구현합니다.
REST 기반 dice_agent_rest와 동일한 기능을 제공하지만, gRPC를 통해 통신합니다.

주요 구성요소:
    - agent: DiceAgent 클래스 - 주사위 굴리기 및 소수 판별 로직
    - agent_executor: DiceAgentExecutor 클래스 - A2A 프로토콜 연결
    - __main__: gRPC 서버 및 AgentCard HTTP 서버 실행 진입점
    - test_client: gRPC 클라이언트 테스트

아키텍처:
    - gRPC 서버: 실제 A2A 프로토콜 통신 담당 (기본 포트: 11001)
    - HTTP 서버: AgentCard 제공 (기본 포트: 11000)
      ※ gRPC는 well-known URL을 직접 제공할 수 없어 별도 HTTP 서버 필요
"""
