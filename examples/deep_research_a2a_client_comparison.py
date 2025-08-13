# ruff: noqa: E402
"""
Deep Research A2A Client 기반 품질 및 성능 비교 스크립트

LangGraph와 A2A SDK 전체 스택의 완전한 비교를 수행합니다.

비교 항목:
1. 단계별/에이전트별 실행 시간
2. MCP 도구 사용 패턴  
3. 병렬 처리 효과
4. 보고서 품질 메트릭
5. 리소스 사용량

A2A 부분은 A2A Client를 통해 Deep Research A2A Server에 요청을 보냅니다.
"""

import asyncio
import json
import time
import re
import subprocess
import sys
import socket
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
import os

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import httpx
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# A2A Client imports
from a2a.client import ClientFactory, A2ACardResolver, ClientConfig
from a2a.client.helpers import create_text_message_object
from a2a.types import AgentCard, TransportProtocol, Role, Message

# 프로젝트 루트의 .env 파일 로드
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class PerformanceTracker:
    """성능 추적을 위한 유틸리티 클래스"""
    
    def __init__(self):
        self.events = []
        self.start_time = time.time()
    
    def log_event(self, event_type: str, event_name: str, data: Dict[str, Any] = None):
        """이벤트 로그"""
        self.events.append({
            "timestamp": time.time() - self.start_time,
            "type": event_type,
            "name": event_name,
            "data": data or {}
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """성능 요약"""
        stage_times = defaultdict(float)
        stage_counts = defaultdict(int)
        
        for i in range(len(self.events) - 1):
            if self.events[i]["type"] == "stage_start":
                for j in range(i + 1, len(self.events)):
                    if (self.events[j]["type"] == "stage_end" and 
                        self.events[j]["name"] == self.events[i]["name"]):
                        duration = self.events[j]["timestamp"] - self.events[i]["timestamp"]
                        stage_times[self.events[i]["name"]] += duration
                        stage_counts[self.events[i]["name"]] += 1
                        break
        
        return {
            "total_time": time.time() - self.start_time,
            "stage_times": dict(stage_times),
            "stage_counts": dict(stage_counts),
            "events": self.events
        }


class ReportQualityAnalyzer:
    """보고서 품질 분석기"""
    
    @staticmethod
    def analyze_report(report: str) -> Dict[str, Any]:
        """보고서 품질 메트릭 분석"""
        if not report:
            return {
                "word_count": 0,
                "sentence_count": 0,
                "paragraph_count": 0,
                "section_count": 0,
                "subsection_count": 0,
                "reference_count": 0,
                "bullet_points": 0,
                "code_blocks": 0,
                "avg_sentence_length": 0,
                "structure_score": 0
            }
        
        # 기본 메트릭
        words = report.split()
        word_count = len(words)
        
        # 문장 수 (마침표, 느낌표, 물음표 기준)
        sentences = re.split(r'[.!?]+', report)
        sentence_count = len([s for s in sentences if s.strip()])
        
        # 단락 수
        paragraphs = report.split('\n\n')
        paragraph_count = len([p for p in paragraphs if p.strip()])
        
        # 섹션 수 (# 제목)
        sections = re.findall(r'^#\s+.+$', report, re.MULTILINE)
        section_count = len(sections)
        
        # 하위 섹션 수 (## 제목)
        subsections = re.findall(r'^##\s+.+$', report, re.MULTILINE)
        subsection_count = len(subsections)
        
        # 참조/인용 수 (대괄호 링크 형식)
        references = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', report)
        reference_count = len(references)
        
        # 글머리 기호
        bullet_points = len(re.findall(r'^\s*[-*]\s+', report, re.MULTILINE))
        
        # 코드 블록
        code_blocks = len(re.findall(r'```[\s\S]*?```', report))
        
        # 평균 문장 길이
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        
        # 구조화 점수 (0-100)
        structure_score = min(100, (
            (section_count * 10) +
            (subsection_count * 5) +
            (paragraph_count * 2) +
            (bullet_points * 1) +
            (reference_count * 3)
        ))
        
        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "paragraph_count": paragraph_count,
            "section_count": section_count,
            "subsection_count": subsection_count,
            "reference_count": reference_count,
            "bullet_points": bullet_points,
            "code_blocks": code_blocks,
            "avg_sentence_length": round(avg_sentence_length, 2),
            "structure_score": structure_score
        }


def is_port_in_use(host: str = "localhost", port: int = 8090) -> bool:
    """포트 사용 중인지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
        except Exception:
            return False


async def check_server_running(host: str = "localhost", port: int = 8090) -> bool:
    """실행 중인 서버 확인 (헬스 체크)"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{host}:{port}/health", timeout=3.0)
            return response.status_code == 200
    except Exception:
        return False


async def get_server_status(host: str = "localhost", port: int = 8090) -> Dict[str, Any]:
    """서버 상태 상세 정보"""
    port_in_use = is_port_in_use(host, port)
    server_responding = await check_server_running(host, port)
    
    status = {
        "port_in_use": port_in_use,
        "server_responding": server_responding,
        "host": host,
        "port": port
    }
    
    if port_in_use and not server_responding:
        status["issue"] = "포트는 사용 중이지만 헬스 체크 실패"
    elif not port_in_use and not server_responding:
        status["issue"] = "서버가 실행되지 않음"
    elif server_responding:
        status["status"] = "정상 작동 중"
    
    return status


async def start_deep_research_a2a_server() -> Optional[subprocess.Popen]:
    """그래프 기반 임베디드 서버 사용 권장: 외부 프로세스 시작 대신 임베디드 사용"""
    print("ℹ️  권장: start_embedded_graph_server를 사용하세요 (임베디드 서버)")
    return None


async def run_langgraph_with_tracking(query: str) -> Tuple[Dict[str, Any], PerformanceTracker]:
    """LangGraph 실행 with 상세 추적"""
    tracker = PerformanceTracker()
    
    try:
        tracker.log_event("system_start", "LangGraph")
        
        # Import
        tracker.log_event("stage_start", "import")
        from src.lg_agents.deep_research_agent import deep_research_graph
        tracker.log_event("stage_end", "import")
        
        # 그래프 준비
        tracker.log_event("stage_start", "graph_setup")
        app = deep_research_graph
        tracker.log_event("stage_end", "graph_setup")
        
        # 실행 (스트리밍으로 각 단계 추적)
        tracker.log_event("stage_start", "total_execution")
        
        step_results = {}
        async for event in app.astream({"messages": [HumanMessage(content=query)]}):
            for node_name, node_output in event.items():
                tracker.log_event("node_start", node_name)
                
                # 노드별 결과 저장
                if isinstance(node_output, dict):
                    step_results[node_name] = {
                        "output_size": len(str(node_output)),
                        "keys": list(node_output.keys()) if isinstance(node_output, dict) else []
                    }
                    
                    # 특정 노드 상세 정보
                    if node_name == "research_supervisor":
                        if "raw_notes" in node_output:
                            tracker.log_event("data", "raw_notes_generated", {
                                "count": len(node_output.get("raw_notes", [])),
                                "size": sum(len(note) for note in node_output.get("raw_notes", []))
                            })
                    
                    if node_name == "final_report_generation":
                        if "final_report" in node_output:
                            tracker.log_event("data", "final_report_generated", {
                                "size": len(node_output.get("final_report", ""))
                            })
                
                tracker.log_event("node_end", node_name)
                
                # 최종 결과 저장
                if isinstance(node_output, dict) and "final_report" in node_output:
                    final_result = node_output
        
        tracker.log_event("stage_end", "total_execution")
        tracker.log_event("system_end", "LangGraph")
        
        return {
            "success": True,
            "final_report": final_result.get("final_report", "") if 'final_result' in locals() else "",
            "step_results": step_results,
            "raw_notes": final_result.get("raw_notes", []) if 'final_result' in locals() else [],
            "notes": final_result.get("notes", []) if 'final_result' in locals() else []
        }, tracker
        
    except Exception as e:
        tracker.log_event("error", "system_error", {"error": str(e)})
        return {
            "success": False,
            "error": str(e),
            "final_report": ""
        }, tracker


async def run_a2a_with_tracking(query: str) -> Tuple[Dict[str, Any], PerformanceTracker]:
    """A2A Client를 통한 Deep Research 실행 with 상세 추적"""
    tracker = PerformanceTracker()
    
    try:
        tracker.log_event("system_start", "A2A_Client")
        
        # A2A Client 생성
        tracker.log_event("stage_start", "client_setup")
        # httpx.AsyncClient는 with 블록으로 수명 주기를 좁혀 커넥션 누수 방지
        async with httpx.AsyncClient() as aio:
            resolver = A2ACardResolver(
                httpx_client=aio,
                base_url="http://localhost:8092",
            )
            agent_card: AgentCard = await resolver.get_agent_card()
        # resolver.get_agent_card() 이후에는 ClientFactory가 내부 클라이언트를 관리
        config = ClientConfig(
            streaming=True,
            supported_transports=[TransportProtocol.jsonrpc, TransportProtocol.http_json, TransportProtocol.grpc],
        )
        factory = ClientFactory(config=config)
        client = factory.create(card=agent_card)
        tracker.log_event("stage_end", "client_setup")
        
        # 에이전트 정보 확인
        tracker.log_event("stage_start", "agent_info")
        print("🔵 A2A 에이전트 정보:")
        print(f"   - 이름: {agent_card.name}")
        print(f"   - 설명: {agent_card.description}")
        print(f"   - 지원 프로토콜: {agent_card.capabilities.streaming}")
        print("   - 기능:")
        for skill in agent_card.skills:
            print(f"     * {skill.name}: {skill.description}")
        tracker.log_event("stage_end", "agent_info")
        
        # A2A 요청 전송
        tracker.log_event("stage_start", "a2a_request")
        print(f"\\n🔵 A2A Deep Research 요청 전송: {query}")
        
        message: Message = create_text_message_object(
            role=Role.user,
            content=query
        )
        
        # A2A 응답 처리 및 추적
        response_text = ""
        step_events = []
        
        async for event in client.send_message(message):
            # A2A 이벤트는 복잡한 tuple 구조로 옴: (Task, Event)
            if isinstance(event, tuple) and len(event) >= 1:
                task = event[0]  # 첫 번째는 Task 객체
                
                # Task에서 artifacts 확인 (최종 응답)
                if hasattr(task, 'artifacts') and task.artifacts:
                    for artifact in task.artifacts:
                        if hasattr(artifact, 'parts') and artifact.parts:
                            for part in artifact.parts:
                                root = getattr(part, 'root', None)
                                text_content = getattr(root, 'text', None)
                                if isinstance(text_content, str):
                                    if text_content not in response_text:
                                        response_text += text_content + "\n"
                
                # Task history에서 중간 메시지들 확인 (진행 과정)
                if hasattr(task, 'history') and task.history:
                    # 마지막 메시지만 처리 (중복 방지)
                    last_message = task.history[-1]
                    if (hasattr(last_message, 'role') and 
                        last_message.role.value == 'agent' and
                        hasattr(last_message, 'parts') and last_message.parts):
                        
                        for part in last_message.parts:
                            root = getattr(part, 'root', None)
                            text_content = getattr(root, 'text', None)
                            if isinstance(text_content, str) and text_content not in response_text:
                                response_text += text_content + "\n"
                                step_events.append({
                                    "timestamp": time.time() - tracker.start_time,
                                    "event": text_content
                                })
                                print(f"[A2A 진행] {text_content}")
        
        tracker.log_event("stage_end", "a2a_request")        
        tracker.log_event("system_end", "A2A_Client")
        
        # step2 패턴: 단순 텍스트 응답 처리
        if response_text.strip():
            return {
                "success": True,
                "final_report": response_text.strip(),
                "raw_response": response_text,
                "step_events": step_events
            }, tracker
        else:
            print("⚠️ 빈 응답 수신됨")
            return {
                "success": False,
                "error": "빈 응답 수신",
                "final_report": "",
                "raw_response": response_text,
                "step_events": step_events
            }, tracker
            
    except Exception as e:
        tracker.log_event("error", "system_error", {"error": str(e)})
        return {
            "success": False,
            "error": str(e),
            "final_report": ""
        }, tracker


async def compare_systems():
    """두 시스템 상세 비교"""
    query = "AI가 교육에 미치는 영향을 분석해주세요"
    
    print("🔬 Deep Research A2A Client 기반 품질 및 성능 비교")
    print("=" * 80)
    print(f"📋 연구 주제: {query}")
    print(f"🕐 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # A2A 서버 상태 확인 및 시작
    print("\\n🔵 Deep Research A2A 서버 준비 중...")
    server_process = await start_deep_research_a2a_server()
    server_started_by_us = server_process is not None
    
    # 서버 가용성 최종 확인
    if not await check_server_running():
        print("❌ A2A 서버를 사용할 수 없습니다 - A2A 비교를 건너뜁니다.")
        print("💡 해결 방법:")
        print("   1. 권장: 임베디드 그래프 서버 사용 (start_embedded_graph_server)")
        print("   2. 포트 8090이 사용 중인지 확인: lsof -i :8090")
        print("   3. 환경 변수가 올바르게 설정되었는지 확인")
        return
    
    print("✅ A2A 서버 사용 준비 완료")
    if not server_started_by_us:
        print("📝 참고: 기존에 실행 중인 서버를 재사용합니다")
    
    try:
        # LangGraph 실행
        print("\\n🔴 LangGraph Deep Research 실행 중...")
        lg_result, lg_tracker = await run_langgraph_with_tracking(query)
        lg_performance = lg_tracker.get_summary()
        
        # 잠시 대기
        await asyncio.sleep(2)
        
        # A2A 실행
        print("\\n🔵 A2A Deep Research (Client 기반) 실행 중...")
        a2a_result, a2a_tracker = await run_a2a_with_tracking(query)
        a2a_performance = a2a_tracker.get_summary()
        
        # 보고서 품질 분석
        print("\\n📊 보고서 품질 분석 중...")
        lg_quality = ReportQualityAnalyzer.analyze_report(lg_result.get("final_report", ""))
        a2a_quality = ReportQualityAnalyzer.analyze_report(a2a_result.get("final_report", ""))
        
        # 결과 출력
        print("\\n" + "=" * 80)
        print("📈 성능 비교 결과")
        print("=" * 80)
        
        # 1. 실행 시간 비교
        print("\\n⏱️  실행 시간 비교:")
        print(f"   🔴 LangGraph: {lg_performance['total_time']:.2f}초")
        if lg_performance['stage_times']:
            for stage, time in lg_performance['stage_times'].items():
                print(f"      - {stage}: {time:.2f}초")
        
        print(f"\\n   🔵 A2A (Client): {a2a_performance['total_time']:.2f}초")
        if a2a_performance['stage_times']:
            for stage, time in a2a_performance['stage_times'].items():
                print(f"      - {stage}: {time:.2f}초")
        
        # A2A 내부 성능 통계 출력
        if a2a_result.get("performance_stats"):
            stats = a2a_result["performance_stats"]
            print("\\n   🔵 A2A 내부 단계별 시간:")
            for key, value in stats.items():
                if key.endswith('_time') and isinstance(value, (int, float)):
                    print(f"      - {key.replace('_time', '')}: {value:.2f}초")
            
            # 병렬 처리 효과 계산
            if 'parallel_research_time' in stats and stats['parallel_research_time'] > 0:
                estimated_sequential = stats['parallel_research_time'] * stats.get('total_researchers', 3)
                speedup = estimated_sequential / stats['parallel_research_time']
                print(f"\\n   🚀 병렬 처리 효과: {speedup:.2f}x 속도 향상 (예상)")
        
        # 2. 보고서 품질 비교
        print("\\n📝 보고서 품질 비교:")
        print("\\n   🔴 LangGraph:")
        for metric, value in lg_quality.items():
            print(f"      - {metric}: {value}")
        
        print("\\n   🔵 A2A:")
        for metric, value in a2a_quality.items():
            print(f"      - {metric}: {value}")
        
        # 3. MCP 도구 사용 분석
        print("\\n🔧 MCP 도구 사용 분석:")
        print("   🔴 LangGraph:")
        lg_raw_notes = lg_result.get("raw_notes", [])
        lg_mcp_usage = analyze_mcp_usage(lg_raw_notes)
        for tool, count in lg_mcp_usage.items():
            print(f"      - {tool}: {count}회 사용")
        
        print("\\n   🔵 A2A:")
        a2a_raw_notes = a2a_result.get("raw_research_notes", [])
        a2a_mcp_usage = analyze_mcp_usage(a2a_raw_notes)
        for tool, count in a2a_mcp_usage.items():
            print(f"      - {tool}: {count}회 사용")
        
        # 4. 종합 평가
        print("\\n🏆 종합 평가:")
        
        # 속도 우위
        speed_winner = "LangGraph" if lg_performance['total_time'] < a2a_performance['total_time'] else "A2A"
        speed_diff = abs(lg_performance['total_time'] - a2a_performance['total_time'])
        print(f"   ⚡ 속도: {speed_winner}가 {speed_diff:.2f}초 빠름")
        
        # 품질 우위
        lg_score = lg_quality['structure_score'] + (lg_quality['word_count'] / 100)
        a2a_score = a2a_quality['structure_score'] + (a2a_quality['word_count'] / 100)
        quality_winner = "LangGraph" if lg_score > a2a_score else "A2A"
        print(f"   📊 품질 점수: LangGraph({lg_score:.1f}) vs A2A({a2a_score:.1f})")
        
        # 상세 결과 저장
        detailed_results = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "langgraph": {
                "success": lg_result.get("success", False),
                "performance": lg_performance,
                "quality": lg_quality,
                "mcp_usage": lg_mcp_usage,
                "report_preview": lg_result.get("final_report", "")[:500] + "..." if lg_result.get("final_report") else ""
            },
            "a2a": {
                "success": a2a_result.get("success", False),
                "performance": a2a_performance,
                "quality": a2a_quality,
                "mcp_usage": a2a_mcp_usage,
                "internal_stats": a2a_result.get("performance_stats", {}),
                "step_events": a2a_result.get("step_events", []),
                "report_preview": a2a_result.get("final_report", "")[:500] + "..." if a2a_result.get("final_report") else ""
            },
            "comparison": {
                "speed_winner": speed_winner,
                "speed_difference": speed_diff,
                "quality_winner": quality_winner,
                "lg_quality_score": lg_score,
                "a2a_quality_score": a2a_score
            }
        }
        
        # JSON 파일로 저장
        with open("deep_research_a2a_client_comparison.json", "w", encoding="utf-8") as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=2)
        
        print("\\n💾 상세 결과가 deep_research_a2a_client_comparison.json에 저장되었습니다.")
        
        # 보고서 전문 저장
        if lg_result.get("final_report"):
            with open("langgraph_report_client_comparison.md", "w", encoding="utf-8") as f:
                f.write(lg_result["final_report"])
            print("📄 LangGraph 보고서가 langgraph_report_client_comparison.md에 저장되었습니다.")
        
        if a2a_result.get("final_report"):
            with open("a2a_report_client_comparison.md", "w", encoding="utf-8") as f:
                f.write(a2a_result["final_report"])
            print("📄 A2A 보고서가 a2a_report_client_comparison.md에 저장되었습니다.")
    
    finally:
        # A2A 서버 종료 (우리가 시작한 서버만)
        if server_process and server_started_by_us:
            print("\\n🔵 A2A 서버 종료 중...")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
                print("✅ A2A 서버가 정상적으로 종료되었습니다")
            except subprocess.TimeoutExpired:
                print("⚠️  서버 종료 타임아웃 - 강제 종료합니다")
                server_process.kill()
                server_process.wait()
        elif not server_started_by_us:
            print("\\n📝 참고: 기존 서버는 그대로 유지됩니다")


def analyze_mcp_usage(notes: List[str]) -> Dict[str, int]:
    """MCP 도구 사용 분석"""
    usage = {"Tavily": 0, "arXiv": 0, "Serper": 0}
    
    for note in notes:
        if isinstance(note, str):
            if "[Tavily]" in note or "[tavily]" in note:
                usage["Tavily"] += 1
            if "[arXiv]" in note or "[arxiv]" in note:
                usage["arXiv"] += 1
            if "[Serper]" in note or "[serper]" in note:
                usage["Serper"] += 1
    
    return usage


if __name__ == "__main__":
    print("🚀 Deep Research A2A Client 기반 품질 및 성능 비교 시작")
    print("""
    📌 실행 전 확인사항:
    1. MCP 서버가 Docker에서 실행 중인지 확인 (Tavily:3001, arXiv:3002, Serper:3003)
    2. OPENAI_API_KEY, TAVILY_API_KEY, SERPER_API_KEY 환경변수가 설정되어 있는지 확인
    
    📌 A2A 서버 자동 관리:
    - 이미 실행 중인 A2A 서버가 있으면 재사용합니다
    - 실행 중인 서버가 없으면 자동으로 새 서버를 시작합니다
    - 비교 완료 후 우리가 시작한 서버만 종료합니다
    
    📌 A2A Client 기반 비교:
    - LangGraph Deep Research는 기존 방식으로 실행
    - A2A Deep Research는 A2A Client를 통해 Deep Research A2A Server에 요청
    - 완전한 orchestration과 병렬 처리 성능을 비교
    
    💡 서버 충돌 시 해결 방법:
    - 포트 충돌: lsof -ti:8090 | xargs kill -9
    - 권장: 임베디드 그래프 서버 사용 (start_embedded_graph_server)
    """)
    
    try:
        asyncio.run(compare_systems())
    except KeyboardInterrupt:
        print("\\n\\n프로그램이 중단되었습니다.")
    except Exception as e:
        print(f"\\n❌ 오류 발생: {e}")
        print("\\n🔧 문제 해결 가이드:")
        print("1. MCP 서버 확인:")
        print("   docker ps | grep mcp")
        print("   docker-compose -f docker-compose.mcp.yml up -d")
        print("\\n2. A2A 서버 포트 충돌 해결:")
        print("   lsof -ti:8090 | xargs kill -9")
        print("   (권장) 임베디드 그래프 서버 사용: start_embedded_graph_server")
        print("\\n3. 환경 변수 확인:")
        print("   echo $OPENAI_API_KEY")
        print("   echo $TAVILY_API_KEY") 
        print("   echo $SERPER_API_KEY")
        print("\\n4. 상세 디버깅:")
        print("   python -c 'import asyncio; from examples.deep_research_a2a_client_comparison import get_server_status; print(asyncio.run(get_server_status()))'")
        
        # 서버 상태 자동 확인
        try:
            import asyncio
            status = asyncio.run(get_server_status())
            print(f"\\n📊 현재 서버 상태: {status}")
        except Exception:
            pass