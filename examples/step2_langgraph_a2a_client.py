# ruff: noqa: E402
"""
Step 2: LangGraph + A2A 통합

=== 학습 목표 ===
LangGraph 에이전트를 A2A(Agent-to-Agent) 스펙에 맞게 래핑(Wrapping)하여
표준화된 에이전트 통신 프로토콜을 구현하는 방법을 학습합니다.

=== 구현 내용 ===
1. LangGraph 에이전트를 A2A 서버로 래핑
2. 임베디드 A2A 서버 시작/종료 자동 관리
3. A2A 클라이언트를 통한 에이전트 간 통신
4. 비동기 컨텍스트 매니저로 리소스 자동 정리

=== 실행 방법 ===
1. 환경변수 설정: OPENAI_API_KEY, TAVILY_API_KEY
2. MCP 서버 실행 상태 확인
3. 이 스크립트 실행: python examples/step2_langgraph_a2a_client.py

=== 주요 개념 ===
- A2A 프로토콜을 통한 에이전트 간 표준화된 통신
- 임베디드 서버 모델로 네트워크 구성 자동화
- Context Manager를 활용한 리소스 관리
- 비동기 에이전트 상호작용
"""

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가 - 상위 디렉토리에서 src 모듈 import (반드시 src import 전에 실행)
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from langchain.chat_models import init_chat_model
from src.a2a_integration.a2a_lg_utils import create_agent_card
from src.a2a_integration.a2a_lg_embedded_server_manager import (
    start_embedded_graph_server,
)
from src.a2a_integration.a2a_lg_client_utils import A2AClientManager


async def test_a2a_agent_client():
    """
    A2A 에이전트 클라이언트 테스트 함수

    === 기능 설명 ===
    1. 임베디드 A2A 서버 자동 시작
    2. A2A 클라이언트를 통한 에이전트와 통신
    3. 다양한 쿼리 테스트
    4. 리소스 자동 정리
    """
    print("[TEST] A2A 에이전트 클라이언트 테스트")
    print("=" * 50)

    from a2a.types import AgentSkill
    from src.lg_agents.simple.simple_lg_agent_with_mcp import (
        SimpleLangGraphWithMCPAgent,
    )

    agent = await SimpleLangGraphWithMCPAgent.create(
        model=init_chat_model(
            model="openai:gpt-4.1",
            temperature=0.1,
            api_key=os.getenv("OPENAI_API_KEY"),
        ),
        agent_name="simple_langgraph_with_mcp",
        is_debug=False,
    )
    skills = [
        AgentSkill(
            id="simple_langgraph_with_mcp",
            name="검색 에이전트",
            description="다양한 검색을 지원하는 에이전트",
            tags=["search", "agent"],
            examples=[
                "OpenAI 의 가장 최근 오픈소스 공개 모델에 대해 자세히 설명해주세요."
            ],
        )
    ]

    host = "0.0.0.0"
    port = 10080

    async with start_embedded_graph_server(
        graph=agent.graph,
        agent_card=create_agent_card(
            name="검색 에이전트",
            description="다양한 검색을 지원하는 에이전트",
            url=f"http://{host}:{port}",
            skills=skills,
            version="1.0.0",
            default_input_modes=["text/plain", "application/json"],
            default_output_modes=["text/plain", "application/json"],
        ),
        host=host,
        port=port,
    ) as server_info:
        print(
            {
                k: server_info[k]
                for k in ("base_url", "host", "port")
                if k in server_info
            }
        )
        print(f"[SUCCESS] 그래프 기반 A2A 서버 시작: {server_info['base_url']}")

        # A2A 클라이언트 생성 및 테스트
        async with A2AClientManager(server_info["base_url"]) as client:
            print(f"[SUCCESS] A2A 클라이언트 연결 성공: {server_info['base_url']}")

            # 1) 단순 텍스트 질의
            query = "LangGraph 와 A2A 통합의 장-단점은?"
            print(f"\n  [INFO] 텍스트 쿼리: {query}")
            print("  [INFO] A2A 프로토콜(텍스트) 전송 중...")
            print("===" * 30)
            response = await client.send_query(query)
            print(f"  [INFO] [에이전트 응답] {response}")
            print("===" * 30)

            # 2) JSON(DataPart) 전송
            payload = {
                "messages": [
                    {
                        "role": "human",
                        "content": "오픈AI와 랭그래프 최근 변화 요약, 지금은 2025년 8월 11일",
                    },
                ],
            }
            print("\n  [INFO] JSON 페이로드(DataPart) 전송")
            print("  [INFO] A2A 프로토콜(JSON) 전송 중...")
            print("===" * 30)
            try:
                await client.send_data(payload)
            except Exception as e:
                print(f"[WARNING] JSON 전송 실패: {e}")
            print("===" * 30)

            print("\n[SUCCESS] 모든 A2A 에이전트 통신 테스트 완료!")


async def main():
    """
    Step 2 데모 메인 함수

    === 실행 과정 ===
    1. A2A 에이전트 클라이언트 테스트 실행
    2. 예외 처리 및 리소스 정리
    3. 실행 결과 리포트
    """
    print("=== Step 2: LangGraph + A2A 통합 데모 ===\n")
    print("=" * 60)
    print("[INFO] 임베디드 A2A 서버 모델로 LangGraph 에이전트 테스트 시작")
    print("[INFO] 네트워크 설정과 리소스 관리가 전체 자동화됨")

    try:
        await test_a2a_agent_client()

        print("\n[SUCCESS] Step 2 - LangGraph + A2A 통합 데모 성공적 완료!")
        print("[INFO] Context Manager에 의한 모든 리소스 자동 정리 완료!")
        print("[INFO] A2A 서버 연결 해제 및 포트 해제 완료!")

    except KeyboardInterrupt:
        print("\n\n[INFO] 사용자에 의해 중단됨")
        print("[INFO] 중단 중에도 Context Manager가 리소스를 안전하게 정리함")
    except Exception as e:
        print(f"\n[WARNING] 예외 발생: {e}")
        print("[INFO] Context Manager가 오류 상황에도 정리 작업을 수행함")
    finally:
        print("\n[INFO] Step 2 데모 종료 - 모든 리소스 정리 완료")


if __name__ == "__main__":
    """
    Step 2 데모 실행 진입점
    
    === 사전 준비사항 ===
    1. 환경변수 설정 (OPENAI_API_KEY, TAVILY_API_KEY)
    2. MCP 서버 실행 상태 확인
    3. 네트워크 연결 확인
    
    === 예상 동작 ===
    1. 임베디드 A2A 서버 자동 시작
    2. A2A 클라이언트 연결
    3. 에이전트와 A2A 통신 테스트
    4. 모든 리소스 자동 정리
    """
    print("[INFO] Step 2 실행 전 안내:")
    print("- 이 데모는 임베디드 모드로 실행되므로 별도의 서버 시작이 불필요합니다.")
    print("- Context Manager가 A2A 서버와 클라이언트를 자동으로 관리합니다.")
    print("- 모든 네트워크 리소스가 자동으로 정리됩니다.\n")

    # 비동기 메인 함수 실행
    asyncio.run(main())
