# ruff: noqa: E402
"""
MCPWebSearchAgent 테스트 모듈

이 모듈은 MCPWebSearchAgent의 기능을 종합적으로 테스트합니다.

실행 방법:
    python tests/test_simple_mcp_agent.py

전제 조건:
    - MCP 서버가 실행 중이어야 함
    - OPENAI_API_KEY 환경변수 설정
    - 인터넷 연결 (웹 검색 테스트를 위해)

테스트 범위:
    1. Agent 초기화 테스트
    2. MCP 도구 기능 테스트:
       - search_web: 웹 검색 기능
       - search_news: 뉴스 검색 기능  
       - search_multiple_queries: 복수 쿼리 검색
    3. Agent 질의 처리 테스트:
       - Python 관련 질문
       - AI 기술 동향 질문
       - FastAPI 정보 질문
       - 머신러닝 뉴스 질문
       - 존재하지 않는 주제 (에러 처리 테스트)

디버깅:
    - 각 도구별 결과 개수 확인
    - 응답 내용 및 사용된 도구 정보 출력
    - 예외 상황에 대한 상세한 오류 메시지
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lg_agents.retriever_agent import MCPWebSearchAgent


class TestMCPWebSearchAgent:
    """MCPWebSearchAgent 테스트 클래스"""
    
    def __init__(self):
        self.agent = None
    
    async def setup(self):
        """테스트 환경 설정"""
        try:
            self.agent = MCPWebSearchAgent()
            await self.agent.initialize()
            print("✅ Agent 초기화 완료")
        except Exception as e:
            print(f"❌ Agent 초기화 실패: {e}")
            raise
    
    async def test_tools(self) -> dict:
        """
        MCP 도구 테스트 - 각 도구의 기본 기능 확인
        
        테스트하는 도구들:
        - search_web: 웹 검색 기능 (Python 3.12 관련)
        - search_news: 뉴스 검색 기능 (AI developments 관련)  
        - search_multiple_queries: 복수 쿼리 동시 검색
        
        Returns:
            dict: 각 도구별 테스트 결과 (success, result_count 등)
        """
        if not self.agent or not self.agent.tools:
            return {"error": "도구가 로드되지 않았습니다"}
        
        test_results = {}
        
        try:
            # 1. search_web 테스트
            search_tool = next((tool for tool in self.agent.tools if tool.name == "search_web"), None)
            if search_tool:
                search_result = await search_tool.ainvoke({"query": "Python 3.12 new features"})
                test_results["search_web"] = {
                    "success": True,
                    "result_count": len(search_result) if isinstance(search_result, list) else 0
                }
            else:
                test_results["search_web"] = {"success": False, "error": "도구를 찾을 수 없음"}
            
            # 2. search_news 테스트
            news_tool = next((tool for tool in self.agent.tools if tool.name == "search_news"), None)
            if news_tool:
                news_result = await news_tool.ainvoke({"query": "AI developments"})
                test_results["search_news"] = {
                    "success": True,
                    "result_count": len(news_result) if isinstance(news_result, list) else 0
                }
            else:
                test_results["search_news"] = {"success": False, "error": "도구를 찾을 수 없음"}
            
            # 3. search_multiple_queries 테스트
            multi_tool = next((tool for tool in self.agent.tools if tool.name == "search_multiple_queries"), None)
            if multi_tool:
                multi_result = await multi_tool.ainvoke({"queries": ["Python", "AI"]})
                test_results["search_multiple_queries"] = {
                    "success": "error" not in multi_result,
                    "result": multi_result
                }
            else:
                test_results["search_multiple_queries"] = {"success": False, "error": "도구를 찾을 수 없음"}
            
        except Exception as e:
            test_results["error"] = str(e)
        
        return test_results
    
    async def test_queries(self):
        """
        에이전트 질의 테스트
        
        다양한 주제의 질문으로 에이전트 응답 품질을 확인합니다.
        각 질의에 대해 도구 사용 여부와 응답 내용을 검증합니다.
        """
        if not self.agent:
            print("❌ Agent가 초기화되지 않았습니다")
            return
        
        # 테스트 질의들
        test_queries = [
            "Python 3.12의 새로운 기능에 대해 알려주세요",
            "최근 AI 개발 동향은 어떻게 되나요?",
            "FastAPI와 관련된 최신 정보를 찾아주세요",
            "머신러닝 관련 뉴스를 알려주세요",
            "존재하지 않는 주제에 대해 알려주세요"  # 검색 결과가 없는 경우 테스트
        ]
        
        for query in test_queries:
            print(f"\n{'='*50}")
            print(f"질의: {query}")
            print('='*50)
            
            try:
                result = await self.agent.query(query)
                print(f"응답: {result['agent_response']}")
                
                if result['tool_calls']:
                    print(f"사용된 도구: {result['tool_calls']}")
                
                if not result['success']:
                    print(f"오류: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"질의 처리 오류: {e}")


async def main():
    """
    메인 테스트 실행 함수
    
    테스트 순서:
    1. TestMCPWebSearchAgent 인스턴스 생성
    2. 에이전트 초기화 및 MCP 도구 로딩
    3. 개별 도구 기능 테스트
    4. 종합적인 질의 응답 테스트
    """
    try:
        # 테스트 인스턴스 생성
        tester = TestMCPWebSearchAgent()
        
        # 테스트 환경 설정
        await tester.setup()
        
        # 도구 테스트
        print("🔧 도구 테스트 실행...")
        tool_test = await tester.test_tools()
        print(f"도구 테스트 결과: {tool_test}")
        
        # 질의 테스트
        print("\n🔍 질의 테스트 실행...")
        await tester.test_queries()
        
    except Exception as e:
        print(f"실행 오류: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 