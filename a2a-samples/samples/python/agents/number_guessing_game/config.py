"""포트 할당을 위한 중앙 집중식 설정.

A2A 숫자 맞추기 데모에서 사용하는 포트 설정입니다.
기본 포트가 시스템의 서비스와 충돌하는 경우 아래 상수를 수정하세요.
모든 에이전트가 이 모듈에서 import하므로 변경 사항이 자동으로 전파됩니다.

포트 할당:
    - AgentAlice (평가자): 8001
    - AgentBob (CLI 프론트엔드): 8002
    - AgentCarol (시각화/셔플): 8003
"""

# 기본 리스닝 포트
AGENT_ALICE_PORT = 8001
AGENT_BOB_PORT = 8002
AGENT_CAROL_PORT = 8003
