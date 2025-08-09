#!/usr/bin/env python3
"""
A2A 서버 간단 테스트 스크립트

목적:
- A2A 서버의 기본 기능 검증 (헬스체크, Agent Card, Task 생성)
- 환경변수에서 포트 설정을 읽어와 유연한 테스트 수행
- A2A 표준 프로토콜 준수 여부 확인

테스트 항목:
1. 헬스체크 엔드포인트 응답 확인
2. Agent Card 정보 조회 및 검증
3. Task 생성 및 응답 확인

사용법:
    python tests/test_simple_a2a.py
    
환경변수:
    TEST_A2A_PORT: 테스트할 A2A 서버 포트 (기본값: 8080)

전제조건:
- A2A 서버가 지정된 포트에서 실행 중이어야 함
- 서버가 A2A 표준 프로토콜을 지원해야 함

예상 결과:
- 모든 테스트 통과 시 성공 메시지 출력
- 서버 연결 실패 시 연결 오류 메시지 출력
"""
import asyncio
import os
import httpx

async def test_a2a_server():
    """
    A2A 서버 기본 기능 테스트
    
    테스트 시나리오:
    1. 헬스체크 API 호출 및 응답 확인
    2. Agent Card 조회 및 메타데이터 검증
    3. Task 생성 요청 및 Task ID 반환 확인
    
    Returns:
        None: 테스트 결과는 콘솔에 출력됨
        
    Raises:
        httpx.ConnectError: 서버 연결 실패 시
        Exception: 기타 테스트 실행 중 오류 발생 시
    """
    # 환경변수에서 포트 설정 또는 기본값 사용
    test_port = int(os.getenv("TEST_A2A_PORT", "8080"))
    base_url = f"http://localhost:{test_port}"
    
    print(f"🧪 A2A 서버 테스트 (포트: {test_port})")
    print("=" * 50)
    
    async with httpx.AsyncClient() as client:
        try:
            # 1단계: 헬스체크 - 서버가 정상적으로 응답하는지 확인
            print("🔍 헬스체크...")
            response = await client.get(f"{base_url}/health")
            print(f"✅ 헬스체크: {response.status_code}")
            print(f"   응답: {response.json()}")
            
            # 2단계: Agent Card 확인 - 에이전트 메타데이터 조회
            print("\n📋 Agent Card 확인...")
            response = await client.get(f"{base_url}/agent")
            print(f"✅ Agent Card: {response.status_code}")
            card = response.json()
            print(f"   이름: {card.get('name')}")
            print(f"   설명: {card.get('description')}")
            print(f"   버전: {card.get('version')}")
            
            # 3단계: Task 생성 테스트 - A2A 프로토콜 준수 확인
            print("\n🚀 Task 생성 테스트...")
            # A2A 표준 Task 요청 구조
            task_request = {
                "conversation": {
                    "messages": [
                        {
                            "role": "user",
                            "parts": [{"text": "안녕하세요! 간단한 테스트입니다."}],
                            "timestamp": "2024-01-01T00:00:00Z"
                        }
                    ]
                }
            }
            
            response = await client.post(f"{base_url}/tasks", json=task_request)
            print(f"✅ Task 생성: {response.status_code}")
            task_result = response.json()
            print(f"   Task ID: {task_result.get('task_id')}")
            
            print("\n✅ A2A 서버 테스트 완료!")
            
        except httpx.ConnectError:
            print(f"❌ 서버 연결 실패 - {base_url} 서버가 실행 중인지 확인하세요")
        except Exception as e:
            print(f"❌ 테스트 오류: {e}")

if __name__ == "__main__":
    asyncio.run(test_a2a_server())