"""서명된 에이전트 실행자 모듈.

이 모듈은 AgentCard 서명/검증 시연을 위한 간단한 AgentExecutor 구현을 제공합니다.
실제 비즈니스 로직은 최소화되어 있으며, 서명 기능의 데모 목적으로 사용됩니다.

클래스:
    SignedAgentExecutor: 간단한 응답을 반환하는 AgentExecutor 구현
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message


class SignedAgentExecutor(AgentExecutor):
    """서명된 에이전트를 위한 테스트용 AgentExecutor 구현.

    이 클래스는 AgentCard 서명/검증 기능을 시연하기 위한 간단한
    에이전트 실행자입니다. 모든 요청에 대해 'Verify me!' 메시지를 반환합니다.

    Note:
        이 에이전트의 주요 목적은 서명된 AgentCard의 검증 프로세스를
        시연하는 것이므로, 실제 비즈니스 로직은 포함되어 있지 않습니다.
    """

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """에이전트 로직을 실행합니다.

        간단하게 'Verify me!' 메시지를 반환합니다.
        이는 사용자에게 AgentCard 검증을 상기시키는 시연용 응답입니다.

        Args:
            context: 요청 컨텍스트. 사용자 입력 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 응답 메시지를 클라이언트에 전달합니다.
        """
        await event_queue.enqueue_event(new_agent_text_message('Verify me!'))

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """취소 요청을 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.
        취소 요청이 들어오면 콘솔에 메시지를 출력합니다.

        Args:
            context: 요청 컨텍스트. 취소할 태스크 정보를 포함합니다.
            event_queue: 이벤트 큐. 취소 관련 이벤트 전달에 사용될 수 있습니다.
        """
        print('Cancel not supported.')
