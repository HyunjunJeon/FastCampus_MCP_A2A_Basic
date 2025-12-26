"""LangGraph 기반 통화 변환 에이전트 패키지.

이 패키지는 LangGraph와 A2A 프로토콜을 통합하는 통화 변환 에이전트를 제공합니다.
환율 조회 도구를 사용하여 다양한 통화 간의 환율 정보를 제공합니다.

주요 구성요소:
    - agent: CurrencyAgent 클래스 - LangGraph 기반 환율 조회 에이전트
    - agent_executor: CurrencyAgentExecutor 클래스 - A2A 프로토콜 연결
    - __main__: A2A 서버 실행 진입점
    - test_client: 에이전트 테스트를 위한 클라이언트

주요 기능:
    - 환율 조회 (get_exchange_rate 도구)
    - 멀티턴 대화 지원 (컨텍스트 유지)
    - 스트리밍 응답 지원
    - 푸시 알림 지원

기술 스택:
    - LangGraph: 상태 기반 에이전트 워크플로우
    - LangChain: LLM 통합 (Google Generative AI 또는 OpenAI)
    - Pydantic: 구조화된 응답 형식
"""
