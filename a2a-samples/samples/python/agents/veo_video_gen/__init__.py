"""VEO 비디오 생성 에이전트 패키지.

이 패키지는 Google VEO 모델을 사용하여 텍스트 프롬프트로부터
비디오를 생성하는 A2A 에이전트를 제공합니다.

주요 구성요소:
    - agent: VideoGenerationAgent - VEO 모델을 사용한 비디오 생성
    - agent_executor: VideoGenerationAgentExecutor - A2A 연결 래퍼
    - __main__: 서버 진입점 (포트 10003)

주요 기능:
    - 텍스트 프롬프트로 비디오 생성
    - Google Cloud Storage에 비디오 저장
    - 서명된 URL로 비디오 접근 제공
    - 진행률 업데이트 스트리밍

필수 환경 변수:
    - GOOGLE_GENAI_USE_VERTEXAI: 'TRUE' 필수
    - GOOGLE_CLOUD_PROJECT: GCP 프로젝트 ID
    - GOOGLE_CLOUD_LOCATION: GCP 리전 (예: us-central1)
    - VIDEO_GEN_GCS_BUCKET: 비디오 저장용 GCS 버킷 이름
"""
