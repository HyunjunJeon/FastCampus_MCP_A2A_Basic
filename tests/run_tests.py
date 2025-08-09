#!/usr/bin/env python3
# ruff: noqa: E402
"""
테스트 실행 스크립트

이 스크립트는 프로젝트의 다양한 테스트를 통합적으로 실행할 수 있는 도구입니다.

실행 방법:
    # 모든 테스트 실행
    python tests/run_tests.py all
    
    # 에이전트 테스트만 실행
    python tests/run_tests.py agent
    
    # 통합 테스트만 실행 (pytest)
    python tests/run_tests.py integration
    
    # 옵션 없이 실행하면 기본값은 'all'
    python tests/run_tests.py

테스트 종류:
    1. agent: MCPWebSearchAgent 기능 테스트
       - MCP 도구 로딩 테스트
       - 웹 검색 기능 테스트
       - 에이전트 질의 응답 테스트
    
    2. integration: pytest 기반 통합 테스트
       - MCP 서버 연결 테스트
       - LangGraph 통합 테스트
       - 모킹을 통한 안정적 테스트
    
    3. all: 위의 모든 테스트 순차 실행

전제 조건:
    - MCP 서버 실행: docker-compose up -d
    - 환경 변수 설정: OPENAI_API_KEY
    - 필요 패키지 설치: pytest, httpx 등

디버깅:
    - 각 테스트 단계별 상세 로그
    - 성공/실패 결과 종합 보고
    - 실패 시 종료 코드 1 반환
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.test_simple_mcp_agent import TestMCPWebSearchAgent
from tests.integration_test import run_integration_tests


async def run_agent_tests():
    """에이전트 테스트 실행"""
    print("🧪 MCPWebSearchAgent 테스트 시작")
    print("=" * 50)
    
    try:
        tester = TestMCPWebSearchAgent()
        await tester.setup()
        
        # 도구 테스트
        print("🔧 도구 테스트 실행...")
        tool_test = await tester.test_tools()
        print(f"도구 테스트 결과: {tool_test}")
        
        # 질의 테스트
        print("\n🔍 질의 테스트 실행...")
        await tester.test_queries()
        
        print("\n✅ 에이전트 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 에이전트 테스트 실패: {e}")
        return False
    
    return True


def main():
    """메인 실행 함수"""
    print("🚀 테스트 실행기 시작")
    print("=" * 60)
    
    # 명령행 인수 확인
    test_type = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if test_type == "agent":
        # 에이전트 테스트만 실행
        success = asyncio.run(run_agent_tests())
        return 0 if success else 1
        
    elif test_type == "integration":
        # 통합 테스트만 실행
        return run_integration_tests()
        
    elif test_type == "all":
        # 모든 테스트 실행
        print("1️⃣ 에이전트 테스트 실행 중...")
        agent_success = asyncio.run(run_agent_tests())
        
        print("\n" + "=" * 60)
        print("2️⃣ 통합 테스트 실행 중...")
        integration_success = run_integration_tests()
        
        if agent_success and integration_success == 0:
            print("\n🎉 모든 테스트 통과!")
            return 0
        else:
            print("\n❌ 일부 테스트 실패")
            return 1
    
    else:
        print(f"❌ 알 수 없는 테스트 타입: {test_type}")
        print("사용법: python tests/run_tests.py [agent|integration|all]")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 