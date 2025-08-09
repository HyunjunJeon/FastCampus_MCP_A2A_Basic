"""
HITL(Human-In-The-Loop) 시스템 데이터 모델 정의

=== 모델 구조 ===
이 모듈은 HITL 시스템의 핵심 데이터 구조들을 정의합니다:

1. ApprovalType: 승인 요청의 유형 분류
   - CRITICAL_DECISION: 중요한 결정사항 (높은 위험도)
   - DATA_VALIDATION: 데이터 검증 승인
   - FINAL_REPORT: 최종 보고서 승인
   - BUDGET_APPROVAL: 예산 사용 승인
   - SAFETY_CHECK: 안전성 검토

2. ApprovalStatus: 승인 요청의 현재 상태
   - PENDING: 대기 중 (초기 상태)
   - APPROVED: 승인됨
   - REJECTED: 거부됨
   - TIMEOUT: 시간 초과
   - AUTO_APPROVED: 자동 승인

3. ApprovalRequest: 승인 요청의 완전한 데이터 구조
   - 메타데이터, 컨텍스트, 상태 추적
   - UUID 기반 고유 식별자
   - 타임스탬프 및 만료 시간 관리

4. HITLContext: 승인 결정을 위한 컨텍스트 정보
   - 현재 작업 상황
   - 이전 결정 내역
   - 위험도 평가 데이터

5. HITLPolicy: HITL 시스템의 운영 정책
   - 자동 승인 타임아웃 설정
   - 알림 채널 구성
   - 에스컬레이션 규칙

=== 사용 목적 ===
- Redis 저장소와의 직렬화/역직렬화
- 웹 API 요청/응답 데이터 검증
- 타입 안전성 보장
- 비즈니스 로직 일관성 유지
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timezone
from enum import Enum
import uuid


class ApprovalType(str, Enum):
    """승인 유형"""

    CRITICAL_DECISION = "critical_decision"
    DATA_VALIDATION = "data_validation"
    FINAL_REPORT = "final_report"
    BUDGET_APPROVAL = "budget_approval"
    SAFETY_CHECK = "safety_check"


class ApprovalStatus(str, Enum):
    """승인 상태"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


class ApprovalRequest(BaseModel):
    """승인 요청"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(..., description="관련 작업 ID")
    agent_id: str = Field(..., description="요청 에이전트 ID")
    approval_type: ApprovalType = Field(..., description="승인 유형")

    # 승인 내용
    title: str = Field(..., description="승인 요청 제목")
    description: str = Field(..., description="상세 설명")
    context: Dict[str, Any] = Field(..., description="관련 컨텍스트")
    options: List[str] = Field(default=["승인", "거부"], description="선택 옵션")

    # 메타데이터
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="만료 시간")
    priority: Literal["low", "medium", "high", "critical"] = Field("medium")

    # 상태
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = None


class HITLContext(BaseModel):
    """HITL 컨텍스트 정보"""

    current_task: str = Field(..., description="현재 작업")
    previous_decisions: List[Dict[str, Any]] = Field(
        default_factory=list, description="이전 결정 내역"
    )
    data_snapshot: Dict[str, Any] = Field(..., description="현재 데이터 스냅샷")
    risk_assessment: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[str]] = None


class HITLPolicy(BaseModel):
    """HITL 정책 설정"""

    auto_approve_timeout: int = Field(
        300,  # 5분
        description="자동 승인 타임아웃 (초)",
    )
    require_reason_for_rejection: bool = Field(
        True, description="거부 시 이유 필수 여부"
    )
    allow_delegation: bool = Field(False, description="다른 검토자에게 위임 허용")
    notification_channels: List[str] = Field(
        default=["web", "email"], description="알림 채널"
    )
    escalation_rules: Dict[str, Any] = Field(
        default_factory=dict, description="에스컬레이션 규칙"
    )
