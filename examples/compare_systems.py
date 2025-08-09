# ruff: noqa: E402
"""
Step 3에서 사용하는 LangGraph vs A2A 시스템 실제 비교 모듈

=== 학습 목표 ===
동일한 연구 작업을 두 가지 다른 아키텍처로 실행하여
실제 성능 차이와 구현 복잡성을 직접 비교합니다.

=== 비교 대상 ===
1. LangGraph Deep Research: 복잡한 상태 그래프 방식 (lg_agents/deep_research_agent.py)
   - 6개 노드의 복잡한 상태 그래프 (clarify_with_user → write_research_brief → supervisor → researcher → compress_research → final_report_generation)
   - 중첩된 상태 관리 (AgentState, SupervisorState, ResearcherState)
   - 서브그래프와 Command 객체로 노드 간 라우팅
   - 단일 프로세스 내 순차 실행

2. A2A Deep Research: 단순한 에이전트 협업 방식 (a2a_orchestrator/agents/deep_research.py)
   - 5개 독립 에이전트의 Agent-to-Agent 통신 (DeepResearchA2AAgent, PlannerA2AAgent, ResearcherA2AAgent, WriterA2AAgent, EvaluatorA2AAgent)
   - 평면적 컨텍스트 공유 (research_context 딕셔너리)
   - 독립 실행과 표준화된 A2A 프로토콜 통신
   - 병렬 실행 가능한 분산 아키텍처

=== 비교 메트릭 ===
- 실행 시간 (시작부터 완료까지)
- State/Context 복잡성 (관리해야 할 데이터 구조)
- 메모리 사용량 및 리소스 효율성
- 에러 처리 및 복구 능력
- 확장성 (새로운 에이전트 추가 용이성)

=== 사용법 ===
이 모듈은 examples/step3_multiagent_systems.py에서 import되어
run_comparison() 함수가 호출되어 실제 비교 실험을 수행합니다.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 파일 로드
load_dotenv(PROJECT_ROOT / ".env")

# 로깅 설정
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def run_langgraph_deep_research(query: str):
    """LangGraph 딥리서치 구현체 실행 (복잡한 State 관리)"""
    print("\n" + "=" * 80)
    print("🔴 LangGraph 딥리서치 구현체 실행")
    print("=" * 80)

    start_time = datetime.now()

    try:
        print("📥 LangGraph 딥리서치 에이전트 임포트 중...")
        # LangGraph 기반 딥리서치 에이전트 (복잡한 State 관리)
        from src.lg_agents.deep_research.deep_research_agent import deep_research_graph
        from langchain_core.messages import HumanMessage

        print("✅ deep_research_graph 임포트 성공")

        print("🔧 LangGraph 딥리서치 그래프 가져오기...")
        app = deep_research_graph
        print("✅ LangGraph 딥리서치 그래프 준비 완료")

        print(f"📝 딥리서치 쿼리 실행: {query}")
        print("🔄 LangGraph 복잡한 State 관리로 실행 중...")

        # 실제 LangGraph 딥리서치 실행
        result = await app.ainvoke({"messages": [HumanMessage(content=query)]})

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        print("✅ LangGraph 딥리서치 실행 완료!")
        print(f"⏱️  실행 시간: {execution_time:.2f}초")
        print(f"📄 결과 길이: {len(str(result))} 문자")

        return {
            "success": True,
            "execution_time": execution_time,
            "result": {
                "final_report": result.get("final_report", ""),
                "research_brief": result.get("research_brief", ""),
                "raw_notes_count": len(result.get("raw_notes", [])),
                "notes_count": len(result.get("notes", [])),
                "messages_count": len(result.get("messages", [])),
                "state_keys": list(result.keys()) if result else [],
            },
            "system_type": "LangGraph 딥리서치",
            "architecture": "복잡한 State 관리, 중앙 집중식, 순차 실행",
        }

    except Exception as e:
        error_msg = f"LangGraph 딥리서치 실행 실패: {e}"
        print(f"❌ {error_msg}")

        import traceback

        print("🔍 에러 상세:")
        print(traceback.format_exc())

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        return {
            "success": False,
            "error": error_msg,
            "execution_time": execution_time,
            "system_type": "LangGraph 딥리서치",
        }


async def run_a2a_deep_research(
    query: str,
    endpoints: dict[str, str] | None = None,
    *,
    enable_hitl: bool = False,
    reviewer_id: str = "demo_reviewer",
    approval_timeout_seconds: int = 600,
):
    """A2A 딥리서치 구현체 실행 (단순한 Context 관리)

    - enable_hitl: 최종 결과물에 대해 HITL 최종 승인 루프(단순 승인/거부)를 적용
      (Step 3 기본 비교에는 False 유지, Step 4에서 True로 활용)
    """
    print("\n" + "=" * 80)
    print("🔵 A2A 딥리서치 구현체 실행")
    print("=" * 80)

    start_time = datetime.now()

    try:
        print("📥 A2A 딥리서치 에이전트들 임포트 중...")
        # 필요 모듈 로드
        from a2a.types import AgentCard, AgentCapabilities, AgentSkill
        from src.a2a_integration.a2a_lg_embedded_server_manager import (
            start_embedded_graph_server,
        )
        from src.lg_agents.deep_research.deep_research_agent import (
            deep_research_graph,
        )
        from src.a2a_integration.a2a_lg_client_utils import A2AClientManager

        print("✅ A2A 딥리서치 에이전트들 임포트 성공")
        print("🔧 A2A 딥리서치 에이전트들 초기화 중...")

        # 외부에서 엔드포인트가 주어지면 그대로 사용 (이미 띄워진 서버)
        if endpoints and isinstance(endpoints, dict) and endpoints.get("deep_research"):
            base_url = endpoints["deep_research"]
            print(f"🔗 외부 제공 A2A 엔드포인트 사용: {base_url}")
            async with A2AClientManager(base_url=base_url) as client:
                response_text = await client.send_query(query)
        else:
            # 임베디드 A2A 서버를 시작해 해당 그래프를 래핑
            host = "0.0.0.0"
            port = 8000
            skills = [
                AgentSkill(
                    id="deep_research",
                    name="Deep Research",
                    description="Deep research pipeline (LangGraph wrapped via A2A)",
                    tags=["research", "pipeline"],
                    examples=["교육에 미치는 AI의 영향 분석"],
                )
            ]

            agent_card = AgentCard(
                name="Deep Research Agent",
                description="Deep research pipeline wrapped by A2A",
                url=f"http://{host}:{port}",
                capabilities=AgentCapabilities(
                    streaming=True,
                    push_notifications=True,
                    state_transition_history=True,
                ),
                default_input_modes=["text"],
                default_output_modes=["text"],
                skills=skills,
                version="1.0.0",
            )

            async with start_embedded_graph_server(
                graph=deep_research_graph, agent_card=agent_card, host=host, port=port
            ) as server_info:
                base_url = server_info["base_url"]
                print(f"✅ 임베디드 A2A 서버 시작: {base_url}")

                async with A2AClientManager(base_url=base_url) as client:
                    response_text = await client.send_query(query)

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        result = {
            "research_brief": "",
            "raw_notes_count": 0,
            "compressed_notes_count": 0,
            "final_report": response_text or "",
            "context_complexity": "낮음 (평면적 구조)",
            "execution_mode": "분산식 (A2A로 그래프 래핑)",
        }

        # 선택: 최종 결과에 대해 HITL 최종 승인 요청/대기 (단순 플로우)
        if enable_hitl and result["final_report"]:
            try:
                from src.hitl.manager import hitl_manager
                from src.hitl.models import ApprovalType

                request = await hitl_manager.request_approval(
                    agent_id="a2a_deep_research",
                    approval_type=ApprovalType.FINAL_REPORT,
                    title="최종 보고서 승인 요청",
                    description="A2A 기반 연구 보고서 검토 및 최종 승인 요청",
                    context={
                        "task_id": f"a2a_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        "research_topic": query,
                        "final_report": result["final_report"],
                        "execution_mode": result["execution_mode"],
                    },
                    options=["승인", "거부"],
                    timeout_seconds=approval_timeout_seconds,
                    priority="high",
                )

                approved = await hitl_manager.wait_for_approval(
                    request.request_id, auto_approve_on_timeout=False
                )

                result["approval"] = {
                    "request_id": approved.request_id,
                    "status": approved.status.value,
                    "decision": approved.decision,
                    "decided_by": approved.decided_by,
                    "reason": approved.decision_reason,
                }
            except Exception as e:
                # HITL 환경이 준비되지 않은 경우에도 비교 실험은 계속
                result["approval_error"] = f"HITL 처리 실패: {e}"

        print("✅ A2A 딥리서치 실행 완료!")
        print(f"⏱️  실행 시간: {execution_time:.2f}초")
        print(f"📄 결과 길이: {len(str(result))} 문자")
        print("🏗️ Context 복잡성: 낮음 (평면적 구조)")

        return {
            "success": True,
            "execution_time": execution_time,
            "result": result,
            "system_type": "A2A 딥리서치",
            "architecture": "단순한 Context 관리, 분산식, 병렬 실행 가능",
        }

    except Exception as e:
        error_msg = f"A2A 딥리서치 실행 실패: {e}"
        print(f"❌ {error_msg}")

        import traceback

        print("🔍 에러 상세:")
        print(traceback.format_exc())

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        return {
            "success": False,
            "error": error_msg,
            "execution_time": execution_time,
            "system_type": "A2A 딥리서치",
        }


async def check_servers():
    """실행 전 서버 상태 체크 (고급 검증 포함)"""
    print("🔍 시스템 사전 체크 (고급 검증 포함)")
    print("-" * 40)

    try:
        # 고급 검증기 사용
        from examples.deep_research_validator import DeepResearchValidator

        validator = DeepResearchValidator()

        # 기본 검증만 실행 (빠른 체크)
        validation_result = await validator.validate_system(run_full_test=False)

        # 검증 결과를 기존 형식으로 변환
        mcp_running = [
            server.port
            for server in validation_result.mcp_servers
            if server.status.value == "running"
        ]
        a2a_running = validation_result.a2a_server.status.value == "running"

        # 상세 결과 출력
        print("\n📊 고급 검증 결과:")
        for server in validation_result.mcp_servers:
            status_emoji = "✅" if server.status.value == "running" else "❌"
            print(
                f"   {status_emoji} {server.name} (포트 {server.port}): {server.status.value}"
            )
            if server.response_time_ms:
                print(f"      응답시간: {server.response_time_ms:.0f}ms")
            if server.error_message:
                print(f"      오류: {server.error_message}")

        status_emoji = "✅" if a2a_running else "❌"
        print(
            f"   {status_emoji} A2A 서버 (포트 8080): {validation_result.a2a_server.status.value}"
        )
        if validation_result.a2a_server.response_time_ms:
            print(
                f"      응답시간: {validation_result.a2a_server.response_time_ms:.0f}ms"
            )
        if validation_result.a2a_server.error_message:
            print(f"      오류: {validation_result.a2a_server.error_message}")

        # 권장사항이 있으면 출력
        if (
            validation_result.recommendations
            and len(validation_result.recommendations) > 1
        ):
            print("\n💡 권장사항:")
            for rec in validation_result.recommendations[:3]:  # 처음 3개만
                if rec.strip():
                    print(f"   {rec}")

        return {
            "mcp_servers": mcp_running,
            "a2a_server": a2a_running,
            "validation_result": validation_result,
        }

    except ImportError:
        return await check_servers_basic()
    except Exception:
        return await check_servers_basic()


async def check_servers_basic():
    """기본 서버 상태 체크"""
    # MCP 서버 체크 (3000, 3001, 3002 포트)
    import socket

    mcp_ports = [3000, 3001, 3002]
    mcp_running = []

    for port in mcp_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result == 0:
                mcp_running.append(port)
                print(f"✅ MCP 서버 포트 {port}: 실행 중")
            else:
                print(f"❌ MCP 서버 포트 {port}: 실행 안됨")
        except Exception:
            print(f"❌ MCP 서버 포트 {port}: 연결 실패")

    # A2A 서버 체크 (8080 포트)
    a2a_running = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 8080))
        sock.close()

        if result == 0:
            a2a_running = True
            print("✅ A2A 서버 포트 8080: 실행 중")
        else:
            print("❌ A2A 서버 포트 8080: 실행 안됨")
    except Exception:
        print("❌ A2A 서버 포트 8080: 연결 실패")

    print("\n📊 체크 결과:")
    print(f"   MCP 서버: {len(mcp_running)}/{len(mcp_ports)} 개 실행 중")
    print(f"   A2A 서버: {'실행 중' if a2a_running else '실행 안됨'}")

    return {"mcp_servers": mcp_running, "a2a_server": a2a_running}


async def run_comparison(endpoints: dict[str, str] | None = None):
    """LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교"""

    query = "AI가 교육에 미치는 영향을 분석해주세요"

    print("🎯 LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교")
    print("=" * 80)
    print(f"📋 연구 주제: {query}")
    print(f"🕐 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("📝 비교 대상:")
    print("   🔴 LangGraph 딥리서치: StateGraph로 상태 관리, 중앙 집중식")
    print("   🔵 A2A 딥리서치: Context로 상태 전달, 분산식")
    print("   🤝 공통점: 동일한 프롬프트 사용, 동일한 논리 흐름")
    print()

    # 서버 상태 사전 체크
    server_status = await check_servers()
    print()

    # MCP 서버가 실행 중이지 않으면 경고
    if not server_status["mcp_servers"]:
        print("⚠️  경고: MCP 서버가 실행되지 않았습니다.")
        print("   MCP 서버 실행: docker-compose -f docker-compose.mcp.yml up")
        print()

    # 전체 실험 시작 시간
    total_start = datetime.now()

    # 1. LangGraph 딥리서치 실행
    langgraph_result = await run_langgraph_deep_research(query)

    # 잠시 대기 (시스템 간 격리)
    await asyncio.sleep(1)

    # 2. A2A 딥리서치 실행
    a2a_result = await run_a2a_deep_research(query, endpoints=endpoints)

    # 전체 실험 완료
    total_end = datetime.now()
    total_time = (total_end - total_start).total_seconds()

    # 결과 비교 출력
    print("\n" + "=" * 80)
    print("📊 실행 결과 비교")
    print("=" * 80)

    print(f"🕐 전체 실험 시간: {total_time:.2f}초")
    print()

    # LangGraph 딥리서치 결과
    print("🔴 LangGraph 딥리서치:")
    if langgraph_result["success"]:
        print("   ✅ 성공")
        print(f"   ⏱️  실행시간: {langgraph_result['execution_time']:.2f}초")
        print(f"   🏗️  아키텍처: {langgraph_result['architecture']}")
        print(
            f"   📄 결과 크기: {len(langgraph_result['result'].get('final_report', ''))} 문자"
        )
    else:
        print(f"   ❌ 실패: {langgraph_result['error']}")
        print(f"   ⏱️  실패까지 시간: {langgraph_result.get('execution_time', 0):.2f}초")

    print()

    # A2A 딥리서치 결과
    print("🔵 A2A 딥리서치:")
    if a2a_result["success"]:
        print("   ✅ 성공")
        print(f"   ⏱️  실행시간: {a2a_result['execution_time']:.2f}초")
        print(f"   🏗️  아키텍처: {a2a_result['architecture']}")
        print(
            f"   📄 결과 크기: {len(a2a_result['result'].get('final_report', ''))} 문자"
        )
    else:
        print(f"   ❌ 실패: {a2a_result['error']}")
        print(f"   ⏱️  실패까지 시간: {a2a_result.get('execution_time', 0):.2f}초")

    # 실패 원인 분석
    if not langgraph_result["success"] or not a2a_result["success"]:
        print("\n🔍 실패 원인 분석:")

        if not server_status["mcp_servers"]:
            print("   📡 MCP 서버가 실행되지 않음")
            print("      → Docker로 MCP 서버를 먼저 시작하세요")

        if not server_status["a2a_server"]:
            print("   🌐 A2A 서버가 실행되지 않음")
            print(
                "      → 그래프 기반 임베디드 서버 사용 권장: start_embedded_graph_server(...)"
            )

        if langgraph_result["success"] and not a2a_result["success"]:
            print("   🎯 LangGraph 성공, A2A 실패:")
            print("      → A2A는 독립적 에이전트 구조로 복잡성 증가")
            print("      → LangGraph는 중앙 집중식으로 더 안정적")

    # 성공한 경우, 성능 비교만 출력
    if langgraph_result["success"] and a2a_result["success"]:
        print("\n📈 성능 분석:")
        langgraph_time = langgraph_result["execution_time"]
        a2a_time = a2a_result["execution_time"]

        if langgraph_time > a2a_time:
            improvement = ((langgraph_time - a2a_time) / langgraph_time) * 100
            print(f"   🚀 A2A가 {improvement:.1f}% 빠름")
            print(f"      LangGraph: {langgraph_time:.2f}초 → A2A: {a2a_time:.2f}초")
        else:
            overhead = ((a2a_time - langgraph_time) / langgraph_time) * 100
            print(f"   📡 A2A 오버헤드: {overhead:.1f}%")
            print(f"      LangGraph: {langgraph_time:.2f}초 → A2A: {a2a_time:.2f}초")

    # 결과를 JSON으로 저장
    comparison_result = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "total_experiment_time": total_time,
        "server_status": server_status,
        "langgraph_deep_research": langgraph_result,
        "a2a_deep_research": a2a_result,
        "comparison_type": "LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교",
    }

    # 결과를 reports/ 폴더에 날짜 포함 파일명으로 저장
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"comparison_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = reports_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison_result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 상세 결과가 {output_path}에 저장되었습니다.")
    print(f"🏁 실험 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 호출자에서 경로를 알 수 있도록 반환 데이터에 포함
    comparison_result["output_path"] = str(output_path)
    return comparison_result


if __name__ == "__main__":
    print("🚀 LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교")
    print("복잡한 State 관리 vs 단순한 Context 관리\n")

    try:
        result = asyncio.run(run_comparison())
        print("\n✅ 모든 실험이 완료되었습니다!")

    except KeyboardInterrupt:
        print("\n⏹️  사용자에 의해 중단되었습니다.")

    except Exception as e:
        print(f"\n💥 예상치 못한 오류: {e}")
        import traceback

        traceback.print_exc()
