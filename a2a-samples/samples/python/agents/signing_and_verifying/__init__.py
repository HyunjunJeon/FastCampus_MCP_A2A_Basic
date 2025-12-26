"""AgentCard 서명 및 검증 에이전트 패키지.

이 패키지는 A2A 프로토콜에서 AgentCard의 디지털 서명 및 검증 기능을
시연하는 에이전트를 제공합니다. ECDSA(ES256) 알고리즘을 사용하여
AgentCard의 무결성과 출처를 검증합니다.

주요 구성요소:
    - agent_executor: SignedAgentExecutor 클래스 - 간단한 에이전트 실행자
    - __main__: 서명된 AgentCard를 제공하는 A2A 서버 실행 진입점
    - test_client: 서명 검증 기능을 테스트하는 클라이언트

주요 기능:
    - ECDSA P-256 (ES256) 알고리즘을 사용한 AgentCard 서명
    - JWK(JSON Web Key) 기반 공개키 배포
    - 공개/확장 AgentCard 모두 서명 지원

보안 개념:
    - 서명: 에이전트 서버가 AgentCard의 무결성을 보장
    - 검증: 클라이언트가 AgentCard가 변조되지 않았음을 확인
    - JKU(JSON Key URL): 공개키를 조회할 수 있는 URL
    - KID(Key ID): 여러 키 중 사용할 키를 식별
"""
