#!/usr/bin/env python3
"""
A2A 서버 웹 검색 테스트 스크립트

목적:
- A2A 서버를 통한 실제 웹 검색 기능 검증
- JSON-RPC 2.0 프로토콜을 사용한 메시지 전송 테스트
- 웹 검색 도구의 정상 동작 확인

테스트 시나리오:
1. 다양한 검색 쿼리로 A2A 서버에 요청 전송
2. JSON-RPC 2.0 표준 형식으로 메시지 구성
3. 서버 응답 분석 및 검색 결과 검증

전제 조건:
- A2A 서버가 localhost:8080에서 실행 중이어야 함
- MCP 웹 검색 도구가 서버에 연동되어 있어야 함
- 네트워크 연결이 원활해야 함 (실제 웹 검색 수행)

예상 결과:
- 각 검색 쿼리에 대한 적절한 응답 반환
- JSON-RPC 표준 응답 형식 준수
- 검색 결과의 품질 및 관련성 확인
"""
import asyncio
import json
import httpx
import uuid

async def test_web_search():
    """
    A2A 서버를 통한 웹 검색 테스트
    
    이 함수는 A2A 서버의 웹 검색 기능을 테스트합니다.
    여러 가지 검색 쿼리를 JSON-RPC 2.0 형식으로 전송하고
    서버의 응답을 분석하여 검색 기능이 정상 작동하는지 확인합니다.
    
    테스트 대상:
    - AI 발전 동향 검색
    - OpenAI 최신 소식 검색
    - LangGraph 개념 검색
    
    Returns:
        None: 테스트 결과는 콘솔에 실시간으로 출력됨
        
    Raises:
        Exception: 네트워크 오류 또는 서버 응답 오류 시
    """
    client = httpx.AsyncClient(timeout=60.0)
    
    try:
        print("🔍 A2A 웹 검색 테스트 시작")
        print("=" * 50)
        
        # 웹 검색 요청
        # 테스트할 검색 쿼리 목록
        # 다양한 도메인의 검색어로 웹 검색 도구의 범용성을 테스트
        search_queries = [
            "2024년 AI 발전 동향에 대해 검색해주세요",     # AI 트렌드 검색
            "OpenAI의 최신 소식을 알려주세요",            # 특정 회사 뉴스 검색
            "LangGraph란 무엇인가요?"                    # 기술적 개념 검색
        ]
        
        for i, query in enumerate(search_queries, 1):
            print(f"\n{i}️⃣ 질의: {query}")
            print("-" * 40)
            
            # JSON-RPC 2.0 표준 형식으로 요청 구성
            # A2A 프로토콜에 맞는 메시지 구조 생성
            request_data = {
                "id": str(uuid.uuid4()),           # 요청 식별자
                "jsonrpc": "2.0",                  # JSON-RPC 버전
                "method": "message/send",          # A2A 메시지 전송 메서드
                "params": {
                    "message": {
                        "kind": "message",         # 메시지 타입
                        "messageId": str(uuid.uuid4()),  # 메시지 고유 ID
                        "parts": [
                            {
                                "kind": "text",    # 텍스트 파트
                                "text": query      # 실제 검색 쿼리
                            }
                        ],
                        "role": "user"             # 사용자 역할
                    }
                }
            }
            
            print("📤 요청 전송 중...")
            response = await client.post(
                "http://localhost:8080/",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            
            print(f"✅ 응답 상태: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    message = result["result"]
                    if "parts" in message:
                        for part in message["parts"]:
                            if "text" in part:
                                print(f"🤖 응답: {part['text']}")
                else:
                    print(f"📋 전체 응답: {json.dumps(result, indent=2, ensure_ascii=False)}")
            else:
                print(f"❌ 오류 응답: {response.text}")
            
            print("=" * 50)
            
        print("\n🎉 모든 테스트 완료!")
            
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_web_search())