#!/bin/bash
# FastCampus MCP & A2A Docker 실행 스크립트
# 사용법: ./run_docker.sh [command] [options]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 스크립트 위치로 이동
cd "$(dirname "$0")"

# 도움말 출력
show_help() {
    echo -e "${BLUE}FastCampus MCP & A2A Docker 실행 스크립트${NC}"
    echo ""
    echo "사용법: ./run_docker.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  build       Docker 이미지 빌드"
    echo "  up          전체 환경 시작 (MCP 서버 + Redis + App)"
    echo "  down        전체 환경 종료"
    echo "  restart     전체 환경 재시작"
    echo "  logs        로그 출력"
    echo "  shell       앱 컨테이너에 bash 접속"
    echo "  step1       Step 1 예제 실행 (MCP + LangGraph)"
    echo "  step2       Step 2 예제 실행 (LangGraph + A2A)"
    echo "  step3       Step 3 예제 실행 (멀티에이전트 비교)"
    echo "  step4       Step 4 예제 실행 (HITL)"
    echo "  run <file>  특정 Python 파일 실행"
    echo "  test        MCP 서버 헬스체크"
    echo "  clean       Docker 리소스 정리"
    echo "  help        이 도움말 출력"
    echo ""
    echo "예시:"
    echo "  ./run_docker.sh build       # 이미지 빌드"
    echo "  ./run_docker.sh up          # 전체 환경 시작"
    echo "  ./run_docker.sh step1       # Step 1 예제 실행"
    echo "  ./run_docker.sh shell       # 컨테이너 쉘 접속"
    echo "  ./run_docker.sh run examples/step1_mcp_langgraph.py"
    echo ""
}

# .env 파일 확인
check_env() {
    if [ ! -f ".env" ]; then
        echo -e "${RED}[ERROR]${NC} .env 파일이 없습니다."
        echo "  .env.example을 복사하여 .env를 생성하고 API 키를 설정하세요:"
        echo "  cp .env.example .env"
        exit 1
    fi
}

# 이미지 빌드
do_build() {
    echo -e "${BLUE}[INFO]${NC} Docker 이미지 빌드 중..."
    docker-compose build
    echo -e "${GREEN}[SUCCESS]${NC} Docker 이미지 빌드 완료!"
}

# 전체 환경 시작
do_up() {
    check_env
    echo -e "${BLUE}[INFO]${NC} 전체 Docker 환경 시작 중..."
    docker-compose up -d redis arxiv-mcp tavily-mcp serper-mcp

    echo -e "${BLUE}[INFO]${NC} MCP 서버 헬스체크 대기 중..."
    sleep 10

    # 헬스체크
    echo -e "${BLUE}[INFO]${NC} 헬스체크 수행 중..."
    do_test

    echo -e "${GREEN}[SUCCESS]${NC} 전체 환경이 시작되었습니다!"
    echo ""
    echo "예제 실행 방법:"
    echo "  ./run_docker.sh step1       # Step 1 예제"
    echo "  ./run_docker.sh shell       # 컨테이너 쉘 접속"
}

# 전체 환경 종료
do_down() {
    echo -e "${BLUE}[INFO]${NC} Docker 환경 종료 중..."
    docker-compose down
    echo -e "${GREEN}[SUCCESS]${NC} Docker 환경이 종료되었습니다."
}

# 재시작
do_restart() {
    do_down
    do_up
}

# 로그 출력
do_logs() {
    docker-compose logs -f "${@:-app}"
}

# 쉘 접속
do_shell() {
    check_env
    echo -e "${BLUE}[INFO]${NC} 앱 컨테이너에 접속 중..."
    docker-compose run --rm app bash
}

# 헬스체크
do_test() {
    echo -e "${BLUE}[INFO]${NC} MCP 서버 헬스체크..."

    # ArXiv 서버
    if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} ArXiv MCP (3000)"
    else
        echo -e "${RED}[FAIL]${NC} ArXiv MCP (3000)"
    fi

    # Tavily 서버
    if curl -sf http://localhost:3001/health > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} Tavily MCP (3001)"
    else
        echo -e "${RED}[FAIL]${NC} Tavily MCP (3001)"
    fi

    # Serper 서버
    if curl -sf http://localhost:3002/health > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} Serper MCP (3002)"
    else
        echo -e "${RED}[FAIL]${NC} Serper MCP (3002)"
    fi

    # Redis
    if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} Redis (6379)"
    else
        echo -e "${RED}[FAIL]${NC} Redis (6379)"
    fi
}

# Step 예제 실행
run_step() {
    local step=$1
    check_env

    echo -e "${BLUE}[INFO]${NC} Step ${step} 예제 실행 중..."
    docker-compose run --rm app uv run python "examples/step${step}_*.py" 2>/dev/null || \
    docker-compose run --rm app uv run python "examples/step${step}"*.py
}

# Step 1 실행
do_step1() {
    check_env
    echo -e "${BLUE}[INFO]${NC} Step 1 예제 실행 중 (MCP + LangGraph)..."
    docker-compose run --rm app uv run python examples/step1_mcp_langgraph.py
}

# Step 2 실행
do_step2() {
    check_env
    echo -e "${BLUE}[INFO]${NC} Step 2 예제 실행 중 (LangGraph + A2A)..."
    docker-compose run --rm app uv run python examples/step2_langgraph_a2a_client.py
}

# Step 3 실행
do_step3() {
    check_env
    echo -e "${BLUE}[INFO]${NC} Step 3 예제 실행 중 (멀티에이전트 비교)..."
    docker-compose run --rm app uv run python examples/step3_multiagent_systems.py
}

# Step 4 실행
do_step4() {
    check_env
    echo -e "${BLUE}[INFO]${NC} Step 4 예제 실행 중 (HITL)..."
    docker-compose run --rm -p 8000:8000 app uv run python examples/step4_hitl_demo.py
}

# 특정 파일 실행
do_run() {
    check_env
    if [ -z "$1" ]; then
        echo -e "${RED}[ERROR]${NC} 실행할 파일을 지정하세요."
        echo "예: ./run_docker.sh run examples/step1_mcp_langgraph.py"
        exit 1
    fi
    echo -e "${BLUE}[INFO]${NC} $1 실행 중..."
    docker-compose run --rm app uv run python "$1"
}

# 리소스 정리
do_clean() {
    echo -e "${YELLOW}[WARN]${NC} Docker 리소스를 정리합니다..."
    docker-compose down -v --rmi local
    echo -e "${GREEN}[SUCCESS]${NC} Docker 리소스 정리 완료!"
}

# 메인 로직
case "${1:-help}" in
    build)
        do_build
        ;;
    up)
        do_up
        ;;
    down)
        do_down
        ;;
    restart)
        do_restart
        ;;
    logs)
        shift
        do_logs "$@"
        ;;
    shell)
        do_shell
        ;;
    test)
        do_test
        ;;
    step1)
        do_step1
        ;;
    step2)
        do_step2
        ;;
    step3)
        do_step3
        ;;
    step4)
        do_step4
        ;;
    run)
        shift
        do_run "$@"
        ;;
    clean)
        do_clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} 알 수 없는 명령: $1"
        show_help
        exit 1
        ;;
esac
