#!/bin/bash
# MCP 서버 Docker 관리 스크립트

set -e

# 프로젝트 루트 디렉토리 설정 (스크립트가 docker/ 디렉토리에 있다고 가정)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 프로젝트 루트로 이동
cd "${PROJECT_ROOT}"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 서비스/포트 유틸리티
# 지정 포트의 /health 엔드포인트가 2xx를 반환하는지 확인
is_health_ok() {
    local port="$1"
    curl -f -s "http://localhost:${port}/health" > /dev/null 2>&1
}

# 지정 포트가 사용 중인지 확인 (LISTEN)
is_port_in_use() {
    local port="$1"
    # macOS 기본 lsof 사용. 실패 시 보수적으로 사용 중으로 간주하지 않음
    if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"${port}" -sTCP:LISTEN -Pn >/dev/null 2>&1
        return $?
    fi
    return 1
}

# 컨테이너가 실행 중인지 확인
is_container_running() {
    local name="$1"
    # docker가 없으면 실행 중 아님 처리
    command -v docker >/dev/null 2>&1 || return 1
    docker ps --format '{{.Names}}' | grep -q "^${name}$"
}

# 특정 서비스가 도커 컨테이너 실행 중이며 헬시한지 확인
is_docker_service_healthy() {
    local name="$1"; local port="$2"
    if is_container_running "${name}" && is_health_ok "${port}"; then
        return 0
    fi
    return 1
}

# 도움말 표시
show_help() {
    cat << EOF
MCP 서버 Docker 관리 스크립트

사용법:
  $0 <command> [options]

명령어:
  build         모든 MCP 서버 이미지 빌드
  up            모든 MCP 서버 시작 (백그라운드)
  up-fg         모든 MCP 서버 시작 (포그라운드)
  down          모든 MCP 서버 중지
  restart       모든 MCP 서버 재시작
  logs          모든 서버 로그 확인
  logs <server> 특정 서버 로그 확인 (tavily, arxiv, serper)
  status        서버 상태 확인
  clean         중지된 컨테이너 및 미사용 이미지 정리
  test          모든 서버 헬스체크 테스트
  
옵션:
  --with-tools  Redis Commander 포함 실행
  
예시:
  $0 build                    # 이미지 빌드
  $0 up                       # 서버 시작
  $0 up --with-tools          # Redis Commander 포함 시작
  $0 logs tavily              # Tavily 서버 로그만 확인
  $0 test                     # 헬스체크 테스트
  
EOF
}

# 환경 파일 확인 (프로젝트 루트에서)
check_env() {
    local env_file="${PROJECT_ROOT}/.env"
    local example_file="${PROJECT_ROOT}/env.example"
    
    if [ ! -f "${env_file}" ]; then
        log_warning "프로젝트 루트에 .env 파일이 없습니다. env.example을 참고하여 생성하세요."
        log_info "경로: ${env_file}"
        if [ -f "${example_file}" ]; then
            log_info "env.example을 .env로 복사하시겠습니까? (y/N)"
            read -r response
            if [[ "$response" =~ ^[Yy]$ ]]; then
                cp "${example_file}" "${env_file}"
                log_success ".env 파일이 생성되었습니다. API 키를 설정하세요."
                log_info "파일 위치: ${env_file}"
            fi
        else
            log_warning "env.example 파일도 찾을 수 없습니다: ${example_file}"
        fi
    else
        log_info ".env 파일 확인됨: ${env_file}"
    fi
}

# Docker Compose 파일 경로
COMPOSE_FILE="docker/docker-compose.mcp.yml"

# 메인 로직
case "${1:-help}" in
    build)
        # .env 파일이 있으면 환경 변수로 export (빌드 시에도 필요할 수 있음)
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            log_info ".env 파일에서 환경 변수 로드 중..."
            set -a  # 자동 export 모드 활성화
            source "${PROJECT_ROOT}/.env"
            set +a  # 자동 export 모드 비활성화
            log_success "환경 변수 로드 완료"
        fi
        
        log_info "MCP 서버 이미지 빌드 중..."
        docker-compose -f $COMPOSE_FILE build
        log_success "이미지 빌드 완료"
        ;;
        
    up)
        check_env
        # .env 파일이 있으면 환경 변수로 export
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            log_info ".env 파일에서 환경 변수 로드 중..."
            set -a  # 자동 export 모드 활성화
            source "${PROJECT_ROOT}/.env"
            set +a  # 자동 export 모드 비활성화
            log_success "환경 변수 로드 완료"
        fi
        
        # 이미 도커로 실행 중이면 재실행 방지: 세 코어 서비스 모두 헬시한지 확인
        need_tools=0
        if [[ "$2" == "--with-tools" ]]; then
            need_tools=1
        fi

        core_ok=0
        if is_docker_service_healthy "mcp_arxiv_server" 3000 \
           && is_docker_service_healthy "mcp_tavily_server" 3001 \
           && is_docker_service_healthy "mcp_serper_server" 3002; then
            core_ok=1
        fi

        if [[ "$core_ok" -eq 1 ]]; then
            if [[ "$need_tools" -eq 1 ]]; then
                # 코어는 실행 중. 도구 프로필만 필요한지 확인
                if is_container_running "mcp_redis_commander" || is_port_in_use 8081; then
                    log_info "코어 MCP 서버와 도구가 이미 실행 중입니다. 재실행을 건너뜁니다."
                else
                    log_info "코어 MCP 서버는 실행 중입니다. 도구 프로필만 시작합니다..."
                    docker-compose -f $COMPOSE_FILE --profile tools up -d
                    log_success "Redis Commander 가 시작되었습니다"
                fi
            else
                log_info "MCP 코어 서버가 이미 실행 중입니다. 재실행을 건너뜁니다."
            fi
            echo ""
            log_info "서버 접속 정보:"
            echo "  - ArXiv MCP Server:  http://localhost:3000"
            echo "  - Tavily MCP Server: http://localhost:3001"
            echo "  - Serper MCP Server: http://localhost:3002"
            if [[ "$need_tools" -eq 1 ]]; then
                echo "  - Redis Commander:   http://localhost:8081 (admin/mcp2025)"
            fi
        else
            # 포트가 다른 프로세스로 점유된 경우 경고 후 진행 판단
            any_port_busy=0
            for p in 3000 3001 3002; do
                if is_port_in_use "$p" && ! is_health_ok "$p"; then
                    any_port_busy=1
                fi
            done

            if [[ "$any_port_busy" -eq 1 ]]; then
                log_warning "일부 포트(3000/3001/3002)가 다른 프로세스에 의해 사용 중인 것으로 보입니다."
                log_warning "해당 포트를 점유한 프로세스를 종료하거나 포트를 변경한 뒤 다시 시도하세요."
                log_warning "docker-compose up은 충돌을 일으킬 수 있어 생략합니다."
            else
                if [[ "$need_tools" -eq 1 ]]; then
                    log_info "Redis Commander 포함하여 MCP 서버들 시작 중..."
                    docker-compose -f $COMPOSE_FILE --profile tools up -d
                else
                    log_info "MCP 서버들 백그라운드 시작 중..."
                    docker-compose -f $COMPOSE_FILE up -d
                fi
                log_success "MCP 서버들이 시작되었습니다"
                echo ""
                log_info "서버 접속 정보:"
                echo "  - ArXiv MCP Server:  http://localhost:3000"
                echo "  - Tavily MCP Server: http://localhost:3001"  
                echo "  - Serper MCP Server: http://localhost:3002"
                if [[ "$need_tools" -eq 1 ]]; then
                    echo "  - Redis Commander:   http://localhost:8081 (admin/mcp2025)"
                fi
            fi
        fi
        ;;
        
    up-fg)
        check_env
        # .env 파일이 있으면 환경 변수로 export
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            log_info ".env 파일에서 환경 변수 로드 중..."
            set -a  # 자동 export 모드 활성화
            source "${PROJECT_ROOT}/.env"
            set +a  # 자동 export 모드 비활성화
            log_success "환경 변수 로드 완료"
        fi
        
        log_info "MCP 서버들 포그라운드 시작 중..."
        docker-compose -f $COMPOSE_FILE up
        ;;
        
    down)
        log_info "MCP 서버들 중지 중..."
        docker-compose -f $COMPOSE_FILE down
        log_success "MCP 서버들이 중지되었습니다"
        ;;
        
    restart)
        # .env 파일이 있으면 환경 변수로 export
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            log_info ".env 파일에서 환경 변수 로드 중..."
            set -a  # 자동 export 모드 활성화
            source "${PROJECT_ROOT}/.env"
            set +a  # 자동 export 모드 비활성화
            log_success "환경 변수 로드 완료"
        fi
        
        log_info "MCP 서버들 재시작 중..."
        docker-compose -f $COMPOSE_FILE restart
        log_success "MCP 서버들이 재시작되었습니다"
        ;;
        
    logs)
        if [ -n "$2" ]; then
            case "$2" in
                tavily)
                    docker-compose -f $COMPOSE_FILE logs -f tavily-mcp
                    ;;
                arxiv)
                    docker-compose -f $COMPOSE_FILE logs -f arxiv-mcp
                    ;;
                serper)
                    docker-compose -f $COMPOSE_FILE logs -f serper-mcp
                    ;;
                redis)
                    docker-compose -f $COMPOSE_FILE logs -f redis
                    ;;
                *)
                    log_error "알 수 없는 서버: $2"
                    log_info "사용 가능한 서버: tavily, arxiv, serper, redis"
                    exit 1
                    ;;
            esac
        else
            docker-compose -f $COMPOSE_FILE logs -f
        fi
        ;;
        
    status)
        log_info "MCP 서버 상태 확인 중..."
        docker-compose -f $COMPOSE_FILE ps
        ;;
        
    clean)
        log_info "미사용 컨테이너 및 이미지 정리 중..."
        docker-compose -f $COMPOSE_FILE down --remove-orphans
        docker system prune -f
        log_success "정리 완료"
        ;;
        
    test)
        log_info "MCP 서버 헬스체크 테스트 중..."
        echo ""
        
        # ArXiv 서버 테스트
        log_info "ArXiv 서버 테스트 (localhost:3000)..."
        if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
            log_success "ArXiv 서버 OK"
        else
            log_error "ArXiv 서버 응답 없음"
        fi
        
        # Tavily 서버 테스트  
        log_info "Tavily 서버 테스트 (localhost:3001)..."
        if curl -f -s http://localhost:3001/health > /dev/null 2>&1; then
            log_success "Tavily 서버 OK"
        else
            log_error "Tavily 서버 응답 없음"
        fi
        
        # Serper 서버 테스트
        log_info "Serper 서버 테스트 (localhost:3002)..."
        if curl -f -s http://localhost:3002/health > /dev/null 2>&1; then
            log_success "Serper 서버 OK"
        else
            log_error "Serper 서버 응답 없음"
        fi
        
        echo ""
        log_info "전체 서비스 상태:"
        docker-compose -f $COMPOSE_FILE ps
        ;;
        
    help|--help|-h)
        show_help
        ;;
        
    *)
        log_error "알 수 없는 명령어: $1"
        echo ""
        show_help
        exit 1
        ;;
esac