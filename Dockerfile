# Python 3.12 slim 베이스 이미지 사용
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 도구 설치
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# UV 패키지 매니저 설치
RUN pip install uv

# 의존성 복사 및 설치
COPY pyproject.toml uv.lock ./  
RUN uv sync --frozen  

# 프로젝트 파일 복사
COPY src/ ./src/

# 헬스체크 엔드포인트: FastMCP custom_route 사용
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# HTTP 포트 노출
EXPOSE 3000

# 환경변수 설정
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=3000
ENV LOG_LEVEL=info

# 애플리케이션 실행
CMD ["uv", "run", "python", "-m", "src.mcp_retriever.server"] 