"""주사위 에이전트 핵심 로직 모듈 (gRPC 버전).

이 모듈은 Google ADK(Agent Development Kit)를 사용하여 주사위 굴리기와
소수 판별 기능을 구현하는 LLM 에이전트를 제공합니다. LiteLLM을 통해
다양한 LLM 모델을 지원합니다.

주요 기능:
    - N면 주사위 굴리기 (roll_dice 도구)
    - 숫자 목록에서 소수 판별 (check_prime 도구)
    - LiteLLM을 통한 다양한 모델 지원

환경 변수:
    LITELLM_MODEL: 사용할 LLM 모델 (기본값: gemini/gemini-2.0-flash-001)

클래스:
    DiceAgent: 주사위 굴리기 및 소수 판별 기능을 제공하는 에이전트

함수:
    roll_dice: N면 주사위를 굴려 결과를 반환
    check_prime: 숫자 목록에서 소수를 판별
    create_agent: LlmAgent 인스턴스를 생성
"""
import os
import random

from collections.abc import AsyncIterable

from google.adk import Runner
from google.adk.agents import LlmAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService
from google.genai import types


def roll_dice(N: int = 6) -> int:
    """N면 주사위를 굴립니다. 면 수가 지정되지 않으면 6을 사용합니다.

    이 함수는 LLM 에이전트의 도구로 사용되어 사용자가 요청한 면 수의
    주사위를 굴리고 결과를 반환합니다.

    Args:
        N: 굴릴 주사위의 면 수. 기본값은 6.

    Returns:
        int: 1과 N 사이의 정수 (양 끝값 포함).

    Examples:
        >>> roll_dice()  # 6면 주사위
        3
        >>> roll_dice(20)  # 20면 주사위
        17
    """
    return random.randint(1, N)


def check_prime(nums: list[int]) -> str:
    """주어진 숫자 목록에서 소수인지 판별합니다.

    이 함수는 LLM 에이전트의 도구로 사용되어 사용자가 제공한
    숫자 목록에서 어떤 숫자가 소수인지 판별합니다.

    Args:
        nums: 소수 여부를 확인할 숫자 목록.

    Returns:
        str: 소수인 숫자들을 나타내는 문자열. 소수가 없으면 해당 메시지 반환.

    Examples:
        >>> check_prime([1, 2, 3, 4, 5])
        '2, 3, 5 are prime numbers.'
        >>> check_prime([4, 6, 8])
        'No prime numbers found.'
    """
    primes = set()
    for number in nums:
        number = int(number)
        if number <= 1:
            continue
        is_prime = True
        for i in range(2, int(number**0.5) + 1):
            if number % i == 0:
                is_prime = False
            break
        if is_prime:
            primes.add(number)
    return (
        'No prime numbers found.'
        if not primes
        else f'{", ".join(str(num) for num in primes)} are prime numbers.'
    )


def create_agent() -> LlmAgent:
    """주사위 굴리기 및 소수 판별 도구가 장착된 LLM 에이전트를 생성합니다.

    이 함수는 LiteLLM을 통해 설정된 모델을 사용하는 LlmAgent를 생성하고,
    roll_dice와 check_prime 도구를 장착합니다.

    Returns:
        LlmAgent: 도구가 장착된 LLM 에이전트 인스턴스.

    Note:
        LITELLM_MODEL 환경 변수를 통해 모델을 지정할 수 있습니다.
        에이전트 지시사항(instruction)은 영문으로 유지됩니다 (LLM 프롬프트).
    """
    # 환경 변수에서 LLM 모델 설정 (기본값: gemini/gemini-2.0-flash-001)
    LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini/gemini-2.0-flash-001')
    return LlmAgent(
        model=LiteLlm(model=LITELLM_MODEL),
        name='dice_roll_agent',
        instruction="""
You roll dice and answer questions about the outcome of the dice rolls.
You can roll dice of different sizes.
You can use multiple tools in parallel by calling functions in parallel (in one request and in one round).
The only things you do are roll dice for the user and discuss the outcomes.
It is ok to discuss previous dice roles, and comment on the dice rolls.
When you are asked to roll a die, you must call the roll_die tool with the number of sides. Be sure to pass in an integer. Do not pass in a string.
You should never roll a die on your own.
When checking prime numbers, call the check_prime tool with a list of integers. Be sure to pass in a list of integers. You should never pass in a string.
You should not check prime numbers before calling the tool.
When you are asked to roll a die and check prime numbers, you should always make the following two function calls:
1. You should first call the roll_die tool to get a roll. Wait for the function response before calling the check_prime tool.
2. After you get the function response from roll_die tool, you should call the check_prime tool with the roll_die result.
    2.1 If user asks you to check primes based on previous rolls, make sure you include the previous rolls in the list.
3. When you respond, you must include the roll_die result from step 1.
You should always perform the previous 3 steps when asking for a roll and checking prime numbers.
You should not rely on the previous history on prime results.
    """,
        description='Rolls an N-sided dice and answers questions about the outcome of the dice rolls. Can also answer questions about prime numbers.',
        tools=[
            roll_dice,
            check_prime,
        ],
    )


class DiceAgent:
    """주사위 굴리기 요청을 처리하는 에이전트.

    이 클래스는 Google ADK Runner를 사용하여 LLM 에이전트를 실행하고,
    세션 관리 및 스트리밍 응답을 처리합니다. LiteLLM을 통해 다양한
    LLM 모델을 지원합니다.

    Attributes:
        SUPPORTED_CONTENT_TYPES: 지원되는 콘텐츠 타입 목록.
        _agent: 내부 LlmAgent 인스턴스.
        _user_id: 세션 관리에 사용되는 기본 사용자 ID.
        _runner: 에이전트 실행 및 세션 관리를 담당하는 Runner 인스턴스.
    """

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def __init__(self) -> None:
        """DiceAgent 인스턴스를 초기화합니다.

        LlmAgent를 생성하고 Runner를 설정합니다. 세션, 아티팩트, 메모리 서비스는
        모두 인메모리 구현을 사용합니다.
        """
        self._agent = create_agent()
        self._user_id = 'remote_agent'
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[tuple[bool, str]]:
        """사용자 쿼리를 처리하고 스트리밍 응답을 생성합니다.

        이 메서드는 세션을 조회하거나 생성한 후, ADK Runner를 통해
        에이전트를 실행합니다. 중간 상태와 최종 응답을 튜플 형태로
        스트리밍합니다.

        Args:
            query: 사용자가 입력한 질문 또는 명령.
            session_id: 대화 세션을 식별하는 고유 ID.

        Yields:
            tuple[bool, str]: (완료 여부, 응답 텍스트) 형태의 튜플.
                - 완료되지 않은 경우: (False, 'working...')
                - 완료된 경우: (True, 최종 응답 텍스트)

        Note:
            세션이 존재하지 않으면 자동으로 새 세션을 생성합니다.
        """
        # 기존 세션 조회
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )

        # 사용자 메시지를 ADK Content 형식으로 변환
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=query)]
        )

        # 세션이 없으면 새로 생성
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )

        # ADK Runner로 에이전트 실행 및 스트리밍 응답 처리
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content
        ):
            if event.is_final_response():
                # 최종 응답: 모든 텍스트 파트를 줄바꿈으로 연결하여 반환
                yield (
                    True,
                    '\n'.join([p.text for p in event.content.parts if p.text]),
                )
            else:
                # 중간 상태: 작업 진행 중 알림
                yield (False, 'working...')
