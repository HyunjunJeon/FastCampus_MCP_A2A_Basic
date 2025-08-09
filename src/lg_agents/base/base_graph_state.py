"""
LangGraph 에이전트의 기본 상태 클래스 정의.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BaseGraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]