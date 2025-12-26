"""공통 타입 정의 모듈.

이 모듈은 A2A-MCP 시스템에서 사용되는 공유 타입들을 정의합니다.

주요 타입:
    - ServerConfig: 서버 설정
    - PlannerTask: 계획 태스크
    - TripInfo: 여행 정보
    - TaskList: 태스크 목록
    - AgentResponse: 에이전트 응답
"""
# type: ignore

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ServerConfig(BaseModel):
    """서버 설정.

    Attributes:
        host: 호스트 주소.
        port: 포트 번호.
        transport: 전송 프로토콜.
        url: 전체 URL.
    """

    host: str
    port: int
    transport: str
    url: str


class PlannerTask(BaseModel):
    """계획 에이전트가 생성한 단일 태스크.

    Attributes:
        id: 태스크 순서 ID.
        description: 실행할 태스크 설명.
        status: 태스크 상태.
    """

    id: int = Field(description='Sequential ID for the task.')
    description: str = Field(
        description='Clear description of the task to be executed.'
    )
    status: (
        Any
        | Literal[
            'input_required',
            'completed',
            'error',
            'pending',
            'incomplete',
            'todo',
            'not_started',
        ]
        | None
    ) = Field(description='Status of the task', default='input_required')


class TripInfo(BaseModel):
    """여행 정보.

    Attributes:
        total_budget: 총 예산.
        origin: 출발지.
        destination: 목적지.
        type: 여행 유형 (business/leisure).
        start_date: 시작일.
        end_date: 종료일.
        travel_class: 좌석 등급.
        accommodation_type: 숙소 유형.
        room_type: 객실 유형.
        is_car_rental_required: 렌터카 필요 여부.
        type_of_car: 차량 유형.
        no_of_travellers: 여행자 수.
        checkin_date: 호텔 체크인 날짜.
        checkout_date: 호텔 체크아웃 날짜.
        car_rental_start_date: 렌터카 시작일.
        car_rental_end_date: 렌터카 종료일.
    """

    total_budget: str | None = Field(description='Total Budget for the trip')
    origin: str | None = Field(description='Trip Origin')
    destination: str | None = Field(description='Trip destination')
    type: str | None = Field(description='Trip type, business or leisure')
    start_date: str | None = Field(description='Trip Start Date')
    end_date: str | None = Field(description='Trip End Date')
    travel_class: str | None = Field(
        description='Travel class, first, business or economy'
    )
    accommodation_type: str | None = Field(
        description='Luxury Hotel, Budget Hotel, AirBnB, etc'
    )
    room_type: str | None = Field(description='Suite, Single, Double etc.')
    is_car_rental_required: str | None = Field(
        description='Whether a rental car is required in the trip.'
    )
    type_of_car: str | None = Field(
        description='Type of the car, SUV, Sedan, Truck etc.'
    )
    no_of_travellers: str | None = Field(
        description='Total number of travellers in the trip'
    )

    checkin_date: str | None = Field(description='Hotel Checkin Date')
    checkout_date: str | None = Field(description='Hotel Checkout Date')
    car_rental_start_date: str | None = Field(
        description='Car Rental Start Date'
    )
    car_rental_end_date: str | None = Field(description='Car Rental End Date')

    @model_validator(mode='before')
    @classmethod
    def set_dependent_var(cls, values):
        """종속 필드를 자동 설정합니다.

        start_date/end_date를 기반으로 체크인/아웃 및 렌터카 날짜를 설정합니다.
        """
        if isinstance(values, dict) and 'start_date' in values:
            values['checkin_date'] = values['start_date']

        if isinstance(values, dict) and 'end_date' in values:
            values['checkout_date'] = values['end_date']

        if isinstance(values, dict) and 'start_date' in values:
            values['car_rental_start_date'] = values['start_date']

        if isinstance(values, dict) and 'end_date' in values:
            values['car_rental_end_date'] = values['end_date']
        return values


class TaskList(BaseModel):
    """계획 에이전트 출력 스키마.

    Attributes:
        original_query: 컨텍스트용 원본 사용자 쿼리.
        trip_info: 여행 정보.
        tasks: 순차 실행할 태스크 목록.
    """

    original_query: str | None = Field(
        description='The original user query for context.'
    )

    trip_info: TripInfo | None = Field(description='Trip information')

    tasks: list[PlannerTask] = Field(
        description='A list of tasks to be executed sequentially.'
    )


class AgentResponse(BaseModel):
    """에이전트 응답 스키마.

    Attributes:
        content: 응답 내용.
        is_task_complete: 태스크 완료 여부.
        require_user_input: 사용자 입력 필요 여부.
    """

    content: str | dict = Field(description='The content of the response.')
    is_task_complete: bool = Field(description='Whether the task is complete.')
    require_user_input: bool = Field(
        description='Whether the agent requires user input.'
    )
