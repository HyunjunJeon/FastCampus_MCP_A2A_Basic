"""차트 생성 에이전트 모듈.

이 모듈은 CrewAI 프레임워크를 사용하여 CSV 형식의 데이터를
막대 차트 이미지로 변환하는 에이전트를 구현합니다.
matplotlib과 pandas를 사용하여 데이터 시각화를 수행합니다.

주요 구성요소:
    - Imagedata: 생성된 이미지 데이터 모델
    - generate_chart_tool: CrewAI 도구로 등록된 차트 생성 함수
    - ChartGenerationAgent: 데이터 시각화 전문가 에이전트
"""
import base64
import logging

from collections.abc import AsyncIterable
from io import BytesIO
from typing import Any
from uuid import uuid4

import matplotlib.pyplot as plt
import pandas as pd

from crewai import Agent, Crew, Task
from crewai.process import Process
from crewai.tools import tool
from dotenv import load_dotenv
from pydantic import BaseModel
from utils import cache


load_dotenv()

logger = logging.getLogger(__name__)


class Imagedata(BaseModel):
    """생성된 이미지 데이터 모델.

    차트 생성 결과를 담는 Pydantic 모델입니다.
    성공 시 이미지 데이터를, 실패 시 오류 메시지를 포함합니다.

    Attributes:
        id: 이미지 고유 ID (UUID).
        name: 파일 이름.
        mime_type: MIME 타입 (예: 'image/png').
        bytes: Base64 인코딩된 이미지 바이트.
        error: 오류 발생 시 오류 메시지.
    """

    id: str | None = None
    name: str | None = None
    mime_type: str | None = None
    bytes: str | None = None
    error: str | None = None


@tool('ChartGenerationTool')
def generate_chart_tool(prompt: str, session_id: str) -> str:
    """matplotlib을 사용하여 CSV 형식 입력에서 막대 차트를 생성합니다.

    CrewAI 도구로 등록되어 에이전트가 호출할 수 있습니다.
    생성된 이미지는 세션 캐시에 저장되고 이미지 ID가 반환됩니다.

    Args:
        prompt: CSV 형식의 데이터 문자열 (헤더 포함, 2열 필수).
        session_id: 세션 식별자. 이미지 캐싱에 사용됩니다.

    Returns:
        str: 생성된 이미지의 ID. 오류 시 -999999999 반환.

    Note:
        입력 데이터는 반드시 두 개의 열(Category, Value)을 가져야 합니다.
        Value 열의 모든 값은 숫자여야 합니다.
    """
    logger.info(f'>>>Chart tool called with prompt: {prompt}')

    if not prompt:
        raise ValueError('Prompt cannot be empty')

    try:
        # CSV 형식 입력 파싱
        from io import StringIO

        df = pd.read_csv(StringIO(prompt))
        if df.shape[1] != 2:
            raise ValueError(
                'Input must have exactly two columns: Category and Value'
            )
        df.columns = ['Category', 'Value']
        df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
        if df['Value'].isnull().any():
            raise ValueError('All values must be numeric')

        # 막대 차트 생성
        fig, ax = plt.subplots()
        ax.bar(df['Category'], df['Value'])
        ax.set_xlabel('Category')
        ax.set_ylabel('Value')
        ax.set_title('Bar Chart')

        # 버퍼에 저장
        buf = BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)
        image_bytes = buf.read()

        # 이미지 인코딩
        data = Imagedata(
            bytes=base64.b64encode(image_bytes).decode('utf-8'),
            mime_type='image/png',
            name='generated_chart.png',
            id=uuid4().hex,
        )

        logger.info(
            f'Caching image with ID: {data.id} for session: {session_id}'
        )

        # 이미지 캐싱
        session_data = cache.get(session_id) or {}
        session_data[data.id] = data
        cache.set(session_id, session_data)

        return data.id

    except Exception as e:
        logger.error(f'Error generating chart: {e}')
        return -999999999


class ChartGenerationAgent:
    """차트 생성을 위한 CrewAI 기반 에이전트.

    CSV 형식의 구조화된 데이터를 막대 차트 이미지로 변환합니다.
    CrewAI의 Agent, Task, Crew를 사용하여 데이터 시각화
    전문가 역할을 수행합니다.

    Attributes:
        SUPPORTED_CONTENT_TYPES: 지원하는 콘텐츠 타입 목록.
        chart_creator_agent: CrewAI Agent 인스턴스.
        chart_creation_task: 차트 생성 Task 정의.
        chart_crew: Agent와 Task를 포함하는 Crew.
    """

    SUPPORTED_CONTENT_TYPES = ['text', 'text/plain', 'image/png']

    def __init__(self) -> None:
        """ChartGenerationAgent 인스턴스를 초기화합니다.

        CrewAI의 Agent, Task, Crew를 설정합니다.
        에이전트는 데이터 시각화 전문가 역할을 수행하며,
        ChartGenerationTool을 사용하여 차트를 생성합니다.
        """
        # 차트 생성 전문가 에이전트 설정
        self.chart_creator_agent = Agent(
            role='Chart Creation Expert',
            goal='Generate a bar chart image based on structured CSV input.',
            backstory='You are a data visualization expert who transforms structured data into visual charts.',
            verbose=False,
            allow_delegation=False,  # 다른 에이전트에게 위임하지 않음
            tools=[generate_chart_tool],
        )

        # 차트 생성 태스크 정의
        # 태스크 설명은 영문 유지 (CrewAI 프레임워크 지시사항)
        self.chart_creation_task = Task(
            description=(
                "You are given a prompt: '{user_prompt}'.\n"
                "If the prompt includes comma-separated key:value pairs (e.g. 'a:100, b:200'), "
                "reformat it into CSV with header 'Category,Value'.\n"
                "Ensure it becomes two-column CSV, then pass that to the 'ChartGenerationTool'.\n"
                "Use session ID: '{session_id}' when calling the tool."
            ),
            expected_output='The id of the generated chart image',
            agent=self.chart_creator_agent,
        )

        # Crew 설정 (순차 처리)
        self.chart_crew = Crew(
            agents=[self.chart_creator_agent],
            tasks=[self.chart_creation_task],
            process=Process.sequential,
            verbose=False,
        )

    import uuid

    def invoke(self, query: str, session_id: str | None = None) -> str:
        """에이전트를 호출하여 차트를 생성합니다.

        사용자 쿼리를 CrewAI에 전달하고 차트 생성 결과를 반환합니다.
        세션 ID가 제공되지 않으면 자동으로 생성합니다.

        Args:
            query: 사용자의 차트 생성 요청. CSV 형식 또는 키:값 쌍.
            session_id: 세션 식별자 (선택사항). 이미지 캐싱에 사용됩니다.

        Returns:
            str: CrewAI 실행 결과 (생성된 이미지 ID 포함).
        """
        import uuid

        # 세션 ID 정규화 또는 생성
        session_id = session_id or f'session-{uuid.uuid4().hex}'
        logger.info(
            f'[invoke] Using session_id: {session_id} for query: {query}'
        )

        inputs = {
            'user_prompt': query,
            'session_id': session_id,
        }

        # CrewAI 실행
        response = self.chart_crew.kickoff(inputs)
        logger.info(f'[invoke] Chart tool returned image ID: {response}')
        return response

    async def stream(self, query: str) -> AsyncIterable[dict[str, Any]]:
        """스트리밍 응답을 반환합니다.

        이 에이전트는 스트리밍을 지원하지 않습니다.

        Args:
            query: 사용자 쿼리.

        Raises:
            NotImplementedError: 항상 발생. 스트리밍이 지원되지 않습니다.
        """
        raise NotImplementedError('Streaming is not supported.')

    def get_image_data(self, session_id: str, image_key: str) -> Imagedata:
        """캐시에서 이미지 데이터를 조회합니다.

        세션 ID와 이미지 키를 사용하여 이전에 생성된 이미지를
        캐시에서 가져옵니다.

        Args:
            session_id: 세션 식별자.
            image_key: 이미지 ID (generate_chart_tool이 반환한 값).

        Returns:
            Imagedata: 이미지 데이터. 찾지 못한 경우 error 필드가 설정됩니다.
        """
        session_data = cache.get(session_id)

        if not session_data:
            logger.error(
                f'[get_image_data] No session data for session_id: {session_id}'
            )
            return Imagedata(
                error=f'No session data found for session_id: {session_id}'
            )

        if image_key not in session_data:
            logger.error(
                f'[get_image_data] Image key {image_key} not found in session data'
            )
            return Imagedata(
                error=f'Image ID {image_key} not found in session {session_id}'
            )

        return session_data[image_key]
