"""여행 플래너 에이전트 모듈.

이 모듈은 LangChain과 ChatOpenAI를 사용하여 여행 계획을 수립하는
에이전트를 구현합니다. 스트리밍 응답을 지원하며, 외부 설정 파일을
통해 모델과 API 엔드포인트를 구성할 수 있습니다.

주요 기능:
    - config.json을 통한 유연한 모델 설정
    - 비동기 스트리밍으로 실시간 응답 제공
    - 전문적인 여행 어시스턴트 시스템 프롬프트
"""
import json
import os
import sys

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class TravelPlannerAgent:
    """여행 플래너 에이전트.

    LangChain의 ChatOpenAI를 사용하여 여행 계획, 목적지 정보,
    여행 추천 등을 제공하는 AI 어시스턴트입니다. 사용자의 선호도와
    제약 조건을 고려하여 실용적인 여행 조언을 제공합니다.

    Attributes:
        model: ChatOpenAI 인스턴스. 대화 생성에 사용됩니다.

    설정 파일 형식 (config.json):
        {
            "api_key": "OPENAI_API_KEY",  # 환경 변수 이름
            "model_name": "gpt-4o",       # 사용할 모델
            "base_url": null              # 커스텀 API 엔드포인트 (선택사항)
        }
    """

    def __init__(self) -> None:
        """TravelPlannerAgent 인스턴스를 초기화합니다.

        config.json 파일에서 모델 설정을 로드하고 ChatOpenAI 클라이언트를
        초기화합니다. 설정 파일이 없거나 필수 환경 변수가 설정되지 않은 경우
        오류 메시지와 함께 프로그램이 종료됩니다.

        Raises:
            SystemExit: 설정 파일이 없거나 API 키가 설정되지 않은 경우.
        """
        try:
            # 설정 파일 로드
            with open('config.json') as f:
                config = json.load(f)

            # API 키 환경 변수 확인
            if not os.getenv(config['api_key']):
                print(f'{config["api_key"]} environment variable not set.')
                sys.exit(1)
            api_key = os.getenv(config['api_key'])

            # ChatOpenAI 모델 초기화
            self.model = ChatOpenAI(
                model=config['model_name'] or 'gpt-4o',
                base_url=config['base_url'] or None,
                api_key=api_key,  # type: ignore
                temperature=0.7,  # 생성 다양성 제어 (0-2, 높을수록 랜덤)
            )
        except FileNotFoundError:
            print('Error: The configuration file config.json cannot be found.')
            sys.exit()
        except KeyError as e:
            print(f'The configuration file is missing required fields: {e}')
            sys.exit()

    async def stream(self, query: str) -> AsyncGenerator[dict[str, Any], None]:
        """사용자 쿼리에 대한 응답을 스트리밍 방식으로 반환합니다.

        LangChain의 astream 메서드를 사용하여 LLM 응답을 청크 단위로
        비동기적으로 생성합니다. 시스템 프롬프트는 여행 전문가로서의
        역할과 응답 가이드라인을 정의합니다.

        Args:
            query: 사용자의 여행 관련 질문 또는 요청.

        Yields:
            dict: 응답 청크를 포함하는 딕셔너리.
                - content (str): 텍스트 청크 내용
                - done (bool): 스트리밍 완료 여부

        Note:
            시스템 프롬프트는 영문으로 유지됩니다 (LLM 지시사항).
            프롬프트는 여행 계획, 일정 수립, 실용적인 조언에 대한
            상세한 가이드라인을 포함합니다.
        """
        try:
            # 대화 히스토리 초기화 (시스템 메시지 포함)
            # 시스템 프롬프트 - 영문 유지 (LLM 지시사항)
            messages = [
                SystemMessage(
                    content="""
                You are an expert travel assistant specializing in trip planning, destination information,
                and travel recommendations. Your goal is to help users plan enjoyable, safe, and
                realistic trips based on their preferences and constraints.

                When providing information:
                - Be specific and practical with your advice
                - Consider seasonality, budget constraints, and travel logistics
                - Highlight cultural experiences and authentic local activities
                - Include practical travel tips relevant to the destination
                - Format information clearly with headings and bullet points when appropriate

                For itineraries:
                - Create realistic day-by-day plans that account for travel time between attractions
                - Balance popular tourist sites with off-the-beaten-path experiences
                - Include approximate timing and practical logistics
                - Suggest meal options highlighting local cuisine
                - Consider weather, local events, and opening hours in your planning

                Always maintain a helpful, enthusiastic but realistic tone and acknowledge
                any limitations in your knowledge when appropriate.
                """
                )
            ]

            # 사용자 메시지를 대화 히스토리에 추가
            messages.append(HumanMessage(content=query))

            # 스트리밍 모드로 모델 호출하여 응답 생성
            async for chunk in self.model.astream(messages):
                # 텍스트 콘텐츠 청크 반환
                if hasattr(chunk, 'content') and chunk.content:
                    yield {'content': chunk.content, 'done': False}

            # 스트리밍 완료 신호
            yield {'content': '', 'done': True}

        except Exception as e:
            print(f'error：{e!s}')
            yield {
                'content': 'Sorry, an error occurred while processing your request.',
                'done': True,
            }
