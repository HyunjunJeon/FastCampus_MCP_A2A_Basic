"""콘텐츠 플래너 에이전트 정의 모듈.

이 모듈은 Google ADK(Agent Development Kit)를 사용하여
콘텐츠 개요를 생성하는 에이전트를 정의합니다.

주요 특징:
    - Gemini 2.5 Flash 모델 사용
    - Google Search 도구 연동으로 정보 수집
    - 고수준 설명에서 상세한 개요 생성

Note:
    description과 instruction은 영문으로 유지됩니다 (LLM 지시사항).
"""
from google.adk.agents import Agent
from google.adk.tools import google_search


# 콘텐츠 플래너 에이전트 정의
# description과 instruction은 영문 유지 (LLM 지시사항)
root_agent = Agent(
    name="content_planner_agent",
    model="gemini-2.5-flash",
    description=("Planning agent that creates a detailed and logical outline for a piece of content,"
                 "given a high-level description."),
    instruction=("You are an expert content planner. Your task is to create a detailed and logical outline for a piece"
                 "of content, given a high-level description."),
    tools=[google_search],  # Google Search 도구를 사용하여 정보 수집
)
