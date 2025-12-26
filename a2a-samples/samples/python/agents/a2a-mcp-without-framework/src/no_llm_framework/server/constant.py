"""서버 설정 상수 모듈.

이 모듈은 서버 에이전트에서 사용하는 환경 변수 기반
설정 상수들을 정의합니다.
"""
import os

# --- API 키 설정 ---
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
