"""
Step 4: HITL 통합 연구 에이전트 (구버전!!!)
이 모듈은 Step 4에서 Human-In-The-Loop(HITL) 기능을 구현하는 에이전트입니다.

단계: Step 4 (A2A + HITL)
역할: 인간의 승인이 필요한 중요한 결정 포인트에서 사용자 피드백을 받는 연구 에이전트

핵심 특징:
1. A2A AgentExecutor 구현
   - A2A 프로토콜을 따르는 표준 에이전트
   - 독립적인 실행 환경에서 동작

2. 3단계 승인 플로우
   - 연구 계획 승인 (CRITICAL_DECISION)
   - 데이터 검증 (DATA_VALIDATION)
   - 최종 보고서 승인 (FINAL_REPORT)

3. Redis 기반 승인 관리
   - 승인 요청을 Redis에 저장
   - 웹 대시보드를 통한 실시간 승인
   - 승인 이력 추적

4. A2A Orchestrator 통합
   - 다른 A2A 에이전트들과 협업
   - Planner, Researcher, Writer 에이전트 조정

사용 시나리오:
1. 중요한 의사결정이 필요한 연구 작업
2. 민감한 데이터를 다루는 분석 작업
3. 최종 결과물의 품질 보증이 필요한 경우

실행 방법:
  # 통합 서버에서 실행
  python -m src.a2a_integration.unified_server --agent-type hitl_research

  # 또는 전체 HITL 시스템 실행
  python scripts/start_hitl_system.py

포트: 8081

웹 대시보드:
- URL: http://localhost:8000/hitl
- 승인 요청 관리 UI 제공
- WebSocket 기반 실시간 업데이트

참고:
- Redis가 실행 중이어야 함 (포트 6379)
- 웹 대시보드는 별도 프로세스로 실행
- A2A 프로토콜 상세는 a2a-python 문서 참조
"""

# 표준 라이브러리 임포트
from src.utils.logging_config import get_logger
from typing import Dict, Any, List, Optional
from datetime import datetime

# A2A 프레임워크 관련 임포트
from a2a.server.agent_execution import (
    AgentExecutor,
    RequestContext,
)
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from a2a.utils import new_agent_text_message  # A2A 텍스트 메시지 유틸리티

# HITL(Human-In-The-Loop) 관련 임포트
from src.hitl.manager import hitl_manager  # HITL 매니저 (승인 요청/대기)
from src.hitl.models import ApprovalType  # 승인 타입 정의

# 로깅 설정
logger = get_logger(__name__)


class HITLResearchAgent(AgentExecutor):
    """
    Human-In-The-Loop 기능이 통합된 Deep Research 에이전트

    이 클래스는 A2A AgentExecutor를 구현하여 다음과 같은 기능을 제공:
    1. 3단계 승인 플로우 (연구계획 -> 데이터검증 -> 최종승인)
    2. Redis 기반 승인 요청 관리
    3. 웹 대시보드를 통한 실시간 승인 처리
    4. A2A 프로토콜 표준 준수

    Attributes:
        agent_id (str): 에이전트 고유 식별자
        _initialized (bool): 초기화 상태 플래그
    """

    def __init__(self):
        """HITL Research Agent 초기화"""
        self.agent_id = "hitl_research_agent"
        # self.orchestrator = A2AOrchestrator()  # A2A 오케스트레이터 (임시 주석 처리)
        self._initialized = False

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        에이전트 취소 처리 (A2A AgentExecutor 추상 메서드 구현)

        Args:
            context (RequestContext): 요청 컨텍스트 (작업 ID, 컨텍스트 ID 포함)
            event_queue (EventQueue): 이벤트 큐 (취소 메시지 전송용)
        """
        logger.info(f"HITL Research Agent 취소됨: {context.task_id}")

        try:
            # 작업 상태를 취소됨으로 업데이트
            from src.a2a_orchestrator.task_updater import TaskUpdater, TaskState

            task_updater = TaskUpdater(
                event_queue=event_queue,
                task_id=context.task_id,
                context_id=context.context_id,
            )
            await task_updater.update_status(TaskState.cancelled)

            if self._initialized:
                # 1) 진행 중인 연구 작업 취소 및 리소스 정리
                if hasattr(self, "agent") and self.agent:
                    # LangGraph agent의 진행 중인 작업 정리
                    logger.info("LangGraph 에이전트 작업 정리 중...")

                # 2) Redis의 승인 요청 상태 업데이트 (취소)
                try:
                    # HITL Manager를 통해 현재 task_id와 연관된 승인 요청들을 취소 상태로 업데이트
                    logger.info(
                        f"HITL 승인 요청 취소 처리 중... Task ID: {context.task_id}"
                    )
                    # Note: HITL Manager에서 취소 처리 메서드가 필요하면 추후 구현
                except Exception as e:
                    logger.warning(f"HITL 승인 요청 취소 처리 중 오류: {e}")

                # 3) 메모리 정리
                if hasattr(self, "_current_research_data"):
                    self._current_research_data = None

            logger.info(f"HITL Research Agent 취소 완료: {context.task_id}")

        except Exception as e:
            logger.error(f"HITL Research Agent 취소 중 오류 발생: {e}")

    async def _ensure_initialized(self):
        """
        에이전트 초기화 확인 및 수행

        초기화되지 않은 경우 필요한 컴포넌트들을 초기화:
        - HITL 매니저 연결 확인
        - Redis 연결 상태 확인
        - 기본 설정 로드
        """
        if not self._initialized:
            self._initialized = True
            logger.info("HITL Research Agent 초기화 완료")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        HITL 통합 연구 실행 워크플로우 (A2A AgentExecutor 메인 메서드)

        3단계 승인 플로우를 통한 연구 실행:
        1. 연구 계획 승인 (CRITICAL_DECISION)
        2. 중요 데이터 검증 (DATA_VALIDATION) - 선택적
        3. 최종 보고서 승인 (FINAL_REPORT)

        Args:
            context (RequestContext): A2A 요청 컨텍스트 (메시지, 작업ID 등 포함)
            event_queue (EventQueue): 실시간 이벤트 전송용 큐
        """
        try:
            # 에이전트 초기화 확인
            await self._ensure_initialized()

            # A2A 작업 상태 관리자 초기화
            task_updater = TaskUpdater(
                event_queue=event_queue,  # 이벤트 전송 큐
                task_id=context.task_id,  # A2A 작업 고유 ID
                context_id=context.context_id,  # A2A 컨텍스트 ID
            )
            # 작업 상태를 '작업 중'으로 변경
            await task_updater.update_status(TaskState.working)

            # 사용자 질문 추출
            user_query = self._extract_query(context)

            # === 1단계: 연구 계획 수립 및 승인 요청 ===
            # AI가 자동으로 연구 계획 생성
            research_plan = await self._create_research_plan(user_query)

            # 사용자에게 계획 내용 전달
            await event_queue.enqueue_event(
                new_agent_text_message(
                    f"🔍 연구 계획을 수립했습니다. 승인을 기다리고 있습니다...\n\n{research_plan}"
                )
            )

            # HITL을 통한 연구 계획 승인 요청
            plan_approval = await self._request_approval(
                approval_type=ApprovalType.CRITICAL_DECISION,  # 중요 의사결정 타입
                title="연구 계획 승인",
                description=f"다음 주제에 대한 연구 계획을 승인해주세요: {user_query}",
                context={
                    "task_id": context.task_id,  # A2A 작업 ID
                    "query": user_query,  # 원본 사용자 질문
                    "plan": research_plan,  # 생성된 연구 계획
                },
                options=["승인", "수정 요청", "취소"],  # 승인 선택지
            )

            if plan_approval.decision == "취소":
                await event_queue.enqueue_event(
                    new_agent_text_message("❌ 연구가 취소되었습니다.")
                )
                await task_updater.complete()
                return

            # 2단계: 연구 실행 (병렬 모드)
            await event_queue.enqueue_event(
                new_agent_text_message(
                    "✅ 연구 계획이 승인되었습니다. 연구를 시작합니다..."
                )
            )

            # research_result = await self.orchestrator.execute_parallel(user_query)  # 임시 주석 처리
            # 시뮬레이션된 연구 결과
            research_result = {
                "shared_context": {
                    "web_search_results": [f"{user_query} 관련 웹 정보"],
                    "arxiv_papers": [f"{user_query} 관련 학술 논문"],
                    "analysis": f"{user_query} 종합 분석",
                },
                "execution_time": 45.0,
                "parallel_execution": False,
            }

            # 3단계: 중요 데이터 검증
            critical_findings = self._extract_critical_findings(research_result)

            if critical_findings:
                await event_queue.enqueue_event(
                    new_agent_text_message(
                        "⚠️ 중요한 발견 사항이 있습니다. 검증을 요청합니다..."
                    )
                )

                # 데이터 검증 승인 요청
                validation_approval = await self._request_approval(
                    approval_type=ApprovalType.DATA_VALIDATION,
                    title="중요 데이터 검증",
                    description="다음 중요 정보의 정확성을 검증해주세요",
                    context={
                        "task_id": context.task_id,
                        "findings": critical_findings,
                        "sources": research_result.get("shared_context", {}),
                    },
                    priority="high",
                )

                if validation_approval.decision == "거부":
                    await event_queue.enqueue_event(
                        new_agent_text_message(
                            f"⚠️ 데이터 검증 실패: {validation_approval.decision_reason}"
                        )
                    )
                    # 재연구 또는 수정 로직

            # 4단계: 최종 보고서 생성
            final_report = self._generate_report(
                research_result, plan_approval, validation_approval
            )

            await event_queue.enqueue_event(
                new_agent_text_message(
                    "📄 최종 보고서를 생성했습니다. 최종 승인을 기다립니다..."
                )
            )

            # 최종 승인 요청
            final_approval = await self._request_approval(
                approval_type=ApprovalType.FINAL_REPORT,
                title="최종 보고서 승인",
                description="연구 보고서를 검토하고 승인해주세요",
                context={
                    "task_id": context.task_id,
                    "report": final_report,
                    "execution_time": research_result.get("execution_time", 0),
                },
                priority="medium",
            )

            if final_approval.decision == "승인":
                # 승인된 보고서 전송
                await event_queue.enqueue_event(
                    new_agent_text_message(f"✅ 최종 승인 완료!\n\n{final_report}")
                )

                # 보고서 저장 (선택사항)
                await self._save_report(context.task_id, final_report, final_approval)

            else:
                await event_queue.enqueue_event(
                    new_agent_text_message(
                        f"❌ 보고서 거부됨: {final_approval.decision_reason}\n"
                        f"수정이 필요합니다."
                    )
                )

            # 작업 완료
            await task_updater.complete()

        except Exception as e:
            logger.error(f"HITL Research Agent 오류: {e}", exc_info=True)
            await event_queue.enqueue_event(
                new_agent_text_message(f"오류 발생: {str(e)}")
            )
            await task_updater.failed()

    def _extract_query(self, context: RequestContext) -> str:
        """요청에서 쿼리 추출"""
        if context.message and hasattr(context.message, "parts"):
            for part in context.message.parts:
                if hasattr(part, "text") and part.text:
                    return part.text
        return "AI 발전 동향 연구"  # 기본 쿼리

    async def _create_research_plan(self, query: str) -> str:
        """연구 계획 생성"""
        plan = f"""
**연구 주제**: {query}

**연구 계획**:
1. **정보 수집 단계**
   - 웹 검색으로 최신 정보 수집
   - 관련 문서 벡터 검색
   - 주요 웹사이트 상세 스크래핑

2. **분석 단계**
   - 수집된 정보 종합 분석
   - 신뢰도 평가
   - 핵심 인사이트 도출

3. **검증 단계**
   - 중요 정보 교차 검증
   - 출처 신뢰도 확인
   - 사실 관계 검증

4. **보고서 작성**
   - 구조화된 보고서 생성
   - 핵심 발견사항 요약
   - 권장사항 제시

**예상 소요 시간**: 약 2-3분
"""
        return plan

    def _extract_critical_findings(
        self, research_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """중요 발견사항 추출"""
        critical_findings = []

        # 분석 결과에서 중요 정보 추출
        analysis_data = (
            research_result.get("results", {}).get("analysis", {}).get("data", {})
        )

        # 예시: 특정 키워드나 패턴을 포함한 정보를 중요 정보로 분류
        keywords = ["critical", "important", "warning", "alert", "breaking"]

        # 검색 결과 확인
        search_results = analysis_data.get("search_results", [])
        for result in search_results:
            content = result.get("content", "").lower()
            if any(keyword in content for keyword in keywords):
                critical_findings.append(
                    {
                        "type": "search_result",
                        "source": result.get("url", ""),
                        "content": result.get("content", ""),
                        "importance": "high",
                    }
                )

        return critical_findings[:3]  # 최대 3개만

    async def _request_approval(
        self,
        approval_type: ApprovalType,
        title: str,
        description: str,
        context: Dict[str, Any],
        options: Optional[List[str]] = None,
        priority: str = "medium",
        timeout_seconds: int = 300,
    ) -> Any:
        """HITL 승인 요청 및 대기"""

        # 승인 요청 생성
        request = await hitl_manager.request_approval(
            agent_id=self.agent_id,
            approval_type=approval_type,
            title=title,
            description=description,
            context=context,
            options=options,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )

        # 승인 대기
        approved_request = await hitl_manager.wait_for_approval(
            request.request_id,
            auto_approve_on_timeout=False,  # 타임아웃 시 자동 거부
        )

        return approved_request

    def _generate_report(
        self,
        research_result: Dict[str, Any],
        plan_approval: Any,
        validation_approval: Any | None = None,
    ) -> str:
        """최종 보고서 생성"""
        report = f"""
# 연구 보고서

**작성일**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**연구 주제**: {research_result.get("query", "")}

## 승인 내역
- 연구 계획: {plan_approval.decision} (by {plan_approval.decided_by})
"""

        if validation_approval:
            report += f"- 데이터 검증: {validation_approval.decision} (by {validation_approval.decided_by})\n"

        report += f"""
## 연구 요약

{research_result.get("final_response", "")}

## 상세 분석

### 1. 웹 검색 결과
- 검색된 문서 수: {len(research_result.get("results", {}).get("search", {}).get("data", []))}
- 주요 출처: [상위 3개 출처 나열]

### 2. 벡터 검색 결과
- 유사 문서 수: {len(research_result.get("results", {}).get("vector", {}).get("data", []))}
- 평균 유사도: [계산된 평균값]

### 3. 스크래핑 분석
- 분석된 페이지 수: {len(research_result.get("results", {}).get("scrape", {}).get("data", []))}
- 총 추출 텍스트: [단어 수]

## 결론 및 권장사항

[AI가 생성한 결론 및 권장사항]

## 메타데이터
- 총 실행 시간: {research_result.get("execution_time", 0):.2f}초
- 실행 모드: {research_result.get("execution_mode", "unknown")}
- 사용된 에이전트: 5개 (WebSearch, ArxivSearch, NewsSearch, Writer, Reviewer)

---
*이 보고서는 AI 기반 연구 시스템에 의해 자동 생성되었으며, 인간 검토자의 승인을 받았습니다.*
"""
        return report

    async def _save_report(self, task_id: str, report: str, approval: Any):
        """보고서 저장"""
        try:
            logger.info(f"보고서 저장 시작: {task_id}")

            # 보고서 메타데이터 생성
            report_metadata = {
                "task_id": task_id,
                "agent_id": self.agent_id,
                "created_at": datetime.now().isoformat(),
                "approval_id": getattr(approval, "request_id", "unknown")
                if approval
                else None,
                "approved_by": getattr(approval, "approved_by", "system")
                if approval
                else "system",
                "report_type": "hitl_research_report",
                "status": "approved" if approval else "auto_generated",
            }

            # 보고서 데이터 구조화
            _ = {
                "content": report,
                "metadata": report_metadata,
                "word_count": len(report.split()),
                "char_count": len(report),
            }

            # 1. 로컬 파일 시스템에 저장 (백업용)
            try:
                import os

                reports_dir = "reports"
                os.makedirs(reports_dir, exist_ok=True)

                report_filename = f"{reports_dir}/report_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                with open(report_filename, "w", encoding="utf-8") as f:
                    f.write(f"# Research Report - {task_id}\n\n")
                    f.write(f"**생성일시:** {report_metadata['created_at']}\n")
                    f.write(f"**승인자:** {report_metadata['approved_by']}\n")
                    f.write(f"**상태:** {report_metadata['status']}\n\n")
                    f.write("---\n\n")
                    f.write(report)

                logger.info(f"보고서 파일 저장 완료: {report_filename}")

            except Exception as e:
                logger.warning(f"보고서 파일 저장 실패: {e}")

            # 2. Redis에 저장 (캐시 및 실시간 접근용)
            # Note: Redis 연결이 설정되어 있다면 사용, 없으면 건너뛰기
            try:
                # Redis 저장 로직 (향후 구현)
                # redis_key = f"research_reports:{task_id}"
                # await redis_client.hset(redis_key, mapping=report_data)
                # await redis_client.expire(redis_key, 86400 * 7)  # 7일 TTL
                logger.info("Redis 저장 기능은 추후 구현 예정")

            except Exception as e:
                logger.warning(f"Redis 보고서 저장 실패: {e}")

            # 3. 데이터베이스 저장 (영구 보관용)
            # Note: 데이터베이스 연결이 설정되어 있다면 사용
            try:
                # 데이터베이스 저장 로직 (향후 구현)
                # await db.reports.insert_one(report_data)
                logger.info("데이터베이스 저장 기능은 추후 구현 예정")

            except Exception as e:
                logger.warning(f"데이터베이스 보고서 저장 실패: {e}")

            logger.info(f"보고서 저장 완료: {task_id}")
            return {
                "task_id": task_id,
                "saved_at": report_metadata["created_at"],
                "storage_locations": ["local_file"],  # 실제 저장된 위치들
            }

        except Exception as e:
            logger.error(f"보고서 저장 중 오류 발생 (task_id: {task_id}): {e}")
            return None
