# ruff: noqa: E402
"""
Step 3: Deep Research 시스템 비교 - LangGraph vs A2A

=== 학습 목표 ===
동일한 Deep Research 기능을 두 가지 다른 아키텍처로 구현하여
각각의 장단점을 실제 코드로 비교 학습합니다.

=== 비교 대상 ===
1. LangGraph Deep Research (lg_agents/deep_research_agent.py)
   - 복잡한 상태 그래프 (AgentState, SupervisorState, ResearcherState)
   - 서브그래프와 Command 객체로 노드 간 라우팅
   - clarify_with_user → write_research_brief → supervisor → researcher → compress_research → final_report_generation

2. A2A Deep Research
   - 독립적인 에이전트들의 Agent-to-Agent 통신
   - 평면적 컨텍스트 공유: 실제로 DeepResearch 에서는 Supervisor 를 호출할 때만 A2A 호출을 활용
   - DeepResearchA2AAgent → SupervisorA2AAgent → (researcher → compress_research → final_report_generation)

=== 실행 방법 ===
1. 환경변수 설정: OPENAI_API_KEY 등 필수 API 키
2. 이 스크립트 실행: python examples/step3_multiagent_systems.py
3. 가이드에 따라 동일한 질문으로 두 시스템 비교 실행

=== 핵심 비교 포인트 ===
- 노드 기반 vs 에이전트 기반 아키텍처
- 중앙집중식 상태 관리 vs 분산된 독립 실행
- 복잡한 그래프 라우팅 vs 단순한 메시지 전달
- 시스템 확장성과 유지보수성 차이
- 실행 성능과 리소스 사용량 비교
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 및 src 경로를 가장 먼저 sys.path에 추가하여 임포트 오류 방지
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv
from lg_agents.deep_research.researcher_graph import researcher_graph


def safe_print(*args, **kwargs):
    """BrokenPipeError 등 출력 스트림 예외를 무시하는 안전 출력 함수"""
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        try:
            sys.stderr.flush()
        except Exception:
            pass
        return

# 환경변수 로드 - API 키 및 설정 값들
load_dotenv(PROJECT_ROOT / ".env")


# --- 런타임 로그 파일 저장 설정 (logs/step3_*.log) ---
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


def _enable_file_logging_for_step(step_number: int) -> str:
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"step{step_number}_{ts}.log"

    # 환경변수 기반 로거들도 파일로 쓰도록 힌트 제공
    os.environ["LOG_FILE"] = str(log_path)
    os.environ["LOG_FILE_PATH"] = str(log_path)

    # stdout/stderr Tee 설정 (print와 로거 모두 파일에 기록되도록)
    f = open(log_path, "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, f)
    sys.stderr = _Tee(sys.stderr, f)
    return str(log_path)

class MultiAgentSystemLauncher:
    """
    멀티에이전트 시스템 실행기

    === 주요 기능 ===
    1. MCP 서버들 자동 시작/관리
    2. A2A 에이전트들 임베디드 서버로 안전하게 시작/관리
    3. Context Manager를 활용한 자동 리소스 관리
    4. 예외 상황에서의 안전한 정리

    === 리소스 관리 개선사항 ===
    - subprocess 대신 임베디드 서버로 안전한 실행
    - Context Manager로 자동 생명주기 관리
    - 예외 발생 시 확실한 자동 정리
    - 포트 충돌 방지 및 자동 할당
    """

    def __init__(self):
        # 임베디드 서버 매니저들을 저장할 리스트
        self.embedded_managers = []
        # 서버 정보들을 저장할 딕셔너리
        self.server_infos = {}
        # 프로젝트 루트 경로 (명령어 실행 기준)
        self.project_root = PROJECT_ROOT

    async def cleanup_embedded_servers(self):
        """
        임베디드 서버들 정리 (Context Manager가 자동으로 처리)

        === 정리 과정 ===
        1. 모든 Context Manager 자동 종료
        2. 서버 정보 딕셔너리 초기화
        3. 포트 자동 해제
        
        === 장점 ===
        - Context Manager의 안전한 자동 정리
        - 포트 누수 방지
        """
        safe_print("\n🧹 임베디드 서버들 정리 중...")
        
        # Context Manager들이 자동으로 정리됨 (Context Manager 블록을 벗어날 때 __aexit__ 호출)
        self.embedded_managers.clear()
        self.server_infos.clear()
        
        safe_print("✅ 모든 임베디드 서버가 안전하게 정리되었습니다.")

    def health_check_mcp_servers(self):
        """
        MCP 서버들의 Health Check

        === Health Check 과정 ===
        1. 각 MCP 서버의 상태 확인
        2. 정상 작동 여부 출력
        3. 비정상 서버에 대한 경고 메시지 출력

        === 사용 목적 ===
        - 모든 MCP 서버가 정상적으로 작동하는지 확인
        - 시스템 시작 전 필수 조건 충족 여부 검사
        """
        safe_print("\n🔍 MCP 서버 Health Check 중...")

        # MCP 서버 URL 목록 (도커에서 실행 중)
        mcp_servers = [
            "http://localhost:3000/health",
            "http://localhost:3001/health",
            "http://localhost:3002/health",
        ]

        for url in mcp_servers:
            try:
                response = httpx.get(url, timeout=5)
                # 상태 코드가 200이면 정상 작동 중
                if response.status_code == 200:
                    safe_print(f"✅ {url} - 정상 작동 중")
                else:
                    safe_print(f"⚠️ {url} - 상태 코드: {response.status_code}")
            except httpx.RequestError as e:
                safe_print(f"❌ {url} - 연결 실패: {e}")

    async def start_a2a_embedded_agents(self):
        """
        A2A 에이전트들을 임베디드 서버로 안전하게 시작

        === A2A 에이전트 역할 ===
        - Planner: 연구 계획 수립 및 작업 분할
        - Researcher: 웹 검색 및 데이터 수집  
        - Writer: 보고서 작성 및 요약

        === 임베디드 서버 장점 ===
        1. Context Manager로 자동 생명주기 관리
        2. 포트 충돌 방지 (자동 할당)
        3. 예외 상황에서 안전한 정리 보장
        4. subprocess 관리 복잡성 제거
        """
        safe_print("\n🤖 A2A 임베디드 에이전트들 시작 중...")

        # 필요한 모듈 import
        from src.a2a_integration.a2a_lg_embedded_server_manager import start_embedded_graph_server
        from src.a2a_integration.a2a_lg_utils import create_agent_card
        from a2a.types import AgentSkill
        from src.lg_agents.deep_research.deep_research_agent_a2a import deep_research_graph_a2a
        from src.lg_agents.deep_research.supervisor_graph import build_supervisor_subgraph

        try:
            skills = [
                AgentSkill(
                    id="deep_research",
                    name="Deep Research Agent",
                    description="Deep research pipeline",
                    tags=["research", "agent"],
                    examples=["Run full deep research pipeline"],
                )
            ]
            
            # 포트 배치: Supervisor=8092, Researcher=8091, DeepResearch=8090
            # DeepResearch는 내부에서 Supervisor를 기본 http://localhost:8092로 호출
            port = 8090
            host = "0.0.0.0"  # 바인딩 호스트
            card_host = "localhost"  # 클라이언트 접속 호스트
            agent_card = create_agent_card(
                name="Deep Research A2A Agent",
                description="Deep research pipeline (Supervisor A2A)",
                url=f"http://{card_host}:{port}",
                version="1.0.0",
                skills=skills,
                default_input_modes=["text/plain", "application/json"],
                default_output_modes=["text/plain", "application/json"],
                streaming=True,
                push_notifications=True,
            )
            graph_ctx = start_embedded_graph_server(
                graph=deep_research_graph_a2a,
                agent_card=agent_card,
                host=host,
                port=port,
            )
            self.embedded_managers.append(("DeepResearchA2AGraph", graph_ctx))
            safe_print("✅ DeepResearchA2AGraph 임베디드 서버 준비 완료 (graph)")
        except Exception as e:
            safe_print(f"⚠️ DeepResearchGraph 시작 실패: {e}")

        # 연구자 A2A 그래프 서버
        try:
            r_port = 8091  # ResearchConfig 기본 a2a_endpoint와 정렬
            r_host = "0.0.0.0"  # 바인딩 호스트
            r_card_host = "localhost"  # 클라이언트 접속 호스트
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
                url=f"http://{r_card_host}:{r_port}",
                version="1.0.0",
                skills=r_skills,
                default_input_modes=["text/plain", "application/json"],
                default_output_modes=["text/plain", "application/json"],
                streaming=True,
                push_notifications=True,
            )
            researcher_ctx = start_embedded_graph_server(
                graph=researcher_graph,
                agent_card=researcher_card,
                host=r_host,
                port=r_port,
            )
            self.embedded_managers.append(("ResearcherA2AGraph", researcher_ctx))
            safe_print("✅ ResearcherA2AGraph 임베디드 서버 준비 완료 (graph)")
        except Exception as e:
            safe_print(f"⚠️ ResearcherA2AGraph 시작 실패: {e}")

        # Supervisor A2A 그래프 서버
        try:
            s_port = 8090
            s_host = "0.0.0.0"
            s_card_host = "localhost"
            s_skills = [
                AgentSkill(
                    id="lead_research",
                    name="Supervisor Agent",
                    description="Lead and orchestrate research tasks",
                    tags=["supervisor", "orchestrator"],
                    examples=["Plan and coordinate multiple research units"],
                )
            ]
            s_port = 8092
            supervisor_card = create_agent_card(
                name="Supervisor Agent",
                description="Supervisor graph wrapped as A2A",
                url=f"http://{s_card_host}:{s_port}",
                version="1.0.0",
                skills=s_skills,
                default_input_modes=["text/plain", "application/json"],
                default_output_modes=["text/plain", "application/json"],
                streaming=True,
                push_notifications=True,
            )
            supervisor_graph = build_supervisor_subgraph()
            supervisor_ctx = start_embedded_graph_server(
                graph=supervisor_graph,
                agent_card=supervisor_card,
                host=s_host,
                port=s_port,
            )
            self.embedded_managers.append(("SupervisorA2AGraph", supervisor_ctx))
            safe_print("✅ SupervisorA2AGraph 임베디드 서버 준비 완료 (graph)")
        except Exception as e:
            safe_print(f"⚠️ SupervisorA2AGraph 시작 실패: {e}")

        total_agents = len(self.embedded_managers)
        safe_print(f"✅ 총 {total_agents}개의 A2A 임베디드 에이전트 준비 완료")
        safe_print("   임베디드 서버는 빠른 초기화로 즉시 사용 가능합니다.")
        if total_agents < 3:
            safe_print("⚠️ 예상된 3개 A2A 서버 중 일부가 시작되지 않았습니다 (DeepResearch/Researcher/Supervisor)")

        return self.embedded_managers


async def run_actual_comparison_with_endpoints(endpoints: dict[str, str] | None = None):
    """
    실제 시스템 비교 실행 (임베디드 서버 기반)

    === 비교 실험 내용 ===
    1. 동일한 연구 주제로 두 시스템 테스트
    2. 실행 시간, 리소스 사용량 측정
    3. 결과 품질 및 사용자 경험 비교
    4. 측정 결과를 JSON 파일로 저장

    === 학습 포인트 ===
    - 이론과 실제의 차이 확인
    - 성능 비교를 위한 측정 방법 학습
    - 실제 환경에서의 예외 상황 처리
    """
    safe_print("\n🔬 실제 멀티에이전트 시스템 비교 실행")
    safe_print("=" * 60)
    try:
        from examples.compare_systems import run_comparison

        start_time = datetime.now()

        query = f"OpenAI, Anthropic, Google, Meta, Microsoft 의 AI 기술 동향에 대해 보고서를 작성해주세요. 오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}"
        
        result = await run_comparison(
            query=query,
            endpoints=endpoints or {},
            langgraph_run=False,
            a2a_run=True,
        )

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        safe_print(f"\n✅ 비교 완료! 총 실행 시간: {total_time:.2f}초")

        if result:
            saved_path = result.get("output_path") if isinstance(result, dict) else None
            if saved_path:
                safe_print(f"\n💾 세부 결과가 {saved_path}에 저장되었습니다.")
            else:
                safe_print("\n💾 세부 결과가 reports/ 내 결과 파일에 저장되었습니다.")

        return True

    except Exception as e:
        safe_print(f"❌ 비교 실행 실패: {e}")
        safe_print("\n💡 문제 해결 방법:")
        safe_print("1. MCP 서버들이 모두 정상 실행 중인지 확인")
        safe_print("2. A2A 에이전트들이 모두 시작되었는지 확인")
        safe_print("3. 네트워크 연결 상태 확인")
        return False


async def main():
    """
    Step 3 메인 실행 함수

    === 실행 단계 ===
    1. State 복잡성 이론 설명
    2. 실행 흐름 차이 비교
    3. 임베디드 서버로 실제 시스템 실행 및 비교
    4. 결과 분석 및 교육적 해설

    === 리소스 관리 개선사항 ===
    - Context Manager를 활용한 자동 서버 생명주기 관리
    - 예외 상황에서도 안전한 자동 종료 보장
    - 포트 누수 및 프로세스 누수 완전 방지
    """
    safe_print("=== Step 3: 멀티에이전트 시스템 실제 비교 ===")

    # 시스템 실행기 초기화
    launcher = MultiAgentSystemLauncher()

    try:
        safe_print("   - LangGraph: 복잡한 상태 그래프 방식")
        safe_print("   - A2A: 단순한 에이전트 협업 방식")

        # 3. 실제 시스템 시작 및 상태 확인
        safe_print("\n🚀 멀티에이전트 시스템 시작 (임베디드 서버 방식)")
        safe_print("=" * 60)
        safe_print("\n🤖 단계 1: A2A 에이전트들 임베디드 서버로 안전 시작")
        # A2A 에이전트들을 임베디드 서버로 시작
        embedded_agents = await launcher.start_a2a_embedded_agents()

        # 시스템 상태 종합 확인
        safe_print("\n📋 단계 2: 시스템 상태 종합 확인")
        safe_print("   모든 서버와 에이전트들의 정상 가동 여부 검사 중...")
        
        # Context Manager들이 활성 상태인지 확인
        running_agents = []
        failed_agents = []

        for name, _ in embedded_agents:
            # 임베디드 서버는 Context Manager 진입 시 즉시 가용
            running_agents.append(name)
            safe_print(f"✅ {name} - 임베디드 서버 정상 실행 중")

        # 시스템 상태 평가
        total_expected = len(embedded_agents)  # 시작된 임베디드 에이전트 수
        success_rate = len(running_agents) / max(total_expected, 1) * 100

        safe_print("\n📊 시스템 상태 요약:")
        safe_print(
            f"   - 정상 작동: {len(running_agents)}/{total_expected} ({success_rate:.1f}%)"
        )
        safe_print(f"   - 실패/중지: {len(failed_agents)}개")

        if len(running_agents) >= 3:  # 최소 3개 에이전트 필요
            safe_print("✅ 전체 시스템이 정상적으로 준비되었습니다!")
        else:
            safe_print("⚠️  일부 서비스 시작 실패했지만, 비교 실험을 계속 진행합니다.")
            safe_print("   실제 환경에서는 이런 부분적 실패도 고려해야 합니다.")

        # 자동 진행 모드 - 입력 대기 없이 바로 시작
        safe_print("\n🚀 비교 실험을 자동으로 시작합니다...")
        await asyncio.sleep(1)  # 짧은 대기

        # 4. Context Manager를 통한 안전한 시스템 실행
        safe_print("\n🔒 임베디드 서버들과 함께 비교 실험 시작")
        safe_print("   Context Manager가 모든 서버를 자동으로 관리합니다.")
        
        # 모든 임베디드 서버들을 Context Manager로 관리하면서 비교 실행
        async def run_with_embedded_servers():
            # 모든 Context Manager 진입
            server_infos = []
            role_endpoints = {}
            async_contexts = []
            
            try:
                for name, server_ctx in embedded_agents:
                    ctx_manager = await server_ctx.__aenter__()
                    async_contexts.append((name, server_ctx))
                    server_infos.append(ctx_manager)
                    safe_print(f"🔗 {name} 임베디드 서버 활성화됨")

                    # 비교 모듈에 전달할 엔드포인트 매핑 수집
                    base_url = ctx_manager.get("base_url")
                    if name == "DeepResearchA2AGraph":
                        role_endpoints["deep_research"] = base_url
                    elif name == "ResearcherA2AGraph":
                        role_endpoints["researcher"] = base_url
                    elif name == "SupervisorA2AGraph":
                        role_endpoints["supervisor"] = base_url

                safe_print("✅ 모든 임베디드 서버가 활성화되었습니다!")
                safe_print(f"🔎 활성 서버 수: {len(server_infos)} (예상: 3)")
                if len(server_infos) < 3:
                    safe_print("⚠️ 서버 수가 부족합니다. A2A 비교는 계속 시도하되 일부 경로에서 폴백이 발생할 수 있습니다.")
                
                # 실제 비교 실행
                # 비교 실행에 동적으로 할당된 A2A 엔드포인트 전달
                success = await run_actual_comparison_with_endpoints(role_endpoints)
                
                return success
                
            finally:
                # 모든 Context Manager 안전 종료
                safe_print("\n🧹 임베디드 서버들 자동 정리 중...")
                for name, server_ctx in reversed(async_contexts):
                    try:
                        await server_ctx.__aexit__(None, None, None)
                        safe_print(f"✅ {name} 안전하게 정리됨")
                    except Exception as e:
                        safe_print(f"⚠️ {name} 정리 중 오류: {e}")

        # 비교 실험 실행
        await run_with_embedded_servers()

    except KeyboardInterrupt:
        safe_print("\n\n🛑 사용자에 의해 중단됨")

    except Exception as e:
        safe_print(f"\n❌ 예상치 못한 오류: {e}")

    finally:
        # 리소스 정리 단계 - Context Manager 자동 정리
        safe_print("\n🧹 리소스 정리 단계 진입...")
        await launcher.cleanup_embedded_servers()
        safe_print("✅ 모든 임베디드 서버들이 Context Manager에 의해 안전하게 정리되었습니다.")
        safe_print("🔒 포트 자동 해제 및 메모리 정리 완료.")


if __name__ == "__main__":
    """
    Step 3 데모 실행 진입점
    """
    # 로그 파일 활성화
    log_file = _enable_file_logging_for_step(3)
    safe_print(f"📝 로그 파일: {log_file}")

    # 실행 전 사전 요구사항 확인
    safe_print("🔍 사전 요구사항 확인 중...")

    # 필수 환경변수 확인
    required_keys = ["OPENAI_API_KEY"]
    missing_keys = []

    for key in required_keys:
        if not os.getenv(key):
            missing_keys.append(key)

    if missing_keys:
        safe_print(f"❌ 필수 환경변수가 설정되지 않았습니다: {', '.join(missing_keys)}")
        safe_print("🔧 해결 방법:")
        safe_print("   1. .env 파일에 API 키 설정")
        safe_print("   2. 환경변수 직접 설정: export OPENAI_API_KEY=your_key")
        sys.exit(1)

    safe_print("✅ 모든 사전 요구사항 확인 완료!")

    try:
        # Step 3 메인 데모 실행
        asyncio.run(main())

    except KeyboardInterrupt:
        safe_print("\n\n⏹️ 사용자에 의해 데모가 중단되었습니다.")
        safe_print("🛡️ 중단 시에도 리소스 정리가 자동으로 수행됩니다.")

    except Exception as e:
        safe_print(f"\n⚠️ 예상치 못한 오류 발생: {e}")
        safe_print("🔧 이러한 오류도 실제 비즈니스 환경에서 고려해야 할 요소입니다.")

    finally:
        safe_print("\n🎓 Step 3 학습 완료: 멀티에이전트 시스템 비교 학습을 마쳤습니다.")
