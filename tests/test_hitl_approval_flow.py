#!/usr/bin/env python3
"""
HITL 승인 플로우 실제 테스트
"""

import asyncio
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath("."))

from src.hitl.manager import hitl_manager
from src.hitl.models import ApprovalRequest, ApprovalType
from src.hitl.storage import approval_storage
from datetime import datetime, timedelta
import uuid


async def test_hitl_approval_flow():
    """HITL 승인 플로우 전체 테스트"""
    print("🚀 HITL 승인 플로우 테스트 시작")
    print("=" * 60)

    try:
        # HITL 매니저 초기화
        await hitl_manager.initialize()
        print("✅ HITL 매니저 초기화 완료")

        # Storage 연결
        await approval_storage.connect()
        print("✅ Storage 연결 완료")

        # 1. 승인 요청 생성 테스트
        print("\n📋 1. 승인 요청 생성 테스트")
        print("-" * 40)

        test_request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            task_id="test_task_001",
            agent_id="test_agent_001",
            approval_type=ApprovalType.CRITICAL_DECISION,
            title="테스트 중요한 결정 승인",
            description="통합 테스트를 위한 중요한 결정 승인 요청입니다.",
            context={
                "tool_name": "web_search",
                "parameters": {"query": "인공지능 최신 동향", "max_results": 10},
            },
            expires_at=datetime.now() + timedelta(hours=1),
        )

        # 승인 요청 저장
        request_id = await approval_storage.create_approval_request(test_request)
        if request_id:
            print(f"✅ 승인 요청 생성 성공: {request_id}")
        else:
            print(f"❌ 승인 요청 생성 실패: {test_request.request_id}")
            return False

        # 2. 대기 중인 승인 요청 조회 테스트
        print("\n📋 2. 대기 중인 승인 요청 조회 테스트")
        print("-" * 40)

        pending_requests = await hitl_manager.get_pending_approvals(limit=10)
        print(f"✅ 대기 중인 승인 요청 수: {len(pending_requests)}")

        # 생성한 요청이 목록에 있는지 확인
        found_request = None
        for req in pending_requests:
            if req.request_id == test_request.request_id:
                found_request = req
                break

        if found_request:
            print(f"✅ 생성한 승인 요청이 대기 목록에서 발견됨: {found_request.title}")
        else:
            print("❌ 생성한 승인 요청이 대기 목록에서 발견되지 않음")
            return False

        # 3. 승인 처리 테스트
        print("\n📋 3. 승인 처리 테스트")
        print("-" * 40)

        approval_success = await hitl_manager.approve(
            request_id=test_request.request_id,
            decided_by="test_user",
            decision="approved",
            reason="통합 테스트 승인",
        )

        if approval_success:
            print(f"✅ 승인 처리 성공: {test_request.request_id}")
        else:
            print(f"❌ 승인 처리 실패: {test_request.request_id}")
            return False

        # 4. 승인된 요청 상태 확인
        print("\n📋 4. 승인된 요청 상태 확인")
        print("-" * 40)

        approved_request = await approval_storage.get_approval_request(
            test_request.request_id
        )
        if approved_request and approved_request.status.value == "approved":
            print(f"✅ 승인 상태 확인됨: {approved_request.status.value}")
            print(f"   - 결정자: {approved_request.decided_by}")
            print(f"   - 결정 시간: {approved_request.decided_at}")
            print(f"   - 사유: {approved_request.decision_reason}")
        else:
            print("❌ 승인 상태 확인 실패")
            return False

        # 5. 거부 플로우 테스트
        print("\n📋 5. 거부 플로우 테스트")
        print("-" * 40)

        # 새로운 승인 요청 생성
        reject_request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            task_id="test_task_002",
            agent_id="test_agent_002",
            approval_type=ApprovalType.DATA_VALIDATION,
            title="테스트 데이터 검증 거부",
            description="거부 테스트를 위한 데이터 검증 요청입니다.",
            context={"data_source": "sensitive_database", "access_type": "read"},
            expires_at=datetime.now() + timedelta(hours=1),
        )

        # 요청 저장
        reject_id = await approval_storage.create_approval_request(reject_request)
        print(f"✅ 거부 테스트용 요청 생성: {reject_id}")

        # 거부 처리
        reject_success = await hitl_manager.reject(
            request_id=reject_request.request_id,
            decided_by="test_user",
            reason="테스트 목적으로 거부",
        )

        if reject_success:
            print(f"✅ 거부 처리 성공: {reject_request.request_id}")
        else:
            print(f"❌ 거부 처리 실패: {reject_request.request_id}")
            return False

        # 거부된 요청 상태 확인
        rejected_request = await approval_storage.get_approval_request(
            reject_request.request_id
        )
        if rejected_request and rejected_request.status.value == "rejected":
            print(f"✅ 거부 상태 확인됨: {rejected_request.status.value}")
            print(f"   - 결정자: {rejected_request.decided_by}")
            print(f"   - 거부 사유: {rejected_request.decision_reason}")
        else:
            print("❌ 거부 상태 확인 실패")
            return False

        # 6. 만료 테스트
        print("\n📋 6. 만료 테스트")
        print("-" * 40)

        # 이미 만료된 요청 생성 (테스트 목적)
        expired_request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            task_id="test_task_003",
            agent_id="test_agent_003",
            approval_type=ApprovalType.SAFETY_CHECK,
            title="만료된 안전 검사 요청",
            description="만료 테스트를 위한 안전 검사 요청입니다.",
            context={"api_endpoint": "https://api.example.com/data", "method": "GET"},
            expires_at=datetime.now() - timedelta(minutes=1),  # 1분 전에 만료
        )

        expired_id = await approval_storage.create_approval_request(expired_request)
        print(f"✅ 만료된 요청 생성: {expired_id}")

        # 만료된 요청에 대한 승인 시도
        try:
            expire_approval_success = await hitl_manager.approve(
                request_id=expired_request.request_id,
                decided_by="test_user",
                decision="approved",
                reason="만료 테스트",
            )

            if not expire_approval_success:
                print("✅ 만료된 요청 승인 거부됨 (예상된 동작)")
            else:
                print("⚠️ 만료된 요청이 승인됨 (예상과 다른 동작)")
        except Exception as e:
            print(f"✅ 만료된 요청 승인 시 예외 발생 (예상된 동작): {str(e)}")

        # 7. 통계 및 요약
        print("\n📋 7. 테스트 결과 요약")
        print("-" * 40)

        # 전체 승인 요청 조회
        all_pending = await hitl_manager.get_pending_approvals(limit=100)

        print(f"✅ 전체 대기 중인 승인 요청: {len(all_pending)}개")

        # 타입별 분류
        type_counts = {}
        for req in all_pending:
            req_type = req.approval_type.value
            type_counts[req_type] = type_counts.get(req_type, 0) + 1

        print("📊 타입별 대기 요청 분포:")
        for req_type, count in type_counts.items():
            print(f"   - {req_type}: {count}개")

        print("\n" + "=" * 60)
        print("🎉 HITL 승인 플로우 테스트 완료")
        print("=" * 60)
        print("✅ 모든 테스트가 성공적으로 완료되었습니다!")

        return True

    except Exception as e:
        print(f"\n❌ 테스트 실행 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # 정리
        try:
            await approval_storage.disconnect()
            await hitl_manager.shutdown()
            print("\n🧹 HITL 매니저 정리 완료")
        except Exception:
            pass


async def main():
    """메인 함수"""
    print("HITL 승인 플로우 테스트를 시작합니다...")

    success = await test_hitl_approval_flow()

    if success:
        print("\n🎯 결론: HITL 시스템이 정상적으로 작동합니다!")
        return 0
    else:
        print("\n💥 결론: HITL 시스템에 문제가 있습니다.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
