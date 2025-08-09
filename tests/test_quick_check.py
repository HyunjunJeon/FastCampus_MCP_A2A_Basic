"""
빠른 환경 및 스트리밍 체크

이 스크립트는 개발 환경과 서버 상태를 빠르게 점검합니다.
A2A 서버의 스트리밍 기능을 간단히 테스트할 수 있습니다.

실행 방법:
    python tests/test_quick_check.py

검사 항목:
    1. 환경 변수 확인:
       - OPENAI_API_KEY
       - TAVILY_API_KEY  
       - MCP_SERVER_URL
    
    2. Docker 컨테이너 환경 변수:
       - fc_mcp_a2a-mcp-retriever-1
       - fc_mcp_a2a-a2a-server-1
    
    3. 서버 상태 확인:
       - MCP 서버 (포트 3000)
       - A2A 서버 (포트 8080)
    
    4. 스트리밍 테스트:
       - 간단한 메시지로 스트리밍 응답 테스트
       - 최대 10개 청크 수집
       - 응답 시간 측정

디버깅:
    - 환경 변수 마스킹 처리 (보안)
    - 서버별 연결 상태 개별 확인
    - 스트리밍 이벤트 실시간 모니터링
    - 타임아웃: 30초
"""
import asyncio
import os
import time
import subprocess
import httpx
from httpx_sse import aconnect_sse


def check_env_vars():
    """환경 변수 확인"""
    print("\n=== 환경 변수 확인 ===")
    
    env_vars = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
        "MCP_SERVER_URL": os.getenv("MCP_SERVER_URL", "http://localhost:3000/mcp/")
    }
    
    for key, value in env_vars.items():
        if value:
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 and "KEY" in key else value
            print(f"✅ {key}: {masked}")
        else:
            print(f"❌ {key}: Not set")


async def check_servers():
    """서버 상태 확인"""
    print("\n=== 서버 상태 확인 ===")
    
    async with httpx.AsyncClient() as client:
        # MCP 서버
        try:
            resp = await client.get("http://localhost:3000/health", timeout=5.0)
            print(f"✅ MCP 서버: {resp.status_code}")
        except Exception as e:
            print(f"❌ MCP 서버: {type(e).__name__}")
        
        # A2A 서버
        try:
            resp = await client.get("http://localhost:8080/health", timeout=5.0)
            health = resp.json()
            print(f"✅ A2A 서버: {resp.status_code}")
            print(f"   - Agent: {health.get('agent')}")
            print(f"   - Streaming: {health.get('capabilities', {}).get('streaming')}")
        except Exception as e:
            print(f"❌ A2A 서버: {type(e).__name__}")


async def test_streaming():
    """간단한 스트리밍 테스트"""
    print("\n=== 스트리밍 테스트 ===")
    
    import uuid
    
    # 짧은 테스트 메시지
    request_data = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/stream",
        "params": {
            "message": {
                "kind": "message", 
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": "안녕하세요"}]
            }
        }
    }
    
    chunks = []
    start_time = time.time()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            }
            
            print("📤 메시지 전송 중...")
            
            async with aconnect_sse(
                client, "POST", "http://localhost:8080/",
                json=request_data, headers=headers
            ) as event_source:
                
                # 최대 10개 청크만 수집
                async for sse in event_source.aiter_sse():
                    if len(chunks) >= 10:
                        break
                        
                    elapsed = time.time() - start_time
                    chunks.append({
                        "time": elapsed,
                        "event": sse.event,
                        "data_len": len(sse.data) if sse.data else 0
                    })
                    
                    print(f"   청크 #{len(chunks)}: {elapsed:.2f}초 - {sse.event}")
                    
                    if sse.event == "error":
                        print(f"   오류: {sse.data[:100]}")
                        break
        
        print(f"\n✅ 총 {len(chunks)}개 청크 수신 ({time.time() - start_time:.2f}초)")
        
    except Exception as e:
        print(f"❌ 스트리밍 오류: {type(e).__name__}: {str(e)}")


def check_docker_env():
    """Docker 컨테이너 환경 변수 확인"""
    print("\n=== Docker 환경 변수 확인 ===")
    
    containers = ["fc_mcp_a2a-mcp-retriever-1", "fc_mcp_a2a-a2a-server-1"]
    
    for container in containers:
        print(f"\n📦 {container}:")
        try:
            # Use 'printenv' to get all environment variables safely
            result = subprocess.run(
                ["docker", "exec", container, "printenv"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                env_lines = result.stdout.strip().splitlines()
                env_dict = {}
                for line in env_lines:
                    if '=' in line:
                        k, v = line.split('=', 1)
                        env_dict[k] = v
                openai_key = env_dict.get("OPENAI_API_KEY")
                tavily_key = env_dict.get("TAVILY_API_KEY")
                if openai_key:
                    openai = openai_key[:8] + "..." + openai_key[-4:] if len(openai_key) > 12 else openai_key
                    print(f"   ✅ OPENAI_API_KEY: {openai}")
                else:
                    print("   ❌ OPENAI_API_KEY: Not set")
                if tavily_key:
                    tavily = tavily_key[:8] + "..." + tavily_key[-4:] if len(tavily_key) > 12 else tavily_key
                    print(f"   ✅ TAVILY_API_KEY: {tavily}")
                else:
                    print("   ❌ TAVILY_API_KEY: Not set")
            else:
                print(f"   ❌ 확인 실패: {result.stderr.strip()}")
                
        except Exception as e:
            print(f"   ❌ 오류: {type(e).__name__}")


async def main():
    print("🧪 빠른 환경 및 스트리밍 체크")
    print("=" * 50)
    
    # 1. 환경 변수
    check_env_vars()
    
    # 2. Docker 환경
    check_docker_env()
    
    # 3. 서버 상태
    await check_servers()
    
    # 4. 스트리밍 테스트
    await test_streaming()
    
    print("\n" + "=" * 50)
    print("✅ 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())