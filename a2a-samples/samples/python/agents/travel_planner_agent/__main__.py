"""여행 플래너 에이전트 서버 진입점.

이 모듈은 여행 계획 수립을 지원하는 A2A 에이전트 서버를 실행합니다.
LangChain의 ChatOpenAI를 사용하여 스트리밍 응답을 제공하며,
사용자의 여행 관련 질문에 실용적인 조언을 제공합니다.

실행 방법:
    python -m travel_planner_agent

서버 포트:
    기본 포트: 10001

엔드포인트:
    - /.well-known/agent.json: AgentCard (에이전트 메타데이터)
    - /: A2A JSON-RPC 엔드포인트
"""
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent_executor import TravelPlannerAgentExecutor


if __name__ == '__main__':
    # 에이전트 스킬 정의
    # 이 스킬은 여행 계획 수립 기능을 나타냅니다
    skill = AgentSkill(
        id='travel_planner',
        name='travel planner agent',
        description='travel planner',
        tags=['travel planner'],
        examples=['hello', 'nice to meet you!'],
    )

    # AgentCard 설정
    # A2A 클라이언트가 이 에이전트를 검색하고 연결하는 데 사용하는 메타데이터
    agent_card = AgentCard(
        name='travel planner Agent',
        description='travel planner',
        url='http://localhost:10001/',
        version='1.0.0',
        default_input_modes=['text'],  # 텍스트 입력만 지원
        default_output_modes=['text'],  # 텍스트 출력만 지원
        capabilities=AgentCapabilities(streaming=True),  # 스트리밍 응답 활성화
        skills=[skill],
    )

    # 요청 핸들러 설정
    # DefaultRequestHandler가 A2A 프로토콜 메시지를 AgentExecutor로 라우팅합니다
    request_handler = DefaultRequestHandler(
        agent_executor=TravelPlannerAgentExecutor(),
        task_store=InMemoryTaskStore(),  # 태스크 상태를 메모리에 저장
    )

    # A2A 서버 애플리케이션 생성 및 실행
    server = A2AStarletteApplication(
        agent_card=agent_card, http_handler=request_handler
    )
    import uvicorn

    # 모든 네트워크 인터페이스에서 수신 대기 (0.0.0.0)
    uvicorn.run(server.build(), host='0.0.0.0', port=10001)
