#!/usr/bin/env python3
"""
종합적인 HITL 시스템 통합 테스트
"""

import asyncio
import aiohttp
import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any


class ComprehensiveHITLTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.hitl_base_url = "http://localhost:8000/hitl"
        self.redis_host = "localhost"
        self.redis_port = 6379

    async def test_basic_connectivity(self) -> Dict[str, Any]:
        """기본 연결성 테스트"""
        print("🔍 기본 연결성 테스트...")
        results = {}

        try:
            async with aiohttp.ClientSession() as session:
                # 메인 서버 테스트
                async with session.get(f"{self.base_url}/") as response:
                    main_server = {
                        "status": "success" if response.status == 200 else "error",
                        "status_code": response.status,
                        "data": await response.json()
                        if response.status == 200
                        else await response.text(),
                    }
                    results["main_server"] = main_server

                # 헬스체크 테스트
                async with session.get(f"{self.base_url}/health") as response:
                    health_check = {
                        "status": "success" if response.status == 200 else "error",
                        "status_code": response.status,
                        "data": await response.json()
                        if response.status == 200
                        else await response.text(),
                    }
                    results["health_check"] = health_check

                # HITL 헬스체크 테스트
                async with session.get(f"{self.hitl_base_url}/health") as response:
                    hitl_health = {
                        "status": "success" if response.status == 200 else "error",
                        "status_code": response.status,
                        "data": await response.json()
                        if response.status == 200
                        else await response.text(),
                    }
                    results["hitl_health"] = hitl_health

            # Redis 연결 테스트
            try:
                import redis.asyncio as redis

                r = redis.Redis(
                    host=self.redis_host, port=self.redis_port, decode_responses=True
                )
                await r.ping()
                redis_result = {"status": "success", "message": "Redis 연결 성공"}
                await r.close()
            except Exception as e:
                redis_result = {"status": "error", "error": str(e)}

            results["redis"] = redis_result

            # 성공한 테스트 개수 계산
            successful_tests = sum(
                1 for test in results.values() if test.get("status") == "success"
            )
            total_tests = len(results)

            print(f"✅ 기본 연결성 테스트: {successful_tests}/{total_tests} 성공")

            return {
                "status": "completed",
                "successful_tests": successful_tests,
                "total_tests": total_tests,
                "results": results,
            }

        except Exception as e:
            print(f"❌ 기본 연결성 테스트 실패: {e}")
            return {"status": "error", "error": str(e)}

    async def test_a2a_protocol_compatibility(self) -> Dict[str, Any]:
        """A2A 프로토콜 호환성 테스트"""
        print("🔍 A2A 프로토콜 호환성 테스트...")

        try:
            # A2A 스타일 연구 요청 테스트
            research_request = {
                "query": "테스트용 간단한 질문",
                "task_id": f"test_task_{uuid.uuid4()}",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/research", json=research_request
                ) as response:
                    status_code = response.status
                    response_data = (
                        await response.json()
                        if response.status == 200
                        else await response.text()
                    )

                    if status_code == 200:
                        # A2A 표준 응답 형식 확인
                        expected_fields = ["task_id", "status", "messages", "query"]
                        has_required_fields = all(
                            field in response_data for field in expected_fields
                        )

                        result = {
                            "status": "success"
                            if has_required_fields
                            else "partial_success",
                            "status_code": status_code,
                            "response_data": response_data,
                            "has_required_fields": has_required_fields,
                            "missing_fields": [
                                field
                                for field in expected_fields
                                if field not in response_data
                            ],
                            "message": "A2A 프로토콜 호환성 확인됨"
                            if has_required_fields
                            else "일부 필드 누락",
                        }

                        print(
                            f"✅ A2A 연구 API 테스트 성공: {response_data.get('task_id')}"
                        )
                    else:
                        result = {
                            "status": "error",
                            "status_code": status_code,
                            "response_data": response_data,
                            "message": f"A2A API 호출 실패: {status_code}",
                        }
                        print(f"❌ A2A 연구 API 테스트 실패: {status_code}")

            return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "A2A 프로토콜 테스트 실패",
            }
            print(f"❌ A2A 프로토콜 테스트 실패: {e}")
            return result

    async def test_websocket_realtime_communication(self) -> Dict[str, Any]:
        """WebSocket 실시간 통신 테스트"""
        print("🔍 WebSocket 실시간 통신 테스트...")

        try:
            import websockets

            async with websockets.connect("ws://localhost:8000/ws") as websocket:
                # 연결 확인

                # 초기 메시지 수신 대기
                try:
                    initial_message = await asyncio.wait_for(
                        websocket.recv(), timeout=3.0
                    )
                    initial_data = json.loads(initial_message)
                    received_initial = True
                except asyncio.TimeoutError:
                    initial_data = None
                    received_initial = False

                # 핑-퐁 테스트
                ping_time = time.time()
                await websocket.send("ping")

                try:
                    pong_response = await asyncio.wait_for(
                        websocket.recv(), timeout=3.0
                    )
                    pong_time = time.time()
                    ping_latency = pong_time - ping_time
                    ping_success = True
                except asyncio.TimeoutError:
                    pong_response = None
                    ping_latency = None
                    ping_success = False

                result = {
                    "status": "success",
                    "connection_established": True,
                    "received_initial_data": received_initial,
                    "initial_data": initial_data,
                    "ping_success": ping_success,
                    "pong_response": pong_response,
                    "ping_latency": ping_latency,
                    "message": "WebSocket 통신 성공",
                }

                print(
                    f"✅ WebSocket 통신 성공 (응답시간: {ping_latency:.3f}초)"
                    if ping_success
                    else "⚠️ WebSocket 연결은 성공했지만 핑 응답 없음"
                )
                return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "WebSocket 통신 실패",
            }
            print(f"❌ WebSocket 통신 실패: {e}")
            return result

    async def test_system_performance(self) -> Dict[str, Any]:
        """시스템 성능 테스트"""
        print("🔍 시스템 성능 테스트...")

        async def measure_endpoint_performance(session, url, requests_count=5):
            times = []
            successes = 0

            for _ in range(requests_count):
                start_time = time.time()
                try:
                    async with session.get(url) as response:
                        end_time = time.time()
                        times.append(end_time - start_time)
                        if response.status == 200:
                            successes += 1
                except Exception:
                    end_time = time.time()
                    times.append(end_time - start_time)

            return {
                "avg_response_time": sum(times) / len(times),
                "min_response_time": min(times),
                "max_response_time": max(times),
                "success_rate": successes / requests_count * 100,
                "total_requests": requests_count,
            }

        try:
            async with aiohttp.ClientSession() as session:
                # 메인 서버 성능 테스트
                main_performance = await measure_endpoint_performance(
                    session, f"{self.base_url}/health"
                )

                # HITL 서버 성능 테스트
                hitl_performance = await measure_endpoint_performance(
                    session, f"{self.hitl_base_url}/health"
                )

                # 동시 요청 테스트
                concurrent_start = time.time()
                tasks = [session.get(f"{self.base_url}/health") for _ in range(10)]

                responses = await asyncio.gather(*tasks, return_exceptions=True)
                concurrent_end = time.time()

                successful_concurrent = sum(
                    1
                    for r in responses
                    if not isinstance(r, Exception) and r.status == 200
                )

                result = {
                    "status": "success",
                    "main_server_performance": main_performance,
                    "hitl_server_performance": hitl_performance,
                    "concurrent_test": {
                        "total_time": concurrent_end - concurrent_start,
                        "successful_requests": successful_concurrent,
                        "total_requests": len(tasks),
                        "success_rate": successful_concurrent / len(tasks) * 100,
                    },
                    "message": "시스템 성능 테스트 완료",
                }

                print(
                    f"✅ 성능 테스트 완료 - 평균 응답시간: {main_performance['avg_response_time']:.3f}초"
                )
                return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "시스템 성능 테스트 실패",
            }
            print(f"❌ 시스템 성능 테스트 실패: {e}")
            return result

    async def test_error_handling(self) -> Dict[str, Any]:
        """에러 처리 테스트"""
        print("🔍 에러 처리 테스트...")

        error_tests = [
            {
                "name": "존재하지 않는 엔드포인트",
                "url": f"{self.base_url}/nonexistent",
                "expected_status": 404,
            },
            {
                "name": "잘못된 JSON 데이터",
                "url": f"{self.base_url}/api/research",
                "method": "POST",
                "data": "invalid json",
                "expected_status": 422,
            },
            {
                "name": "빈 연구 요청",
                "url": f"{self.base_url}/api/research",
                "method": "POST",
                "json": {},
                "expected_status": 422,
            },
        ]

        results = {}

        try:
            async with aiohttp.ClientSession() as session:
                for test in error_tests:
                    try:
                        if test.get("method") == "POST":
                            if "json" in test:
                                async with session.post(
                                    test["url"], json=test["json"]
                                ) as response:
                                    status = response.status
                                    response_data = await response.text()
                            else:
                                async with session.post(
                                    test["url"], data=test["data"]
                                ) as response:
                                    status = response.status
                                    response_data = await response.text()
                        else:
                            async with session.get(test["url"]) as response:
                                status = response.status
                                response_data = await response.text()

                        test_result = {
                            "status": "success"
                            if status == test["expected_status"]
                            else "unexpected",
                            "actual_status": status,
                            "expected_status": test["expected_status"],
                            "response_data": response_data[:200]
                            if response_data
                            else None,
                        }

                        results[test["name"]] = test_result

                        if status == test["expected_status"]:
                            print(f"✅ {test['name']}: 예상된 에러 응답 ({status})")
                        else:
                            print(
                                f"⚠️ {test['name']}: 예상과 다른 응답 (예상: {test['expected_status']}, 실제: {status})"
                            )

                    except Exception as e:
                        results[test["name"]] = {"status": "error", "error": str(e)}
                        print(f"❌ {test['name']}: 테스트 실행 오류 - {e}")

            successful_tests = sum(
                1 for result in results.values() if result.get("status") == "success"
            )
            total_tests = len(error_tests)

            return {
                "status": "completed",
                "successful_tests": successful_tests,
                "total_tests": total_tests,
                "results": results,
                "message": f"에러 처리 테스트 완료: {successful_tests}/{total_tests} 성공",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "에러 처리 테스트 실패",
            }

    async def run_comprehensive_test(self) -> Dict[str, Any]:
        """종합 테스트 실행"""
        print("🚀 HITL 시스템 종합 통합 테스트 시작")
        print("=" * 80)

        test_suite = [
            ("기본 연결성", self.test_basic_connectivity),
            ("A2A 프로토콜 호환성", self.test_a2a_protocol_compatibility),
            ("WebSocket 실시간 통신", self.test_websocket_realtime_communication),
            ("시스템 성능", self.test_system_performance),
            ("에러 처리", self.test_error_handling),
        ]

        test_results = {}
        start_time = time.time()

        for test_name, test_func in test_suite:
            print(f"\n📋 테스트: {test_name}")
            print("-" * 50)
            test_results[test_name] = await test_func()

        end_time = time.time()
        total_time = end_time - start_time

        # 결과 요약
        successful_tests = sum(
            1
            for result in test_results.values()
            if result.get("status") in ["success", "completed"]
        )
        total_tests = len(test_suite)

        print("\n" + "=" * 80)
        print("📊 종합 테스트 결과 요약")
        print("=" * 80)
        print(f"총 테스트 카테고리: {total_tests}")
        print(f"성공한 카테고리: {successful_tests}")
        print(f"실패한 카테고리: {total_tests - successful_tests}")
        print(f"성공률: {successful_tests / total_tests * 100:.1f}%")
        print(f"총 소요시간: {total_time:.2f}초")

        # 개별 테스트 결과
        for test_name, result in test_results.items():
            status_icon = (
                "✅" if result.get("status") in ["success", "completed"] else "❌"
            )
            print(f"{status_icon} {test_name}: {result.get('message', 'No message')}")

        print("\n" + "=" * 80)
        print("🔧 시스템 상태 요약")
        print("=" * 80)

        # 기본 연결성 결과 요약
        if "기본 연결성" in test_results:
            connectivity = test_results["기본 연결성"]
            if connectivity.get("status") == "completed":
                conn_results = connectivity.get("results", {})
                print(
                    f"• 메인 서버: {'✅' if conn_results.get('main_server', {}).get('status') == 'success' else '❌'}"
                )
                print(
                    f"• 헬스체크: {'✅' if conn_results.get('health_check', {}).get('status') == 'success' else '❌'}"
                )
                print(
                    f"• HITL 헬스체크: {'✅' if conn_results.get('hitl_health', {}).get('status') == 'success' else '❌'}"
                )
                print(
                    f"• Redis 연결: {'✅' if conn_results.get('redis', {}).get('status') == 'success' else '❌'}"
                )

        # A2A 호환성 결과 요약
        if "A2A 프로토콜 호환성" in test_results:
            a2a_result = test_results["A2A 프로토콜 호환성"]
            print(
                f"• A2A 프로토콜: {'✅' if a2a_result.get('status') == 'success' else '❌'}"
            )

        # WebSocket 결과 요약
        if "WebSocket 실시간 통신" in test_results:
            ws_result = test_results["WebSocket 실시간 통신"]
            print(
                f"• WebSocket 통신: {'✅' if ws_result.get('status') == 'success' else '❌'}"
            )

        return {
            "summary": {
                "total_test_categories": total_tests,
                "successful_categories": successful_tests,
                "failed_categories": total_tests - successful_tests,
                "success_rate": successful_tests / total_tests * 100,
                "total_time": total_time,
            },
            "test_results": test_results,
            "timestamp": datetime.now().isoformat(),
        }


async def main():
    tester = ComprehensiveHITLTest()
    results = await tester.run_comprehensive_test()

    # 결과를 JSON 파일로 저장
    with open(
        "comprehensive_hitl_test_results.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print("\n💾 테스트 결과가 comprehensive_hitl_test_results.json에 저장되었습니다.")

    return results


if __name__ == "__main__":
    asyncio.run(main())
