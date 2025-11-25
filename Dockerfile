# FastCampus MCP & A2A 예제 실행을 위한 Docker 이미지
# 소스코드와 실행환경을 모두 포함하여 예제를 바로 실행할 수 있습니다.
#
# 빌드: docker build -t fc-mcp-a2a .
# 실행: docker-compose up (권장) 또는 개별 실행
#
# ⚠️ 중요: uv.lock 파일을 통해 정확한 의존성 버전이 보장됩니다.
#    pyproject.toml 변경 시 반드시 `uv lock` 실행 후 uv.lock을 커밋하세요.

FROM python:3.12-slim

# 메타데이터
LABEL maintainer="Hyunjun Jeon <jeonhj920@gmail.com>"
LABEL description="FastCampus MCP & A2A Multi-Agent System Examples"
LABEL version="1.0.0"

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# UV 패키지 매니저 설치 (최신 안정 버전)
RUN pip install --no-cache-dir uv

# ============================================
# 의존성 설치 (캐시 최적화를 위해 소스보다 먼저)
# ============================================

# 1. 의존성 정의 파일 복사
#    - pyproject.toml: 의존성 선언
#    - uv.lock: 정확한 버전 고정 (재현 가능한 빌드의 핵심!)
COPY pyproject.toml uv.lock LICENSE ./
COPY .python-version ./

# 2. 소스 코드 복사 (uv sync에서 프로젝트 설치에 필요)
COPY src/ ./src/
COPY examples/ ./examples/
COPY docs/ ./docs/
COPY steps/ ./steps/
COPY code_index.md ./

# 3. 의존성 설치 (uv.lock 기반 정확한 버전 설치)
#    --frozen: lock 파일을 절대 업데이트하지 않음 (재현성 보장)
#    빌드 시 lock 파일과 pyproject.toml이 불일치하면 에러 발생
RUN uv sync --frozen

# 4. 개발 모드로 패키지 설치 (src 모듈 임포트 가능하도록)
RUN uv pip install -e .

# 환경변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# MCP 서버 연결을 위한 환경변수 (Docker 네트워크 내에서 서비스명으로 접근)
# 호스트에서 실행할 때는 localhost, Docker에서는 서비스명 사용
ENV MCP_ARXIV_URL=http://arxiv-mcp:3000
ENV MCP_TAVILY_URL=http://tavily-mcp:3001
ENV MCP_SERPER_URL=http://serper-mcp:3002
ENV REDIS_URL=redis://redis:6379/0

# A2A 서버 포트
EXPOSE 8090 8091 8092

# HITL 웹 대시보드 포트
EXPOSE 8000

# 기본 명령: bash 쉘 (예제 실행을 위해)
CMD ["bash"]
