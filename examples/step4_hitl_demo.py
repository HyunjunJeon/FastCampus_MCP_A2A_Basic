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

=== 실행 방법 ===
1. 사전 준비:
   - Redis 시작: docker-compose -f docker/docker-compose.mcp.yml up -d redis
   - (선택) 웹 대시보드 접속: http://localhost:8000/hitl
     본 스크립트는 HITL 웹 서버와 A2A 서버를 자동으로 기동합니다.
2. 실행: python examples/step4_hitl_demo.py

=== 주요 개념 ===
- HITL 패턴: AI 자동화와 인간 통제의 균형
- 다단계 승인 워크플로우: 단계별 품질 관리
- 실시간 알림: WebSocket을 통한 즉시 상태 업데이트
- 상태 영속성: Redis를 통한 승인 요청 상태 관리
- 표준화된 통신: A2A 프로토콜을 통한 에이전트 상호운용성
- 사용자 경험: 직관적인 웹 인터페이스와 실시간 피드백
"""

import asyncio
import sys
import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트 디렉토리 설정
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 프로젝트 루트의 .env 파일 로드 (override=True로 기존 환경변수 덮어쓰기)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# A2A 관련 환경변수 강제 설정 (누락 방지)
os.environ.setdefault("A2A_TASK_STORE", "redis")
os.environ.setdefault("A2A_TASK_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("A2A_TASK_TTL_SECONDS", "3600")

# Step4 데모에서는 내부 그래프의 HITL을 비활성화하고
# UI에서 단일 승인 루프만 관리하도록 한다 (중복 승인 방지)
os.environ.setdefault("ENABLE_HITL", "0")
os.environ.setdefault("HITL_MODE", os.environ.get("HITL_MODE", "external"))
# Step4: 초기 명확화 질문은 건너뛰고 바로 연구/보고서 생성으로 진행
os.environ.setdefault("ALLOW_CLARIFICATION", "0")

from a2a.types import AgentSkill

from src.hitl.manager import hitl_manager
from src.hitl.storage import approval_storage

# A2A 임베디드 서버 유틸 및 HITL 그래프
from src.a2a_integration.a2a_lg_embedded_server_manager import (
    start_embedded_graph_server,
)
from src.a2a_integration.a2a_lg_utils import create_agent_card
from src.lg_agents.deep_research.deep_research_agent_a2a import (
    deep_research_graph_a2a,
)
from src.lg_agents.deep_research.supervisor_graph import build_supervisor_subgraph
from src.lg_agents.deep_research.researcher_graph import researcher_graph
from src.utils.http_client import http_client

A2A_DEFAULT_MODES = ["text/plain", "application/json", "text/markdown"]


async def start_hitl_server():
    """HITL 웹 서버 자동 시작"""

    print("[INFO] HITL 웹 서버 시작 중...")

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
                    f"[ERROR] HITL 서버 프로세스가 종료되었습니다 (exit code: {process.returncode})"
                )
                if stderr:
                    print(f"   에러: {stderr[:200]}")
                return None

            # 서버 응답 확인
            try:
                resp = await http_client.get(
                    "http://localhost:8000/health",
                    timeout=2,
                )
                if resp.status_code == 200:
                    print(f"[SUCCESS] HITL 웹 서버 정상 시작됨 ({i + 1}초 소요)")
                    return process
            except Exception:
                pass

            if i < 5:
                print(f"   ... 초기화 중 ({i + 1}/10초)")

        # 10초 후에도 응답하지 않으면 실패
        print("[ERROR] HITL 서버 시작 타임아웃 (10초)")
        process.terminate()
        return None

    except Exception as e:
        print(f"[ERROR] HITL 서버 시작 실패: {e}")
        return None


async def start_a2a_deep_research_servers():
    """Step3와 동일한 포트(8090, 8091, 8092)로 3개의 A2A 임베디드 서버를 기동"""
    host = "0.0.0.0"  # 바인드는 0.0.0.0로, 카드 URL은 localhost로 설정

    async_contexts: list[tuple[str, any]] = []
    server_infos: list[dict] = []

    # 1) Supervisor A2A 그래프 (8092)
    try:
        s_port = 8092
        s_skills = [
            AgentSkill(
                id="lead_research",
                name="Supervisor Agent",
                description="Lead and orchestrate research tasks",
                tags=["supervisor", "orchestrator"],
                examples=["Plan and coordinate multiple research units"],
            )
        ]
        supervisor_card = create_agent_card(
            name="Supervisor Agent",
            description="Supervisor graph wrapped as A2A",
            url=f"http://localhost:{s_port}",
            version="1.0.0",
            skills=s_skills,
            default_input_modes=A2A_DEFAULT_MODES,
            default_output_modes=A2A_DEFAULT_MODES,
            streaming=True,
            push_notifications=True,
        )
        supervisor_graph = build_supervisor_subgraph()
        s_ctx = start_embedded_graph_server(
            graph=supervisor_graph,
            agent_card=supervisor_card,
            host=host,
            port=s_port,
        )
        s_info = await s_ctx.__aenter__()
        async_contexts.append(("SupervisorA2AGraph", s_ctx))
        server_infos.append(s_info)
        print(
            f"[SUCCESS] SupervisorA2AGraph 임베디드 서버 준비 완료: {s_info.get('base_url')}"
        )
    except Exception as e:
        print(f"[WARNING] SupervisorA2AGraph 시작 실패: {e}")

    # 2) Researcher A2A 그래프 (8091)
    try:
        r_port = 8091
        r_skills = [
            AgentSkill(
                id="conduct_research",
                name="Researcher Agent",
                description="Web research via MCP tools",
                tags=["research", "web", "mcp"],
                examples=["Search web and synthesize findings"],
            )
        ]
        researcher_card = create_agent_card(
            name="Researcher Agent",
            description="Researcher subgraph wrapped as A2A",
            url=f"http://localhost:{r_port}",
            version="1.0.0",
            skills=r_skills,
            default_input_modes=A2A_DEFAULT_MODES,
            default_output_modes=A2A_DEFAULT_MODES,
            streaming=True,
            push_notifications=True,
        )
        researcher_graph_built = researcher_graph
        r_ctx = start_embedded_graph_server(
            graph=researcher_graph_built,
            agent_card=researcher_card,
            host=host,
            port=r_port,
        )
        r_info = await r_ctx.__aenter__()
        async_contexts.append(("ResearcherA2AGraph", r_ctx))
        server_infos.append(r_info)
        print(
            f"[SUCCESS] ResearcherA2AGraph 임베디드 서버 준비 완료: {r_info.get('base_url')}"
        )
    except Exception as e:
        print(f"[WARNING] ResearcherA2AGraph 시작 실패: {e}")

    # 3) DeepResearch(HITL) A2A 그래프 (8090)
    try:
        d_port = 8090
        d_skills = [
            AgentSkill(
                id="deep_research_hitl",
                name="Deep Research (HITL)",
                description="Deep research pipeline with human-in-the-loop approvals",
                tags=["research", "hitl"],
                examples=["Run deep research with human approvals and revisions"],
            )
        ]
        deep_card = create_agent_card(
            name="Deep Research Agent (HITL)",
            description="Deep research with human-in-the-loop approval loop",
            url=f"http://localhost:{d_port}",
            version="1.0.0",
            skills=d_skills,
            default_input_modes=A2A_DEFAULT_MODES,
            default_output_modes=A2A_DEFAULT_MODES,
            streaming=True,
            push_notifications=True,
        )
        d_ctx = start_embedded_graph_server(
            graph=deep_research_graph_a2a,
            agent_card=deep_card,
            host=host,
            port=d_port,
        )
        d_info = await d_ctx.__aenter__()
        async_contexts.append(("DeepResearchA2AGraph", d_ctx))
        server_infos.append(d_info)
        print(
            f"[SUCCESS] DeepResearchA2AGraph 임베디드 서버 준비 완료: {d_info.get('base_url')}"
        )
        # DeepResearch A2A URL 환경변수로 노출 및 즉시 헬스체크
        try:
            deep_url = d_info.get("base_url", f"http://localhost:{d_port}")
            os.environ["HITL_DEEP_RESEARCH_A2A_URL"] = deep_url
            resp = await http_client.get(
                f"{deep_url}/.well-known/agent-card.json",
                timeout=5,
            )
            if resp.status_code == 200:
                print(f"[SUCCESS] DeepResearch A2A 헬스체크 성공: {deep_url}")
            else:
                print(
                    f"[WARNING] DeepResearch A2A 헬스체크 비정상 응답: HTTP {resp.status_code}"
                )
        except Exception as e:
            print(f"[WARNING] DeepResearch A2A 헬스체크 실패: {e}")
    except Exception as e:
        print(f"[WARNING] DeepResearchA2AGraph 시작 실패: {e}")

    print(f"[SUCCESS] 총 {len(server_infos)}개의 A2A 임베디드 서버 준비 완료 (예상 3)")
    if len(server_infos) < 3:
        print("[WARNING] 일부 서버가 시작되지 않았습니다. 로그를 확인하세요.")
    return async_contexts, server_infos


async def check_system_status():
    """시스템 상태 확인 및 자동 시작"""
    print("\n[INFO] 시스템 상태 확인")
    print("=" * 60)

    hitl_server_process = None

    # Redis 연결 테스트 강화
    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis(host="localhost", port=6379)
        await r.ping()
        await r.close()
        print("[SUCCESS] Redis: 정상")
    except Exception as e:
        print(f"[ERROR] Redis: 연결 실패 - {e}")
        print(
            "   [INFO] Redis 시작: docker-compose -f docker/docker-compose.mcp.yml up -d redis"
        )

    # MCP 서버 상태 확인 추가
    mcp_services = [
        ("http://localhost:3000/health", "ArXiv MCP"),
        ("http://localhost:3001/health", "Tavily MCP"),
        ("http://localhost:3002/health", "Serper MCP"),
    ]

    for url, name in mcp_services:
        try:
            resp = await http_client.get(url, timeout=2)
            if resp.status_code == 200:
                print(f"[SUCCESS] {name}: 정상")
            else:
                print(f"[ERROR] {name}: 응답 오류")
        except Exception as e:
            print(f"[ERROR] {name}: 연결 실패 - {e}")

    # HITL API 확인 및 자동 시작
    try:
        resp = await http_client.get(
            "http://localhost:8000/health",
            timeout=5,
        )
        if resp.status_code == 200:
            print("[SUCCESS] HITL API: 정상")
        else:
            print("[ERROR] HITL API: 응답 오류")
    except Exception:
        print("[WARNING]  HITL API: 연결 실패 - 자동 시작 시도")
        hitl_server_process = await start_hitl_server()
        if hitl_server_process:
            pass  # 서버가 시작됨
        else:
            print("[ERROR] HITL API 자동 시작 실패")

    # A2A Agents 확인 (Supervisor:8092, Researcher:8091, Deep(HITL):8090)
    async def _check(url: str, name: str):
        try:
            resp = await http_client.get(
                url,
                timeout=5,
            )
            if resp.status_code == 200:
                print(f"[SUCCESS] {name}: 정상")
            else:
                print(f"[ERROR] {name}: 응답 오류")
        except Exception:
            print(f"[ERROR] {name}: 연결 실패")

    await _check("http://localhost:8092/.well-known/agent-card.json", "Supervisor A2A")
    await _check("http://localhost:8091/.well-known/agent-card.json", "Researcher A2A")
    await _check(
        "http://localhost:8090/.well-known/agent-card.json",
        "DeepResearch Control(HITL) A2A",
    )

    return hitl_server_process


async def run_a2a_deep_research_hitl_demo():
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
    a2a_contexts: list[tuple[str, any]] = []

    try:
        # 1. 시스템 상태 확인
        print("\n[INFO] 1단계: 시스템 상태 확인")
        hitl_server_process = await check_system_status()

        # 2. HITL 시스템 초기화
        print("\n[INFO] 2단계: HITL 시스템 초기화")
        if not await tester.initialize_hitl_system():
            print("[ERROR] HITL 시스템 초기화 실패. 테스트를 중단합니다.")
            return False

        # 2-1. A2A 서버들(3개) 시작 - Step3와 동일 포트 사용
        try:
            a2a_contexts, server_infos = await start_a2a_deep_research_servers()
        except Exception as e:
            print(f"[ERROR] A2A 서버 시작 실패: {e}")
            return False

        # 3. CLI에서 연구 실행 → 결과만 UI에서 확인/승인
        print("\n[INFO] 3단계: CLI에서 연구 실행 후 UI로 승인/거절")
        print("- UI는 결과 확인 및 승인/거절/피드백 입력에만 사용합니다.")
        print("- 대시보드 열기: http://localhost:8000/hitl")

        # DeepResearch(HITL) A2A 엔드포인트
        deep_url = os.environ.get("HITL_DEEP_RESEARCH_A2A_URL", "http://localhost:8090")

        # 실행 주제
        topic = os.environ.get(
            "HITL_DEMO_TOPIC", "OpenAI 가 최근에 발표한 오픈소스 모델에 대한 심층 분석"
        )

        # 개정 루프 한도
        from src.config import ResearchConfig
        from src.hitl.models import ApprovalType
        from src.a2a_integration.a2a_lg_client_utils import A2AClientManager

        max_loops = ResearchConfig().max_revision_loops
        revision_count = 0

        async def _run_deep_research(query_text: str) -> str:
            """A2A DeepResearch 서버에 질의하고 최종 보고서 텍스트만 반환

            - 텍스트 스트림이 아닌 DataPart(JSON)를 병합 수신하여 'final_report' 키를 신뢰한다.
            - 보고서가 없으면 빈 문자열을 반환한다.
            """
            async with A2AClientManager(base_url=deep_url) as client:
                merged = await client.send_data_merged(
                    {"messages": [{"role": "human", "content": query_text}]}
                )
                return (
                    (merged.get("final_report") or "")
                    if isinstance(merged, dict)
                    else ""
                )

        # 3-1) 최종 보고서 생성 먼저 수행
        print(f"\n[INFO] 연구 주제: {topic}")
        final_report = await _run_deep_research(topic)
        if not isinstance(final_report, str) or not final_report.strip():
            print("[ERROR] 최종 보고서를 생성하지 못했습니다.")
            return False

        # 3-2) 최종보고서 승인 요청 생성 (UI에서 상세보기/승인/거절)
        request = await hitl_manager.request_approval(
            agent_id="deep_research_cli",
            approval_type=ApprovalType.FINAL_REPORT,
            title="최종 보고서 승인 요청",
            description="CLI 실행 DeepResearch 결과의 최종 승인 요청",
            context={
                "task_id": "deep_research_cli_task",
                "research_topic": topic,
                "final_report": final_report,
            },
            options=["승인", "거부"],
            timeout_seconds=600,
            priority="high",
        )

        print("\n[INFO] 승인 대기 중... (UI(localhost:8000)에서 승인/거절하세요)")
        decision = await hitl_manager.wait_for_approval(
            request.request_id, auto_approve_on_timeout=False
        )

        while (
            decision
            and getattr(decision, "status", None)
            and getattr(decision.status, "value", "") == "rejected"
            and revision_count < max_loops
        ):
            revision_count += 1
            feedback = getattr(
                decision, "decision_reason", "개선 요청사항을 반영해 주세요."
            )
            print(f"[WARNING] 거부됨 → 피드백 반영 재실행 {revision_count}/{max_loops}")

            # 피드백을 반영해 보고서 개선 요청
            improved_query = (
                f"{topic}\n\n{final_report}\n\nFeedback:{feedback}\n\n"
                "위 피드백을 반영해 전체 보고서 개선 방향을 정하고 개선된 보고서를 작성해 주세요."
            )
            last_final_report = await _run_deep_research(improved_query)

            # 새 승인 요청으로 교체
            request = await hitl_manager.request_approval(
                agent_id="deep_research_cli",
                approval_type=ApprovalType.FINAL_REPORT,
                title=f"개정 보고서 승인 요청 (#{revision_count})",
                description="검토 피드백을 반영한 개정 보고서 승인 요청",
                context={
                    "task_id": f"deep_research_cli_task_rev_{revision_count}",
                    "research_topic": topic,
                    "feedback": feedback,
                    "final_report": last_final_report,
                },
                options=["승인", "거부"],
                timeout_seconds=600,
                priority="high",
            )
            print("[INFO] 개정본 승인 대기 중...")
            decision = await hitl_manager.wait_for_approval(
                request.request_id, auto_approve_on_timeout=False
            )

        # 종료 조건 평가
        if (
            decision
            and getattr(decision, "status", None)
            and getattr(decision.status, "value", "") in {"approved", "auto_approved"}
        ):
            print("\n[SUCCESS] 최종 승인 완료!")
            return True
        elif (
            revision_count >= max_loops
            and decision
            and getattr(decision, "status", None)
            and getattr(decision.status, "value", "") == "rejected"
        ):
            print("\n[WARNING] 개정 한도 초과로 종료합니다 (승인 미획득)")
            return False
        else:
            print("\n[WARNING] 승인 플로우가 정상적으로 완료되지 않았습니다.")
            return False

    except Exception as e:
        print(f"\n[ERROR] 데모 실행 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # 임베디드 A2A 서버 정리
        if a2a_contexts:
            print("\n[INFO] A2A 임베디드 서버 정리 중...")
            for name, ctx in reversed(a2a_contexts):
                try:
                    await ctx.__aexit__(None, None, None)
                    print(f"[SUCCESS] {name} 안전하게 정리됨")
                except Exception as e:
                    print(f"[WARNING] {name} 정리 중 오류: {e}")
        # HITL 웹 서버 정리
        try:
            if hitl_server_process and hitl_server_process.poll() is None:
                hitl_server_process.terminate()
                print("[SUCCESS] HITL 웹 서버 종료 요청")
        except Exception:
            pass


async def main():
    """메인 실행 함수"""
    await run_a2a_deep_research_hitl_demo()


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
    [INFO] 실행 전 확인사항:
    1. Redis가 실행 중인지 확인
       - docker-compose -f docker/docker-compose.mcp.yml up -d redis
    2. (선택) 웹 대시보드 접속 가능한지 확인
       - http://localhost:8000/hitl
       (본 스크립트는 HITL 웹 서버와 A2A 서버를 자동 기동합니다)
    
    [INFO] HITL 개념:
    - Human-In-The-Loop: AI와 인간의 협업
    - 중요한 결정은 인간이 승인
    - 실시간 웹 대시보드로 관리
    - A2A 프로토콜로 표준화된 통신
    """)

    try:
        log_file = _enable_file_logging_for_step(4)
        print(f"[INFO] 로그 파일: {log_file}")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] 프로그램이 사용자에 의해 중단되었습니다.")
        print("[SUCCESS] 안전하게 종료됩니다.")
    except Exception as e:
        print(f"\n[ERROR] 오류 발생: {e}")
        print("\n[INFO] 문제 해결:")
        print("1. HITL 시스템이 실행 중인지 확인하세요.")
        print("2. Redis 서비스 상태를 확인하세요.")
        print("3. 필요한 환경 변수가 설정되었는지 확인하세요.")
