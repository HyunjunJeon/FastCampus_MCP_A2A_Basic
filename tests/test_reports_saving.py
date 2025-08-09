#!/usr/bin/env python3
"""
Reports 저장 기능 테스트

이 테스트는 step4_hitl_demo.py에 추가된 보고서 자동 저장 기능을 검증합니다:
1. reports 디렉토리 자동 생성
2. 고유한 파일명으로 보고서 저장
3. 메타데이터 포함된 Markdown 형식 저장
4. 저장된 파일 경로 반환
"""

import unittest
import sys
import os
from pathlib import Path
import hashlib
import tempfile
import shutil

# 프로젝트 루트 디렉토리를 시스템 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# step4_hitl_demo에서 보고서 저장 함수 임포트
from examples.step4_hitl_demo import save_research_report


class TestReportsSaving(unittest.TestCase):
    """Reports 저장 기능 테스트"""
    
    def setUp(self):
        """테스트 준비"""
        # 임시 작업 디렉토리 생성
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        """테스트 정리"""
        # 원래 디렉토리로 복귀
        os.chdir(self.original_cwd)
        # 임시 디렉토리 삭제
        shutil.rmtree(self.test_dir)
    
    def test_reports_directory_creation(self):
        """
        reports 디렉토리 자동 생성 테스트
        
        검증 항목:
        - 디렉토리가 존재하지 않을 때 자동 생성
        - 생성된 디렉토리가 올바른 타입인지 확인
        - 파일이 실제로 저장되는지 검증
        """
        query = "테스트 쿼리"
        response = "테스트 응답"
        progress_messages = ["테스트 메시지 1", "테스트 메시지 2"]
        agent_name = "TestAgent"
        
        # reports 디렉토리가 존재하지 않는 상태에서 시작
        reports_dir = Path("reports")
        self.assertFalse(reports_dir.exists())
        
        # 보고서 저장
        report_path = save_research_report(query, response, progress_messages, agent_name)
        
        # reports 디렉토리가 생성되었는지 확인
        self.assertTrue(reports_dir.exists())
        self.assertTrue(reports_dir.is_dir())
        
        # 파일이 저장되었는지 확인
        self.assertIsNotNone(report_path)
        self.assertTrue(Path(report_path).exists())
        
        print(f"✅ Reports 디렉토리 자동 생성 및 파일 저장 성공: {report_path}")
    
    def test_unique_filename_generation(self):
        """고유한 파일명 생성 테스트"""
        query1 = "첫 번째 쿼리"
        query2 = "두 번째 쿼리"
        response = "테스트 응답"
        progress_messages = ["테스트 메시지"]
        agent_name = "TestAgent"
        
        # 두 개의 다른 쿼리로 보고서 저장
        report_path1 = save_research_report(query1, response, progress_messages, agent_name)
        report_path2 = save_research_report(query2, response, progress_messages, agent_name)
        
        # 파일 경로가 다른지 확인
        self.assertIsNotNone(report_path1)
        self.assertIsNotNone(report_path2)
        self.assertNotEqual(report_path1, report_path2)
        
        # 파일명이 올바른 형식인지 확인 (timestamp_hash.md)
        filename1 = Path(report_path1).name
        filename2 = Path(report_path2).name
        
        # 파일명 형식 검증 (YYYY-MM-DD_HH-MM-SS_hash.md)
        self.assertTrue(filename1.endswith('.md'))
        self.assertTrue(filename2.endswith('.md'))
        
        # 해시 부분이 다른지 확인
        hash1 = filename1.split('_')[-1].replace('.md', '')
        hash2 = filename2.split('_')[-1].replace('.md', '')
        self.assertNotEqual(hash1, hash2)
        
        # 해시가 쿼리에 기반한 올바른 값인지 확인
        expected_hash1 = hashlib.md5(query1.encode()).hexdigest()[:8]
        expected_hash2 = hashlib.md5(query2.encode()).hexdigest()[:8]
        self.assertEqual(hash1, expected_hash1)
        self.assertEqual(hash2, expected_hash2)
        
        print("✅ 고유한 파일명 생성 검증:")
        print(f"   파일1: {filename1} (해시: {hash1})")
        print(f"   파일2: {filename2} (해시: {hash2})")
    
    def test_markdown_format_and_metadata(self):
        """Markdown 형식 및 메타데이터 포함 테스트"""
        query = "AI 의료 진단 영향 연구"
        response = "AI는 의료 진단 분야에서 혁신적인 변화를 가져오고 있습니다."
        progress_messages = [
            "연구 계획 수립 중...",
            "관련 논문 검색 중...",
            "데이터 분석 중...",
            "보고서 작성 중..."
        ]
        agent_name = "DeepResearchAgent"
        
        # 보고서 저장
        report_path = save_research_report(query, response, progress_messages, agent_name)
        self.assertIsNotNone(report_path)
        
        # 저장된 파일 내용 확인
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 메타데이터 포함 여부 확인
        self.assertIn("# Deep Research 보고서", content)
        self.assertIn("## 메타데이터", content)
        self.assertIn(f"- **에이전트**: {agent_name}", content)
        self.assertIn(f"- **진행 메시지 수**: {len(progress_messages)}개", content)
        self.assertIn(f"- **최종 응답 길이**: {len(response)}자", content)
        
        # 쿼리 포함 여부 확인
        self.assertIn("## 연구 쿼리", content)
        self.assertIn(query, content)
        
        # 진행상황 포함 여부 확인
        self.assertIn("## 실행 진행상황", content)
        for i, msg in enumerate(progress_messages, 1):
            self.assertIn(f"{i}. {msg}", content)
        
        # 최종 결과 포함 여부 확인
        self.assertIn("## 최종 연구 결과", content)
        self.assertIn(response, content)
        
        # 자동 생성 표시 확인
        self.assertIn("*이 보고서는 HITL Deep Research 시스템에 의해 자동으로 생성되었습니다.*", content)
        
        print("✅ Markdown 형식 및 메타데이터 검증 완료")
        print(f"   보고서 길이: {len(content)} 문자")
        print("   메타데이터 포함: ✓")
        print(f"   진행상황 {len(progress_messages)}개 포함: ✓")
    
    def test_empty_response_handling(self):
        """빈 응답 처리 테스트"""
        query = "빈 응답 테스트"
        response = ""  # 빈 응답
        progress_messages = []  # 빈 진행 메시지
        agent_name = "TestAgent"
        
        report_path = save_research_report(query, response, progress_messages, agent_name)
        self.assertIsNotNone(report_path)
        
        # 저장된 파일 내용 확인
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 빈 응답 처리 확인
        self.assertIn("(최종 응답 없음)", content)
        self.assertIn("(진행상황 메시지 없음)", content)
        
        print("✅ 빈 응답 및 메시지 처리 검증 완료")
    
    def test_error_handling(self):
        """오류 처리 테스트"""
        query = "오류 테스트 쿼리"
        response = "연구 실행 중 오류 발생: 네트워크 연결 실패"
        progress_messages = []
        agent_name = "Unknown"
        
        report_path = save_research_report(query, response, progress_messages, agent_name)
        self.assertIsNotNone(report_path)
        
        # 저장된 파일 내용 확인
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 오류 정보가 포함되었는지 확인
        self.assertIn("연구 실행 중 오류 발생", content)
        self.assertIn("- **에이전트**: Unknown", content)
        
        print("✅ 오류 상황 처리 검증 완료")
    
    def test_cross_platform_compatibility(self):
        """크로스 플랫폼 호환성 테스트"""
        query = "크로스 플랫폼 테스트"
        response = "플랫폼 호환성 테스트 응답"
        progress_messages = ["플랫폼 테스트 진행 중"]
        agent_name = "TestAgent"
        
        # pathlib.Path 사용으로 크로스 플랫폼 호환성 확인
        report_path = save_research_report(query, response, progress_messages, agent_name)
        self.assertIsNotNone(report_path)
        
        # 경로 구분자 확인 (Windows: \, Unix: /)
        path_obj = Path(report_path)
        self.assertTrue(path_obj.exists())
        self.assertTrue(path_obj.is_absolute())  # 절대 경로인지 확인
        
        print("✅ 크로스 플랫폼 호환성 검증 완료")
        print(f"   절대 경로: {report_path}")


class TestFunctionIntegration(unittest.TestCase):
    """함수 통합 테스트"""
    
    def test_function_signature(self):
        """함수 시그니처 테스트"""
        import inspect
        
        # 함수 시그니처 확인
        sig = inspect.signature(save_research_report)
        params = list(sig.parameters.keys())
        
        # 예상되는 파라미터들이 모두 있는지 확인
        expected_params = ['query', 'response', 'progress_messages', 'agent_name']
        for param in expected_params:
            self.assertIn(param, params)
        
        # 리턴 타입 확인 (Optional[str])
        return_annotation = sig.return_annotation
        self.assertTrue(return_annotation is not None)
        
        print(f"✅ 함수 시그니처 검증 완료: {params}")
    
    def test_return_value_format(self):
        """반환값 형식 테스트"""
        query = "반환값 테스트"
        response = "테스트 응답"
        progress_messages = ["테스트"]
        agent_name = "TestAgent"
        
        # 임시 디렉토리에서 실행
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                result = save_research_report(query, response, progress_messages, agent_name)
                
                # 반환값이 절대 경로인지 확인
                self.assertIsNotNone(result)
                self.assertIsInstance(result, str)
                self.assertTrue(os.path.isabs(result))  # 절대 경로 확인
                
                # 실제 파일이 존재하는지 확인
                self.assertTrue(os.path.exists(result))
                
                print(f"✅ 반환값 형식 검증 완료: {result}")
                
            finally:
                os.chdir(original_cwd)


def run_tests():
    """
    Reports 저장 기능 포괄 테스트 실행
    
    실행하는 테스트:
    - TestReportsSaving: 핵심 저장 기능 테스트
    - TestFunctionIntegration: 함수 시그니처 및 통합 테스트
    
    테스트 결과에 따라 성공/실패 메시지와 함께 실행 가이드를 제공합니다.
    """
    print("=" * 70)
    print("🧪 Reports 저장 기능 포괄 테스트 시작")
    print("=" * 70)
    print("""
    검증 항목:
    1️⃣ reports 디렉토리 자동 생성
    2️⃣ 고유한 파일명 생성 (timestamp_hash.md)
    3️⃣ Markdown 형식 및 메타데이터 포함
    4️⃣ 빈 응답 및 오류 상황 처리
    5️⃣ 크로스 플랫폼 호환성
    6️⃣ 함수 통합성
    """)
    
    # 테스트 스위트 생성
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 테스트 케이스들 추가
    suite.addTests(loader.loadTestsFromTestCase(TestReportsSaving))
    suite.addTests(loader.loadTestsFromTestCase(TestFunctionIntegration))
    
    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 결과 출력
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("🎉 모든 Reports 저장 기능 테스트가 성공했습니다!")
        print("✅ step4_hitl_demo.py의 자동 저장 기능이 올바르게 구현되었습니다.")
        print("\n💡 이제 다음 명령으로 실제 테스트를 실행해보세요:")
        print("   python examples/step4_hitl_demo.py")
        print("   → reports/ 디렉토리에 결과가 자동 저장됩니다!")
    else:
        print(f"❌ {len(result.failures)} 개의 실패, {len(result.errors)} 개의 오류")
        if result.failures:
            print("\n실패한 테스트:")
            for test, traceback in result.failures:
                print(f"   • {test}: {traceback}")
        if result.errors:
            print("\n오류 테스트:")
            for test, traceback in result.errors:
                print(f"   • {test}: {traceback}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)