#!/usr/bin/env python3
"""
HITL 시스템 통합 테스트
"""

import asyncio
import aiohttp
import json
import redis.asyncio as redis
import websockets
import uuid
import time
from datetime import datetime
from typing import Dict, Any


class HITLIntegrationTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.ws_url = "ws://localhost:8000/ws"
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.test_results = {}

    async def test_redis_connection(self) -> Dict[str, Any]:
        """Redis 연결 테스트"""
        print("🔍 Redis 연결 테스트...")
        try:
            r = redis.Redis(
                host=self.redis_host, port=self.redis_port, decode_responses=True
            )
            await r.ping()

            # Redis 정보 확인
            info = await r.info()
            version = info.get("redis_version", "unknown")
            connected_clients = info.get("connected_clients", 0)

            await r.close()

            result = {
                "status": "success",
                "version": version,
                "connected_clients": connected_clients,
                "message": "Redis 연결 성공",
            }
            print(
                f"✅ Redis 연결 성공 (버전: {version}, 클라이언트: {connected_clients})"
            )
            return result

        except Exception as e:
            result = {"status": "error", "error": str(e), "message": "Redis 연결 실패"}
            print(f"❌ Redis 연결 실패: {e}")
            return result

    async def test_hitl_server_health(self) -> Dict[str, Any]:
        """HITL 서버 헬스체크 테스트"""
        print("🔍 HITL 서버 헬스체크...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        result = {
                            "status": "success",
                            "health_data": data,
                            "response_time": response.headers.get(
                                "X-Response-Time", "N/A"
                            ),
                            "message": "HITL 서버 정상",
                        }
                        print(f"✅ HITL 서버 정상: {data}")
                        return result
                    else:
                        result = {
                            "status": "error",
                            "status_code": response.status,
                            "message": f"HITL 서버 응답 오류: {response.status}",
                        }
                        print(f"❌ HITL 서버 응답 오류: {response.status}")
                        return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "HITL 서버 연결 실패",
            }
            print(f"❌ HITL 서버 연결 실패: {e}")
            return result

    async def test_api_endpoints(self) -> Dict[str, Any]:
        """API 엔드포인트 테스트"""
        print("🔍 API 엔드포인트 테스트...")
        results = {}

        endpoints = [
            ("/", "루트 엔드포인트"),
            ("/health", "헬스체크"),
            ("/api/approvals/pending", "대기 중인 승인 요청"),
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for endpoint, description in endpoints:
                    try:
                        async with session.get(
                            f"{self.base_url}{endpoint}"
                        ) as response:
                            status = response.status
                            try:
                                data = await response.json()
                            except Exception:
                                data = await response.text()

                            results[endpoint] = {
                                "status": "success"
                                if status in [200, 404]
                                else "error",
                                "status_code": status,
                                "data": data,
                                "description": description,
                            }

                            if status == 200:
                                print(f"✅ {description} ({endpoint}): {status}")
                            else:
                                print(f"⚠️ {description} ({endpoint}): {status}")

                    except Exception as e:
                        results[endpoint] = {
                            "status": "error",
                            "error": str(e),
                            "description": description,
                        }
                        print(f"❌ {description} ({endpoint}): {e}")

            return {
                "status": "completed",
                "results": results,
                "message": f"{len(endpoints)}개 엔드포인트 테스트 완료",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "API 엔드포인트 테스트 실패",
            }

    async def test_websocket_connection(self) -> Dict[str, Any]:
        """WebSocket 연결 테스트"""
        print("🔍 WebSocket 연결 테스트...")
        try:
            async with websockets.connect(self.ws_url) as websocket:
                # 연결 직후 초기 데이터 수신 대기
                try:
                    initial_message = await asyncio.wait_for(
                        websocket.recv(), timeout=5.0
                    )
                    initial_data = json.loads(initial_message)

                    # Ping 테스트
                    await websocket.send("ping")
                    pong_response = await asyncio.wait_for(
                        websocket.recv(), timeout=5.0
                    )

                    result = {
                        "status": "success",
                        "initial_data": initial_data,
                        "ping_response": pong_response,
                        "message": "WebSocket 연결 및 통신 성공",
                    }
                    print(
                        f"✅ WebSocket 연결 성공, 초기 데이터: {len(initial_data.get('data', []))}개 승인 요청"
                    )
                    return result

                except asyncio.TimeoutError:
                    result = {
                        "status": "partial_success",
                        "message": "WebSocket 연결은 성공했지만 초기 데이터 수신 시간 초과",
                    }
                    print("⚠️ WebSocket 연결 성공, 하지만 초기 데이터 수신 시간 초과")
                    return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "WebSocket 연결 실패",
            }
            print(f"❌ WebSocket 연결 실패: {e}")
            return result

    async def test_approval_flow(self) -> Dict[str, Any]:
        """승인 플로우 테스트"""
        print("🔍 승인 플로우 테스트...")

        # Redis를 통해 직접 승인 요청 생성
        request_id = str(uuid.uuid4())
        test_request = {
            "id": request_id,
            "agent_id": "test_agent",
            "approval_type": "TOOL_EXECUTION",
            "title": "테스트 승인 요청",
            "description": "통합 테스트를 위한 승인 요청",
            "details": {"tool_name": "test_tool", "parameters": {"query": "test"}},
            "status": "PENDING",
            "created_at": datetime.now().isoformat(),
            "expires_at": None,
            "decided_by": None,
            "decided_at": None,
            "decision": None,
            "reason": None,
        }

        try:
            # Redis에 테스트 요청 저장
            r = redis.Redis(
                host=self.redis_host, port=self.redis_port, decode_responses=True
            )
            await r.hset(f"approval_request:{request_id}", mapping=test_request)
            await r.sadd("pending_approval_requests", request_id)

            # API를 통해 승인 요청 조회
            async with aiohttp.ClientSession() as session:
                # 대기 중인 승인 요청 목록 조회
                async with session.get(
                    f"{self.base_url}/api/approvals/pending"
                ) as response:
                    if response.status == 200:
                        pending_requests = await response.json()
                        found_request = any(
                            req.get("id") == request_id for req in pending_requests
                        )

                        if found_request:
                            print(
                                f"✅ 승인 요청이 정상적으로 저장되고 조회됨: {request_id}"
                            )

                            # 승인 처리 테스트
                            approval_data = {
                                "request_id": request_id,
                                "decision": "approved",
                                "decided_by": "test_user",
                                "reason": "통합 테스트 승인",
                            }

                            async with session.post(
                                f"{self.base_url}/api/approvals/{request_id}/approve",
                                json=approval_data,
                            ) as approve_response:
                                if approve_response.status == 200:
                                    approve_result = await approve_response.json()
                                    print(f"✅ 승인 처리 성공: {approve_result}")

                                    result = {
                                        "status": "success",
                                        "request_id": request_id,
                                        "found_in_pending": True,
                                        "approval_success": True,
                                        "message": "승인 플로우 테스트 성공",
                                    }
                                else:
                                    error_text = await approve_response.text()
                                    print(
                                        f"❌ 승인 처리 실패: {approve_response.status} - {error_text}"
                                    )
                                    result = {
                                        "status": "partial_success",
                                        "request_id": request_id,
                                        "found_in_pending": True,
                                        "approval_success": False,
                                        "error": error_text,
                                        "message": "승인 요청은 저장되었지만 승인 처리 실패",
                                    }
                        else:
                            print(
                                f"❌ 승인 요청이 목록에서 발견되지 않음: {request_id}"
                            )
                            result = {
                                "status": "error",
                                "request_id": request_id,
                                "found_in_pending": False,
                                "message": "승인 요청이 저장되었지만 API에서 조회되지 않음",
                            }
                    else:
                        error_text = await response.text()
                        print(
                            f"❌ 대기 중인 승인 요청 조회 실패: {response.status} - {error_text}"
                        )
                        result = {
                            "status": "error",
                            "error": error_text,
                            "message": "대기 중인 승인 요청 조회 실패",
                        }

            # 정리
            await r.delete(f"approval_request:{request_id}")
            await r.srem("pending_approval_requests", request_id)
            await r.close()

            return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "승인 플로우 테스트 실패",
            }
            print(f"❌ 승인 플로우 테스트 실패: {e}")
            return result

    async def test_concurrent_requests(self) -> Dict[str, Any]:
        """동시 요청 처리 테스트"""
        print("🔍 동시 요청 처리 테스트...")

        async def make_request(session, endpoint):
            try:
                start_time = time.time()
                async with session.get(f"{self.base_url}{endpoint}") as response:
                    end_time = time.time()
                    return {
                        "status": response.status,
                        "response_time": end_time - start_time,
                        "success": response.status == 200,
                    }
            except Exception as e:
                return {"status": "error", "error": str(e), "success": False}

        try:
            async with aiohttp.ClientSession() as session:
                # 10개의 동시 요청
                tasks = [make_request(session, "/health") for _ in range(10)]
                results = await asyncio.gather(*tasks)

                successful_requests = sum(1 for r in results if r.get("success"))
                avg_response_time = sum(
                    r.get("response_time", 0) for r in results
                ) / len(results)

                result = {
                    "status": "success",
                    "total_requests": len(results),
                    "successful_requests": successful_requests,
                    "success_rate": successful_requests / len(results) * 100,
                    "average_response_time": avg_response_time,
                    "results": results,
                    "message": f"동시 요청 테스트 완료: {successful_requests}/{len(results)} 성공",
                }

                print(
                    f"✅ 동시 요청 테스트: {successful_requests}/{len(results)} 성공, 평균 응답시간: {avg_response_time:.3f}초"
                )
                return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "동시 요청 테스트 실패",
            }
            print(f"❌ 동시 요청 테스트 실패: {e}")
            return result

    async def test_redis_data_persistence(self) -> Dict[str, Any]:
        """Redis 데이터 지속성 테스트"""
        print("🔍 Redis 데이터 지속성 테스트...")

        try:
            r = redis.Redis(
                host=self.redis_host, port=self.redis_port, decode_responses=True
            )

            # 테스트 데이터 저장
            test_key = f"test_persistence_{uuid.uuid4()}"
            test_data = {"timestamp": datetime.now().isoformat(), "test": "data"}

            await r.hset(test_key, mapping=test_data)

            # 데이터 조회
            retrieved_data = await r.hgetall(test_key)

            # 데이터 일치 확인
            data_matches = all(
                retrieved_data.get(k) == str(v) for k, v in test_data.items()
            )

            # 정리
            await r.delete(test_key)
            await r.close()

            if data_matches:
                result = {
                    "status": "success",
                    "test_key": test_key,
                    "data_matches": True,
                    "message": "Redis 데이터 지속성 테스트 성공",
                }
                print("✅ Redis 데이터 지속성 테스트 성공")
            else:
                result = {
                    "status": "error",
                    "test_key": test_key,
                    "data_matches": False,
                    "expected": test_data,
                    "retrieved": retrieved_data,
                    "message": "데이터 불일치",
                }
                print("❌ Redis 데이터 불일치")

            return result

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e),
                "message": "Redis 데이터 지속성 테스트 실패",
            }
            print(f"❌ Redis 데이터 지속성 테스트 실패: {e}")
            return result

    async def run_all_tests(self) -> Dict[str, Any]:
        """전체 테스트 실행"""
        print("🚀 HITL 시스템 통합 테스트 시작")
        print("=" * 60)

        test_suite = [
            ("redis_connection", self.test_redis_connection),
            ("hitl_server_health", self.test_hitl_server_health),
            ("api_endpoints", self.test_api_endpoints),
            ("websocket_connection", self.test_websocket_connection),
            ("approval_flow", self.test_approval_flow),
            ("concurrent_requests", self.test_concurrent_requests),
            ("redis_data_persistence", self.test_redis_data_persistence),
        ]

        test_results = {}
        start_time = time.time()

        for test_name, test_func in test_suite:
            print(f"\n📋 테스트: {test_name}")
            print("-" * 40)
            test_results[test_name] = await test_func()

        end_time = time.time()
        total_time = end_time - start_time

        # 결과 요약
        successful_tests = sum(
            1 for result in test_results.values() if result.get("status") == "success"
        )
        total_tests = len(test_suite)

        print("\n" + "=" * 60)
        print("📊 테스트 결과 요약")
        print("=" * 60)
        print(f"총 테스트: {total_tests}")
        print(f"성공: {successful_tests}")
        print(f"실패: {total_tests - successful_tests}")
        print(f"성공률: {successful_tests / total_tests * 100:.1f}%")
        print(f"총 소요시간: {total_time:.2f}초")

        # 개별 테스트 결과
        for test_name, result in test_results.items():
            status_icon = "✅" if result.get("status") == "success" else "❌"
            print(f"{status_icon} {test_name}: {result.get('message', 'No message')}")

        return {
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": total_tests - successful_tests,
                "success_rate": successful_tests / total_tests * 100,
                "total_time": total_time,
            },
            "results": test_results,
        }


async def main():
    tester = HITLIntegrationTest()
    results = await tester.run_all_tests()

    # 결과를 JSON 파일로 저장
    import json

    with open("test_hitl_integration_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print("\n💾 테스트 결과가 test_hitl_integration_results.json에 저장되었습니다.")

    return results


if __name__ == "__main__":
    asyncio.run(main())
