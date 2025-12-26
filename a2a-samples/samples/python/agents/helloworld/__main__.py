"""helloworld 에이전트 서버 진입점.

이 모듈은 Hello World A2A 에이전트 서버를 실행하는 메인 진입점입니다.
uvicorn을 사용하여 A2AStarletteApplication을 호스팅하고,
공개(public) 및 확장(extended) AgentCard를 모두 지원합니다.

실행 방법:
    python -m helloworld

서버 포트:
    기본 포트: 9999

주요 기능:
    - 공개 AgentCard: 기본 hello_world 스킬 제공
    - 확장 AgentCard: 인증된 사용자에게 super_hello_world 스킬 추가 제공
    - 스트리밍 지원: AgentCapabilities(streaming=True)
"""
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent_executor import (
    HelloWorldAgentExecutor,  # type: ignore[import-untyped]
)


if __name__ == '__main__':
    # --8<-- [start:AgentSkill]
    # 기본 스킬 정의: 간단한 Hello World 응답을 반환하는 스킬
    skill = AgentSkill(
        id='hello_world',
        name='Returns hello world',
        description='just returns hello world',
        tags=['hello world'],
        examples=['hi', 'hello world'],
    )
    # --8<-- [end:AgentSkill]

    # 확장 스킬 정의: 인증된 사용자에게만 제공되는 추가 스킬
    extended_skill = AgentSkill(
        id='super_hello_world',
        name='Returns a SUPER Hello World',
        description='A more enthusiastic greeting, only for authenticated users.',
        tags=['hello world', 'super', 'extended'],
        examples=['super hi', 'give me a super hello'],
    )

    # --8<-- [start:AgentCard]
    # 공개용 AgentCard: 인증 없이 접근 가능한 기본 에이전트 정보
    # 이 카드는 /.well-known/agent.json 경로에서 제공됩니다
    public_agent_card = AgentCard(
        name='Hello World Agent',
        description='Just a hello world agent',
        url='http://localhost:9999/',
        version='1.0.0',
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],  # 공개 카드에는 기본 스킬만 포함
        supports_authenticated_extended_card=True,
    )
    # --8<-- [end:AgentCard]

    # 인증된 확장 AgentCard: 인증된 사용자에게 추가 기능을 노출
    # 기본 카드를 복사하고 확장 스킬을 추가합니다
    specific_extended_agent_card = public_agent_card.model_copy(
        update={
            'name': 'Hello World Agent - Extended Edition',  # 구분을 위한 다른 이름
            'description': 'The full-featured hello world agent for authenticated users.',
            'version': '1.0.1',  # 버전도 다르게 설정 가능
            # url, default_input_modes, default_output_modes, supports_authenticated_extended_card 등
            # 다른 필드들은 명시하지 않으면 public_agent_card에서 상속됩니다
            'skills': [
                skill,
                extended_skill,
            ],  # 확장 카드에는 모든 스킬 포함
        }
    )

    # 요청 핸들러 설정: 에이전트 실행자와 태스크 저장소를 연결
    request_handler = DefaultRequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # A2A 서버 애플리케이션 생성
    # 공개 카드와 확장 카드를 모두 등록하여 인증 수준에 따라 다른 정보 제공
    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler,
        extended_agent_card=specific_extended_agent_card,
    )

    # uvicorn으로 서버 실행 (모든 네트워크 인터페이스에서 9999 포트로 수신)
    uvicorn.run(server.build(), host='0.0.0.0', port=9999)
