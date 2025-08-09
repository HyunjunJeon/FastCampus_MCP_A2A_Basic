#!/usr/bin/env python3
"""
A2A 서버 직접 메시지 처리 테스트 스크립트

이 스크립트는 A2A 서버의 직접 메시지 처리 기능을 테스트합니다.
스트리밍 대신 직접적인 메시지 송수신을 테스트합니다.

실행 방법:
    python tests/debug_message_test.py

전제 조건:
    - A2A 서버가 localhost:8080에서 실행 중
    - MCP 서버들이 정상 동작 중
    - OPENAI_API_KEY 환경변수 설정

테스트 내용:
    - JSON-RPC 2.0 형식의 message/send 메서드 호출
    - AI 기술 동향에 대한 질의
    - 동기식 응답 수신 및 검증

디버깅:
    - 전송 요청 JSON 구조 상세 출력
    - HTTP 상태 코드 확인
    - 응답 내용 파싱 및 표시
    - 에러 상황별 상세한 메시지 출력

응답 형식:
    - JSON-RPC 2.0 표준 준수
    - result 필드에 AI 응답 포함
    - 타임아웃: 60초
"""
import asyncio
import json
import httpx
import uuid

async def test_direct_message():
    """A2A 서버 직접 메시지 처리 테스트"""
    client = httpx.AsyncClient(timeout=60.0)

    try:
        print("🔍 A2A 직접 메시지 처리 테스트")
        print("=" * 50)

        request_data = {
            "id": str(uuid.uuid4()),
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "messageId": str(uuid.uuid4()),
                    "parts": [
                        {
                            "kind": "text",
                            "text": "최신 AI 기술 동향에 대해 알려주세요."
                        }
                    ],
                    "role": "user"
                }
            }
        }

        print("📤 전송할 요청:")
        print(json.dumps(request_data, indent=2))
        print("-" * 50)

        response = await client.post(
            "http://localhost:8080/direct",
            json=request_data
        )
        response.raise_for_status()
        print(f"✅ 응답 상태: {response.status_code}")
        print("📥 응답 내용:")
        print(json.dumps(response.json(), indent=2))

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP 오류: {e.response.status_code}")
        print(f"   응답: {e.response.text}")
    except httpx.RequestError as e:
        print(f"❌ 오류: {e}")
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_direct_message())