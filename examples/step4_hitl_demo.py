#!/usr/bin/env python
# ruff: noqa: E402
"""
Step 4: HITL(Human-In-The-Loop) 통합 포괄 데모

=== 학습 목표 ===
AI 에이전트의 중요한 결정에 대해 인간의 승인을 받는
HITL(Human-In-The-Loop) 시스템의 완전한 구현과 테스트를 통해
AI와 인간의 협업 모델을 학습합니다.

=== 구현 내용 ===
1. 다단계 승인 워크플로우 (계획 → 검증 → 최종보고서)
2. 실시간 웹 대시보드를 통한 승인 요청 관리
3. WebSocket 기반 실시간 알림 시스템
4. Redis 기반 승인 상태 영속성 관리
5. A2A 프로토콜을 통한 에이전트 간 표준화된 통신
6. 취소 가능한 장시간 작업 지원 (Ctrl+C, 'cancel' 입력)
7. 부분 결과 저장 및 복구 메커니즘

=== 실행 방법 ===
1. 사전 준비:
   - Redis 시작: docker-compose -f docker/docker-compose.mcp.yml up -d redis
   - (선택) 웹 대시보드 접속: http://localhost:8000/hitl
     본 스크립트는 HITL 웹 서버와 A2A 서버를 자동으로 기동합니다.
2. 실행: python examples/step4_hitl_demo.py
3. 실행 모드 선택:
   - comprehensive: 자동화된 포괄적 테스트
   - interactive: 단계별 대화형 데모
   - cancellable: 취소 가능한 DeepResearch 테스트

=== 주요 개념 ===
- HITL 패턴: AI 자동화와 인간 통제의 균형
- 다단계 승인 워크플로우: 단계별 품질 관리
- 실시간 알림: WebSocket을 통한 즉시 상태 업데이트
- 상태 영속성: Redis를 통한 승인 요청 상태 관리
- 표준화된 통신: A2A 프로토콜을 통한 에이전트 상호운용성
- 복원력: 취소/중단 시나리오에서의 안전한 정리
- 사용자 경험: 직관적인 웹 인터페이스와 실시간 피드백
"""

import asyncio
import sys
import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# 프로젝트 루트의 .env 파일 로드
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import aiohttp
from a2a.types import AgentSkill

# HITL 컴포넌트 임포트
from src.hitl.manager import hitl_manager
from src.hitl.storage import approval_storage

# A2A 임베디드 서버 유틸 및 HITL 그래프
from src.a2a_integration.a2a_lg_embedded_server_manager import (
    start_embedded_graph_server,
)
from src.a2a_integration.a2a_lg_utils import create_agent_card
from src.lg_agents.deep_research.deep_research_agent_hitl import (
    deep_research_graph_with_hitl,
)

async def start_hitl_server():
    """HITL 웹 서버 자동 시작"""
    import subprocess

    print("🚀 HITL 웹 서버 시작 중...")

    try:
        # HITL 서버 시작 (백그라운드)
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "src.hitl_web.api:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]

        # stdout/stderr를 파이프로 받으면 버퍼가 가득 차 서버가 멈출 수 있으므로 버리고 실행
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 서버 시작 대기 (최대 10초)
        for i in range(10):
            await asyncio.sleep(1)

            # 프로세스가 죽었는지 확인
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                print(
                    f"❌ HITL 서버 프로세스가 종료되었습니다 (exit code: {process.returncode})"
                )
                if stderr:
                    print(f"   에러: {stderr[:200]}")
                return None

            # 서버 응답 확인
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "http://localhost:8000/health",
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as resp:
                        if resp.status == 200:
                            print(f"✅ HITL 웹 서버 정상 시작됨 ({i + 1}초 소요)")
                            return process
            except Exception:
                pass

            if i < 5:
                print(f"   ... 초기화 중 ({i + 1}/10초)")

        # 10초 후에도 응답하지 않으면 실패
        print("❌ HITL 서버 시작 타임아웃 (10초)")
        process.terminate()
        return None

    except Exception as e:
        print(f"❌ HITL 서버 시작 실패: {e}")
        return None

async def start_hitl_a2a_server():
    """HITL 통합 DeepResearch 그래프를 A2A 서버로 임베디드 기동 (포트 8090)"""
    host = "0.0.0.0"  # 바인드는 0.0.0.0로, 카드 URL은 localhost로 설정
    port = 8090

    skills = [
        AgentSkill(
            id="deep_research_hitl",
            name="Deep Research (HITL)",
            description="Deep research pipeline with human-in-the-loop approvals",
            tags=["research", "hitl"],
            examples=["Run deep research with human approvals and revisions"],
        )
    ]

    agent_card = create_agent_card(
        name="Deep Research Agent (HITL)",
        description="Deep research with human-in-the-loop approval loop",
        url=f"http://localhost:{port}",
        version="1.0.0",
        skills=skills,
        default_input_modes=["text"],
        default_output_modes=["text/plain"],
        streaming=True,
        push_notifications=True,
    )

    # Async context manager 수동 진입/종료를 위해 반환
    ctx = start_embedded_graph_server(
        graph=deep_research_graph_with_hitl, agent_card=agent_card, host=host, port=port
    )
    ctx_manager = await ctx.__aenter__()
    print(f"✅ HITL A2A 서버 시작됨: {ctx_manager.get('base_url')}")
    return ctx

async def check_system_status():
    """시스템 상태 확인 및 자동 시작"""
    print("\n🔍 시스템 상태 확인")
    print("=" * 60)

    hitl_server_process = None

    # Redis 확인
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379)
        r.ping()
        print("✅ Redis: 정상")
    except Exception:
        print("❌ Redis: 연결 실패")
        print(
            "   💡 Redis 시작: docker-compose -f docker/docker-compose.mcp.yml up -d redis"
        )

    # HITL API 확인 및 자동 시작
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8000/health", timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    print("✅ HITL API: 정상")
                else:
                    print("❌ HITL API: 응답 오류")
    except Exception:
        print("⚠️  HITL API: 연결 실패 - 자동 시작 시도")
        hitl_server_process = await start_hitl_server()
        if hitl_server_process:
            pass  # 서버가 시작됨
        else:
            print("❌ HITL API 자동 시작 실패")

    # A2A Agent 확인 (HITL 그래프, 8090)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8090/.well-known/agent-card.json",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status == 200:
                    print("✅ HITL Research Agent: 정상")
                else:
                    print("❌ HITL Research Agent: 응답 오류")
    except Exception:
        print("❌ HITL Research Agent: 연결 실패")

    return hitl_server_process

async def a2a_deepresearch_hitl():
    """HITL DeepResearch 데모 실행"""
    print("=== Step 4: HITL DeepResearch 데모 ===")

    class _Noop:
        async def initialize_hitl_system(self):
            try:
                await hitl_manager.initialize()
                await approval_storage.connect()
                return True
            except Exception:
                return False
        async def cleanup(self):
            try:
                await approval_storage.disconnect()
                await hitl_manager.shutdown()
            except Exception:
                pass
        @property
        def test_results(self):
            return []
        def generate_test_report(self):
            return 1.0
    tester = _Noop()
    hitl_server_process = None
    a2a_ctx = None

    try:
        # 1. 시스템 상태 확인
        print("\n🔍 1단계: 시스템 상태 확인")
        hitl_server_process = await check_system_status()

        # 2. HITL 시스템 초기화
        print("\n⚡ 2단계: HITL 시스템 초기화")
        if not await tester.initialize_hitl_system():
            print("❌ HITL 시스템 초기화 실패. 테스트를 중단합니다.")
            return False

        # 2-1. HITL A2A 서버(그래프) 시작
        try:
            a2a_ctx = await start_hitl_a2a_server()
        except Exception as e:
            print(f"❌ HITL A2A 서버 시작 실패: {e}")
            return False

        print("- 웹 대시보드에서 승인/거부/피드백과 연구 시작을 직접 제어하세요.")
        print("- 실시간 진행상황은 WebSocket으로 자동 반영됩니다.")
        print("\n📌 열기: http://localhost:8000/")
        print("   연구 시작(우측 하단 🔬) → 승인 항목에서 승인/거부/상세보기 동작 확인")
        print("\n⏳ 서버가 실행 중입니다. 중지하려면 Ctrl+C 를 누르세요.")

        # 사용자 중단(CTRL+C)까지 무기한 대기
        try:
            await asyncio.Event().wait()
        except Exception:
            pass

    except Exception as e:
        print(f"\n💥 데모 실행 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        pass


async def main():
    """메인 실행 함수"""
    print("""
    📌 실행 전 확인사항:
    1. Redis가 실행 중인지 확인
       - docker-compose -f docker/docker-compose.mcp.yml up -d redis
    2. 웹 대시보드 접속 확인  
       - http://localhost:8000/hitl
       (본 스크립트는 HITL 웹 서버와 A2A 서버를 자동 기동합니다)
    """)
    await a2a_deepresearch_hitl()


def _enable_file_logging_for_step(step_number: int) -> str:
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"step{step_number}_{ts}.log")

    # 환경변수 힌트 (구조화 로깅/루트 로거 파일 핸들러)
    os.environ["LOG_FILE"] = log_path
    os.environ["LOG_FILE_PATH"] = log_path

    class _Tee:
        def __init__(self, stream, file):
            self._stream = stream
            self._file = file
        def write(self, data):
            try:
                self._stream.write(data)
            except Exception:
                pass
            try:
                self._file.write(data)
            except Exception:
                pass
        def flush(self):
            try:
                self._stream.flush()
            except Exception:
                pass
            try:
                self._file.flush()
            except Exception:
                pass

    f = open(log_path, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)
    return log_path


if __name__ == "__main__":
    print("""
    📌 실행 전 확인사항:
    1. Redis가 실행 중인지 확인
       - docker-compose -f docker/docker-compose.mcp.yml up -d redis
    2. (선택) 웹 대시보드 접속 가능한지 확인
       - http://localhost:8000/hitl
       (본 스크립트는 HITL 웹 서버와 A2A 서버를 자동 기동합니다)
    
    📌 HITL 개념:
    - Human-In-The-Loop: AI와 인간의 협업
    - 중요한 결정은 인간이 승인
    - 실시간 웹 대시보드로 관리
    - A2A 프로토콜로 표준화된 통신
    
    🆕 새로운 기능:
    - 작업 중간 취소 기능 (Ctrl+C 또는 'cancel' 입력)
    - 부분 결과 저장 및 복구
    - 안전한 리소스 정리
    """)

    try:
        log_file = _enable_file_logging_for_step(4)
        print(f"📝 로그 파일: {log_file}")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 프로그램이 사용자에 의해 중단되었습니다.")
        print("✅ 안전하게 종료됩니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        print("\n🔧 문제 해결:")
        print("1. HITL 시스템이 실행 중인지 확인하세요.")
        print("2. Redis 서비스 상태를 확인하세요.")
        print("3. 필요한 환경 변수가 설정되었는지 확인하세요.")
