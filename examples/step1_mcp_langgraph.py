# ruff: noqa: E402
"""
Step 1: MCP Server를 LangGraph Agent의 도구로 통합하기

=== 학습 목표 ===
이 예제는 MCP(Model Context Protocol) 서버의 도구를
LangGraph 에이전트에서 사용하는 방법을 보여줍니다.

=== 구현 내용 ===
1. MCP 서버에서 도구를 동적으로 로드
2. LangGraph의 create_react_agent를 통해 ReAct 패턴 구현
3. 스트리밍 응답으로 실시간 사용자 경험 제공
4. 도구 호출 과정의 투명한 로깅

=== 실행 방법 ===
1. MCP 서버 모음 Docker 로 실행: . docker/mcp-docker.sh (Windows 는 . docker/mcp-docker.ps1)
2. 환경변수 설정: OPENAI_API_KEY, TAVILY_API_KEY
3. 이 스크립트 실행: python examples/step1_mcp_langgraph.py

=== 주요 개념 ===
- MCP 서버에서 도구를 가져와 LangGraph 에이전트에 통합
- ReAct 패턴으로 자동 도구 선택 및 실행
- 스트리밍 응답 지원
- 도구 호출과 응답의 실시간 모니터링
"""

import asyncio
import sys
import os
from uuid import uuid4
from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 프로젝트 루트의 .env 파일 로드 (import 전에 먼저 로드, override=True로 기존 환경변수 덮어쓰기)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# 환경 변수 검증 시스템 사용
from src.utils.env_validator import validate_environment, print_env_report

# 환경 변수 검증
try:
    if not validate_environment(raise_on_error=True):
        print("[WARNING] 환경 변수 검증 실패. 아래 리포트를 확인하세요:")
        print_env_report()
        sys.exit(1)
except ValueError as e:
    print(f"[ERROR] 환경 변수 오류: {e}")
    print_env_report()
    sys.exit(1)

from src.lg_agents import SimpleLangGraphWithMCPAgent
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver


async def main():
    print("=== Step 1: MCP + LangGraph 통합 데모 ===\n")

    print("1. MCP 웹 검색 에이전트 생성 중...")
    agent = await SimpleLangGraphWithMCPAgent.create(
        model=init_chat_model(
            model="openai:gpt-4.1",
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY"),
        ),
        checkpointer=MemorySaver(),
        agent_name="simple_langgraph_with_mcp",
        is_debug=False,
    )

    test_queries = [
        # "2025년 AI 트렌드는 무엇인가요?",
        # "LangGraph와 MCP를 함께 사용하는 장점은 무엇인가요?",
        "OpenAI 의 2025년 08월 가장 최근 오픈소스 공개 모델에 대해 자세히 설명해주세요.",
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n{'=' * 60}")
        print(f"질문 {idx}: {query}")
        print(f"{'=' * 60}\n")

        lg_config = RunnableConfig(
            configurable={
                "thread_id": str(uuid4()),
            }
        )
        async for chunk in agent.graph.astream(
            {"messages": [HumanMessage(content=query)]}, config=lg_config
        ):
            if isinstance(chunk, dict):
                for node_state in chunk.values():
                    messages = node_state.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            # 도구 호출 정보 출력
                            if msg.tool_calls:
                                print("\n[도구 사용]")
                                for tool_call in msg.tool_calls:
                                    print(
                                        f"  - {tool_call['name']}: {tool_call['args']}"
                                    )
                                print()

                            if msg.content:
                                print(msg.content)


if __name__ == "__main__":
    print("""
        [INFO] 실행 전 확인사항:
        1. MCP - TAVILY 서버가 실행 중인지 확인 (포트 3001)
        2. OPENAI_API_KEY, TAVILY_API_KEY 환경변수가 설정되어 있는지 확인
    """)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        print("\nMCP 서버가 실행 중인지 확인하세요:")
