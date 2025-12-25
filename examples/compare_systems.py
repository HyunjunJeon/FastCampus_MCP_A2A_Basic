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

# 프로젝트 루트 설정 (절대경로로 고정하여 실행 CWD와 무관하게 저장되도록 함)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 파일 로드 (override=True로 기존 환경변수 덮어쓰기)
load_dotenv(PROJECT_ROOT / ".env", override=True)

# 로깅 설정
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def run_langgraph_deep_research(query: str):
    """LangGraph 딥리서치 구현체 실행 (복잡한 State 관리)"""
    print("\n" + "=" * 80)
    print("[INFO] LangGraph 딥리서치 구현체 실행")
    print("=" * 80)

    start_time = datetime.now()

    try:
        print("[INFO] LangGraph 딥리서치 에이전트 임포트 중...")
        # LangGraph 기반 딥리서치 에이전트 (복잡한 State 관리)
        from src.lg_agents.deep_research.deep_research_agent import deep_research_graph
        from langchain_core.messages import HumanMessage

        print(f"[INFO] 딥리서치 쿼리 실행: {query}")
        print("[INFO] LangGraph 복잡한 State 관리로 실행 중...")

        # 실제 LangGraph 딥리서치 실행
        result = await deep_research_graph.ainvoke(
            {"messages": [HumanMessage(content=query)]}
        )

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        print("[SUCCESS] LangGraph 딥리서치 실행 완료!")
        print(f"[INFO] 실행 시간: {execution_time:.2f}초")
        print(f"[INFO] 결과 길이: {len(str(result))} 문자")

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
            "system_type": "LangGraph",
            "architecture": "복잡한 State 관리, 중앙 집중식, 순차 실행",
        }

    except Exception as e:
        error_msg = f"LangGraph 딥리서치 실행 실패: {e}"
        print(f"[ERROR] {error_msg}")

        import traceback

        print("[INFO] 에러 상세:")
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
    print("[INFO] A2A 딥리서치 구현체 실행")
    print("=" * 80)

    start_time = datetime.now()

    try:
        from src.a2a_integration.a2a_lg_client_utils import A2AClientManager

        # 외부에서 엔드포인트가 주어지면 그대로 사용 (이미 띄워진 서버)
        if endpoints and isinstance(endpoints, dict) and endpoints.get("deep_research"):
            base_url = endpoints["deep_research"]
            logger.info(
                f"[INFO] 외부 제공 A2A 엔드포인트 사용(DeepResearchA2AGraph): {base_url}"
            )

            graph_input = {
                "messages": [
                    {"role": "human", "content": query},
                ],
            }

            logger.info(
                f"DeepResearchGraph 스펙에 맞는 데이터 Input 을 위해 전처리: {graph_input}"
            )
            async with A2AClientManager(base_url=base_url) as client:
                merged = await client.send_data_merged(graph_input)

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        final_report_text = ""
        try:
            if isinstance(merged, dict):
                # 구조화 결과에서 우선적으로 final_report를 찾는다
                final_report_text = str(
                    merged.get("final_report") or merged.get("text") or ""
                )
            else:
                final_report_text = str(merged)
        except Exception:
            final_report_text = str(merged)

        logger.info(f"A2A 딥리서치 결과 길이: {len(final_report_text)}")
        result = {
            "research_brief": "",
            "raw_notes_count": 0,
            "compressed_notes_count": 0,
            "final_report": final_report_text,
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

        print("[SUCCESS] A2A 딥리서치 실행 완료!")
        print(f"[INFO] 실행 시간: {execution_time:.2f}초")
        print(f"[INFO] 결과 길이: {len(str(result))} 문자")
        print("[INFO] Context 복잡성: 낮음 (평면적 구조)")

        return {
            "success": True,
            "execution_time": execution_time,
            "result": result,
            "system_type": "A2A 딥리서치",
            "architecture": "단순한 Context 관리, 분산식, 병렬 실행 가능",
        }

    except Exception as e:
        error_msg = f"A2A 딥리서치 실행 실패: {e}"
        print(f"[ERROR] {error_msg}")

        import traceback

        print("[INFO] 에러 상세:")
        print(traceback.format_exc())

        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        return {
            "success": False,
            "error": error_msg,
            "execution_time": execution_time,
            "system_type": "A2A 딥리서치",
        }


async def check_servers_basic():
    """기본 서버 상태 체크 (MCP + 기본 A2A Supervisor 포트)"""
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
                print(f"[SUCCESS] MCP 서버 포트 {port}: 실행 중")
            else:
                print(f"[ERROR] MCP 서버 포트 {port}: 실행 안됨")
        except Exception:
            print(f"[ERROR] MCP 서버 포트 {port}: 연결 실패")

    # A2A Supervisor 기본 포트(8090) 헬스체크
    a2a_healthy = False
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8090/health", timeout=1.5)
            a2a_healthy = resp.status_code == 200
    except Exception:
        a2a_healthy = False

    print("\n[INFO] 체크 결과:")
    print(f"   MCP 서버: {len(mcp_running)}/{len(mcp_ports)} 개 실행 중")
    print(f"   A2A Supervisor(8090): {'정상' if a2a_healthy else '비정상/미실행'}")

    return {"mcp_servers": mcp_running, "a2a_server": a2a_healthy}


async def run_comparison(
    query: str,
    endpoints: dict[str, str] | None = None,
    langgraph_run: bool = True,
    a2a_run: bool = True,
):
    """LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교"""

    print("[INFO] LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교")
    print("=" * 80)
    print(f"[INFO] 연구 주제: {query}")
    print(f"[INFO] 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("[INFO] 비교 대상:")
    print("   [INFO] LangGraph 딥리서치: StateGraph로 상태 관리, 중앙 집중식")
    print("   [INFO] A2A 딥리서치: Context로 상태 전달, 분산식")
    print("   [INFO] 공통점: 동일한 프롬프트 사용, 동일한 논리 흐름")
    print()

    # 서버 상태 사전 체크
    server_status = await check_servers_basic()
    print()

    # MCP 서버가 실행 중이지 않으면 경고
    if not server_status["mcp_servers"]:
        print("[WARNING]  경고: MCP 서버가 실행되지 않았습니다.")
        print("   MCP 서버 실행: docker-compose -f docker-compose.mcp.yml up")
        print()

    # 전체 실험 시작 시간
    total_start = datetime.now()

    if langgraph_run:
        # 1. LangGraph 딥리서치 실행
        langgraph_result = await run_langgraph_deep_research(query)
        # 잠시 대기 (시스템 간 격리를 위함)
        await asyncio.sleep(2)

    if a2a_run:
        # 2. A2A 딥리서치 실행
        a2a_result = await run_a2a_deep_research(query, endpoints=endpoints)

    # 전체 실험 완료
    total_end = datetime.now()
    total_time = (total_end - total_start).total_seconds()

    # 결과 비교 출력
    print("\n" + "=" * 80)
    print("[INFO] 실행 결과 비교")
    print("=" * 80)

    print(f"🕐 전체 실험 시간: {total_time:.2f}초")
    print()

    # LangGraph 딥리서치 결과
    if langgraph_run:
        print("[INFO] LangGraph 딥리서치:")
        if langgraph_result.get("success", False):
            print("   [SUCCESS] 성공")
            print(f"   [INFO] 실행시간: {langgraph_result['execution_time']:.2f}초")
            print(f"   [INFO] 아키텍처: {langgraph_result['architecture']}")
            print(
                f"   [INFO] 결과 크기: {len(langgraph_result['result'].get('final_report', ''))} 문자"
            )
        else:
            print(f"   [ERROR] 실패: {langgraph_result['error']}")
            print(
                f"   [INFO] 실패까지 시간: {langgraph_result.get('execution_time', 0):.2f}초"
            )

    # A2A 딥리서치 결과
    if a2a_run:
        print("\n[INFO] A2A 딥리서치:")
        if a2a_result.get("success", False):
            print("   [SUCCESS] 성공")
            print(f"   [INFO] 실행시간: {a2a_result['execution_time']:.2f}초")
            print(f"   [INFO] 아키텍처: {a2a_result['architecture']}")
            print(
                f"   [INFO] 결과 크기: {len(a2a_result['result'].get('final_report', ''))} 문자"
            )
        else:
            print(f"   [ERROR] 실패: {a2a_result['error']}")
            print(
                f"   [INFO] 실패까지 시간: {a2a_result.get('execution_time', 0):.2f}초"
            )

    # # 실패 원인 분석
    # if langgraph_run or a2a_run:
    #     if not langgraph_result.get("success", False) and not a2a_result.get("success", False):
    #         print("\n🔍 실패 원인 분석:")

    #     if not server_status["mcp_servers"]:
    #         print("   📡 MCP 서버가 실행되지 않음")
    #         print("      → Docker로 MCP 서버를 먼저 시작하세요")

    #     if not server_status["a2a_server"]:
    #         print("   🌐 A2A 서버가 실행되지 않음")
    #         print(
    #             "      → 테스트 용도로는 임베디드 서버 사용 권장: start_embedded_graph_server(...)"
    #         )

    # 결과를 JSON으로 저장
    comparison_result = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "total_experiment_time": total_time,
        "server_status": server_status,
        "langgraph_deep_research": langgraph_result or None,
        "a2a_deep_research": a2a_result or None,
        "comparison_type": "LangGraph 딥리서치 vs A2A 딥리서치 구현체 비교",
    }

    # 결과를 reports/ 폴더에 날짜 포함 파일명으로 저장
    reports_dir = PROJECT_ROOT / "reports" / "step3"
    reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"comparison_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path = reports_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison_result, f, ensure_ascii=False, indent=2)

    print(f"\n[INFO] 상세 결과가 {output_path}에 저장되었습니다.")
    print(f"[SUCCESS] 실험 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 호출자에서 경로를 알 수 있도록 반환 데이터에 포함
    comparison_result["output_path"] = str(output_path)
    return comparison_result
