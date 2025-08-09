#!/usr/bin/env python
"""
SafeEventQueue 테스트

이 테스트는 A2A 서버의 SafeEventQueue 구현이 "queue is closed" 오류를 해결했는지 검증합니다.

실행 방법:
    python tests/test_safeeventqueue.py

전제 조건:
    - A2A 서버가 localhost:8090에서 실행 중이어야 함
    - MCP 서버들이 실행 중이어야 함 (검색 기능 테스트를 위해)

테스트 항목:
    1. 헬스체크 API 연결 테스트
    2. JSON-RPC 스트리밍 호출 테스트
    3. "queue is closed" 오류 발생 여부 검사
    4. 정상적인 응답 수신 확인

디버깅:
    - 스트림 이벤트 개수 카운팅
    - 에러 메시지 패턴 매칭
    - 타임아웃: 30초

예상 결과:
    - ✅ Queue is closed 에러 없음: SafeEventQueue가 정상 작동
    - ✅ 응답 수신 성공: 정상적인 스트리밍 동작
"""

import asyncio
import httpx
import json
import sys


async def test_safeeventqueue():
    """SafeEventQueue 적용 후 테스트"""

    print("🧪 SafeEventQueue 테스트 시작...")
    print("=" * 60)

    # 1. 헬스 체크
    print("\n1️⃣ 헬스 체크...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8090/health")
            if response.status_code == 200:
                print("   ✅ 서버 상태: 정상")
            else:
                print(f"   ❌ 서버 상태: {response.status_code}")
                return
        except Exception as e:
            print(f"   ❌ 연결 실패: {e}")
            return

    # 2. 매우 간단한 JSON-RPC 호출
    print("\n2️⃣ JSON-RPC 호출 (매우 간단한 쿼리)...")
    query = "안녕"  # 최대한 간단하게

    request_data = {
        "jsonrpc": "2.0",
        "method": "message/stream",
        "params": {
            "message": {
                "messageId": "test-safe-queue-1",
                "role": "user",
                "parts": [{"text": query}],
            }
        },
        "id": 1,
    }

    print(f"   쿼리: {query}")
    print("   응답 대기중...")

    has_response = False
    error_count = 0
    event_count = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream(
                "POST",
                "http://localhost:8090/",
                json=request_data,
                headers={
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
            ) as response:
                print(f"   상태 코드: {response.status_code}")

                if response.status_code == 200:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            event_count += 1
                            data = line[6:]

                            # 처음 몇 개의 이벤트만 출력
                            if event_count <= 5:
                                print(f"   📥 이벤트 {event_count}: {data[:100]}...")

                            # 에러 체크
                            if (
                                "error" in data.lower()
                                and "queue is closed" in data.lower()
                            ):
                                error_count += 1
                                print("   ⚠️ Queue is closed 에러 감지!")

                            # 응답 확인
                            try:
                                event = json.loads(data)
                                if "result" in event:
                                    has_response = True
                            except Exception:
                                pass

                        elif line == "data: [DONE]":
                            print(f"\n   ✅ 스트림 종료 (총 {event_count}개 이벤트)")
                            break
                else:
                    print(f"   ❌ 응답 실패: {response.status_code}")

        except Exception as e:
            print(f"   ❌ 오류 발생: {e}")

    # 3. 결과 분석
    print("\n3️⃣ 결과 분석")
    print("=" * 60)

    if error_count > 0:
        print(
            f"   ❌ Queue is closed 에러 {error_count}번 발생 - SafeEventQueue가 제대로 작동하지 않음"
        )
    else:
        print("   ✅ Queue is closed 에러 없음 - SafeEventQueue가 정상 작동")

    if has_response:
        print("   ✅ 응답 수신 성공")
    else:
        print("   ❌ 응답 수신 실패")

    if event_count > 0:
        print(f"   ℹ️ 총 {event_count}개의 이벤트 수신")

    print("\n테스트 완료!")
    return error_count == 0


if __name__ == "__main__":
    success = asyncio.run(test_safeeventqueue())
    sys.exit(0 if success else 1)
