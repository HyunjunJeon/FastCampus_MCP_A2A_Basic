"""Hello World 에이전트 실행자 모듈.

이 모듈은 가장 간단한 A2A AgentExecutor 구현을 제공합니다.
AgentExecutor 인터페이스의 핵심 메서드인 execute()와 cancel()을 구현하여
A2A 프로토콜을 통해 메시지를 주고받는 방법을 보여줍니다.

클래스:
    HelloWorldAgent: 실제 비즈니스 로직을 수행하는 에이전트 클래스
    HelloWorldAgentExecutor: A2A 프로토콜과 에이전트를 연결하는 실행자 클래스
"""
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message


# --8<-- [start:HelloWorldAgent]
class HelloWorldAgent:
    """Hello World 에이전트.

    가장 간단한 A2A 에이전트 구현으로, 'Hello World' 메시지를 반환합니다.
    이 클래스는 실제 비즈니스 로직을 캡슐화하며, AgentExecutor에 의해 호출됩니다.
    """

    async def invoke(self) -> str:
        """에이전트를 호출하여 인사 메시지를 반환합니다.

        Returns:
            str: 'Hello World' 문자열.
        """
        return 'Hello World'


# --8<-- [end:HelloWorldAgent]


# --8<-- [start:HelloWorldAgentExecutor_init]
class HelloWorldAgentExecutor(AgentExecutor):
    """Hello World 에이전트를 위한 AgentExecutor 구현.

    A2A 프로토콜의 AgentExecutor 인터페이스를 구현하여
    HelloWorldAgent를 감싸는 래퍼 클래스입니다.

    이 클래스는 A2A 서버로부터 요청을 받아 HelloWorldAgent를 호출하고,
    결과를 EventQueue를 통해 클라이언트에게 전달합니다.

    Attributes:
        agent: HelloWorldAgent 인스턴스. 실제 비즈니스 로직을 수행합니다.
    """

    def __init__(self) -> None:
        """HelloWorldAgentExecutor 인스턴스를 초기화합니다.

        내부적으로 HelloWorldAgent 인스턴스를 생성하여 저장합니다.
        """
        self.agent = HelloWorldAgent()

    # --8<-- [end:HelloWorldAgentExecutor_init]
    # --8<-- [start:HelloWorldAgentExecutor_execute]
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """피어 에이전트로부터 받은 메시지를 처리합니다.

        이 메서드는 A2A 서버가 새로운 메시지를 수신할 때 호출됩니다.
        HelloWorldAgent를 호출하여 결과를 얻고, EventQueue를 통해
        응답 메시지를 클라이언트에게 전달합니다.

        Args:
            context: 요청 컨텍스트. 현재 태스크, 메시지 등의 정보를 포함합니다.
            event_queue: 이벤트 큐. 응답 메시지를 클라이언트에게 전달하는 데 사용됩니다.

        Note:
            이 구현은 입력 메시지의 내용과 관계없이 항상 'Hello World'를 반환합니다.
        """
        result = await self.agent.invoke()
        await event_queue.enqueue_event(new_agent_text_message(result))

    # --8<-- [end:HelloWorldAgentExecutor_execute]

    # --8<-- [start:HelloWorldAgentExecutor_cancel]
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """실행 중인 태스크의 취소를 처리합니다.

        이 에이전트는 취소 기능을 지원하지 않습니다.
        취소 요청이 들어오면 예외를 발생시킵니다.

        Args:
            context: 요청 컨텍스트. 취소할 태스크의 정보를 포함합니다.
            event_queue: 이벤트 큐. 취소 관련 이벤트를 전달하는 데 사용될 수 있습니다.

        Raises:
            Exception: 이 에이전트는 취소를 지원하지 않으므로 항상 예외를 발생시킵니다.
        """
        raise Exception('cancel not supported')

    # --8<-- [end:HelloWorldAgentExecutor_cancel]
