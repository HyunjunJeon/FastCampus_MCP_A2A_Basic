"""콘텐츠 플래너 에이전트 패키지.

이 패키지는 Google ADK(Agent Development Kit)와 Gemini 모델을 사용하여
콘텐츠 개요를 생성하는 A2A 에이전트를 제공합니다.

주요 구성요소:
    - content_planner_agent: ADK Agent 정의 (Gemini 2.5 Flash 사용)
    - agent_executor: ADKAgentExecutor - ADK 에이전트를 A2A와 연결
    - __main__: 서버 진입점 (포트 10001)

주요 기능:
    - 고수준 콘텐츠 설명에서 상세한 개요 생성
    - Google Search 도구를 활용한 정보 수집
    - 스트리밍 응답 지원
"""
