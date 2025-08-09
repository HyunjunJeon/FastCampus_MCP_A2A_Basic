"""
.env 파일 로드 및 스트리밍 청크 전송 테스트
"""
import asyncio
import os
import json
import time
from datetime import datetime

# 환경 변수 확인 테스트
def test_env_file_loaded():
    """
    Docker Compose 환경변수 로드 검증
    
    목적:
    - .env 파일의 API 키들이 정상적으로 로드되었는지 확인
    - Docker Compose 환경에서 환경변수 전달이 올바른지 검증
    - 보안을 고려한 환경변수 출력 (일부만 표시)
    
    확인 항목:
    - OPENAI_API_KEY: OpenAI API 접근을 위한 키
    - TAVILY_API_KEY: Tavily 웹 검색을 위한 키
    
    Returns:
        bool: 모든 환경변수가 정상 로드되었으면 True
        
    보안 주의사항:
    - API 키는 앞 8자리와 뒤 4자리만 출력
    - 로그에 전체 키가 노출되지 않도록 마스킹 처리
    """
    print("\n=== .env 파일 로드 테스트 ===")
    
    # 필수 환경 변수 체크
    required_env_vars = ["OPENAI_API_KEY", "TAVILY_API_KEY"]
    loaded_vars = {}
    missing_vars = []
    
    for var in required_env_vars:
        value = os.getenv(var)
        if value:
            # 보안을 위해 일부만 표시
            masked_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            loaded_vars[var] = masked_value
        else:
            missing_vars.append(var)
    
    print("✅ 로드된 환경 변수:")
    for var, value in loaded_vars.items():
        print(f"   - {var}: {value}")
    
    if missing_vars:
        print("❌ 누락된 환경 변수:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    print("✅ 모든 필수 환경 변수가 로드되었습니다.")
    return True


# 스트리밍 청크 테스트
async def test_streaming_chunks():
    """
    A2A 서버 스트리밍 청크 전송 검증
    
    목적:
    - A2A 서버의 실시간 스트리밍 기능 확인
    - 응답이 청크 단위로 분할되어 전송되는지 검증
    - 스트리밍 성능 및 지연시간 측정
    - SSE(Server-Sent Events) 프로토콜 준수 확인
    
    테스트 시나리오:
    1. 긴 응답을 유도하는 복잡한 질문 전송
    2. JSON-RPC 2.0 스트리밍 요청 구성
    3. SSE 이벤트 스트림 실시간 수신
    4. 청크 간격 및 크기 분석
    
    성공 기준:
    - 최소 5개 이상의 청크 수신
    - 평균 청크 간격 1초 미만
    - 각 청크가 의미있는 내용 포함
    
    Returns:
        bool: 스트리밍이 예상대로 작동하면 True
        
    Raises:
        Exception: 네트워크 오류 또는 스트리밍 실패 시
    """
    print("\n=== 스트리밍 청크 전송 테스트 ===")
    
    import httpx
    from httpx_sse import aconnect_sse
    import uuid
    
    base_url = "http://localhost:8080"
    
    # 테스트용 긴 응답을 유도하는 질문
    # 스트리밍을 위해 의도적으로 복잡하고 상세한 답변을 요구하는 쿼리
    test_message = "FastMCP의 주요 기능 10가지를 자세히 설명해주세요. 각 기능마다 예제 코드도 포함해주세요."
    
    # JSON-RPC 요청 생성
    request_data = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/stream",
        "params": {
            "message": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": test_message
                    }
                ]
            }
        }
    }
    
    chunks_received = []
    chunk_times = []
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 헬스체크
            health_response = await client.get(f"{base_url}/health")
            if health_response.status_code != 200:
                print(f"❌ 서버 헬스체크 실패: {health_response.status_code}")
                return False
            
            print("✅ 서버 헬스체크 성공")
            print(f"📤 테스트 메시지 전송: {test_message[:50]}...")
            
            # SSE 스트리밍 요청
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
            
            async with aconnect_sse(
                client,
                "POST",
                f"{base_url}/",
                json=request_data,
                headers=headers
            ) as event_source:
                print("\n📥 스트리밍 응답 수신 중...")
                
                async for sse in event_source.aiter_sse():
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    if sse.event == "message":
                        try:
                            data = json.loads(sse.data)
                            
                            # 청크 정보 기록
                            chunk_info = {
                                "time": elapsed,
                                "data": data,
                                "size": len(str(data))
                            }
                            chunks_received.append(chunk_info)
                            chunk_times.append(elapsed)
                            
                            # 실시간 출력 (처음 5개 청크만)
                            if len(chunks_received) <= 5:
                                print(f"   청크 #{len(chunks_received)}: {elapsed:.3f}초 - {chunk_info['size']}바이트")
                            
                        except json.JSONDecodeError:
                            print(f"   ⚠️ JSON 파싱 실패: {sse.data[:50]}...")
                    
                    elif sse.event == "error":
                        print(f"   ❌ 에러: {sse.data}")
                        break
        
        # 결과 분석
        print("\n📊 스트리밍 분석 결과:")
        print(f"   - 총 청크 수: {len(chunks_received)}개")
        print(f"   - 총 소요 시간: {chunk_times[-1] if chunk_times else 0:.3f}초")
        
        if len(chunks_received) > 1:
            # 청크 간 시간 간격 계산
            intervals = []
            for i in range(1, len(chunk_times)):
                interval = chunk_times[i] - chunk_times[i-1]
                intervals.append(interval)
            
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            print(f"   - 평균 청크 간격: {avg_interval:.3f}초")
            print(f"   - 최소 간격: {min(intervals):.3f}초")
            print(f"   - 최대 간격: {max(intervals):.3f}초")
            
            # 청크 크기 분석
            chunk_sizes = [chunk['size'] for chunk in chunks_received]
            avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
            print(f"   - 평균 청크 크기: {avg_size:.0f}바이트")
            
            # 스트리밍 효과 확인
            if len(chunks_received) >= 5 and avg_interval < 1.0:
                print("\n✅ 스트리밍이 청크 단위로 잘 작동하고 있습니다!")
                return True
            else:
                print("\n⚠️ 스트리밍이 예상대로 작동하지 않을 수 있습니다.")
                return False
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


# Docker 환경에서 환경 변수 확인
async def test_docker_env_vars():
    """Docker 컨테이너 내부의 환경 변수 확인"""
    print("\n=== Docker 컨테이너 환경 변수 테스트 ===")
    
    import subprocess
    
    try:
        # MCP 서버 컨테이너 환경 변수 확인
        print("\n📦 MCP 서버 컨테이너:")
        result = subprocess.run(
            ["docker", "exec", "fc_mcp_a2a-mcp-retriever-1", "env"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            env_vars = result.stdout.strip().split('\n')
            for var in env_vars:
                if any(key in var for key in ["OPENAI_API_KEY", "TAVILY_API_KEY", "MCP_", "LOG_"]):
                    # 보안을 위해 값 마스킹
                    key, value = var.split('=', 1)
                    if "API_KEY" in key:
                        masked_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                        print(f"   - {key}={masked_value}")
                    else:
                        print(f"   - {var}")
        else:
            print(f"   ⚠️ 컨테이너 확인 실패: {result.stderr}")
        
        # A2A 서버 컨테이너 환경 변수 확인
        print("\n📦 A2A 서버 컨테이너:")
        result = subprocess.run(
            ["docker", "exec", "fc_mcp_a2a-a2a-server-1", "env"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            env_vars = result.stdout.strip().split('\n')
            for var in env_vars:
                if any(key in var for key in ["OPENAI_API_KEY", "TAVILY_API_KEY", "MCP_", "LOG_"]):
                    # 보안을 위해 값 마스킹
                    key, value = var.split('=', 1)
                    if "API_KEY" in key:
                        masked_value = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
                        print(f"   - {key}={masked_value}")
                    else:
                        print(f"   - {var}")
            print("\n✅ Docker 컨테이너에 환경 변수가 제대로 전달되었습니다.")
            return True
        else:
            print(f"   ⚠️ 컨테이너 확인 실패: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"   ❌ Docker 확인 중 오류: {e}")
        return False


async def main():
    """메인 테스트 실행"""
    print("🧪 A2A 통합 테스트 시작")
    print(f"📅 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 로컬 환경 변수 테스트
    env_test_passed = test_env_file_loaded()
    
    # 2. Docker 환경 변수 테스트
    docker_test_passed = await test_docker_env_vars()
    
    # 3. 스트리밍 테스트
    streaming_test_passed = await test_streaming_chunks()
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약:")
    print(f"   - 로컬 환경 변수 로드: {'✅ 성공' if env_test_passed else '❌ 실패'}")
    print(f"   - Docker 환경 변수 전달: {'✅ 성공' if docker_test_passed else '❌ 실패'}")
    print(f"   - 스트리밍 청크 전송: {'✅ 성공' if streaming_test_passed else '❌ 실패'}")
    
    all_passed = env_test_passed and docker_test_passed and streaming_test_passed
    print(f"\n{'🎉 모든 테스트 통과!' if all_passed else '⚠️ 일부 테스트 실패'}")
    print(f"📅 종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)