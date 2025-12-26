#!/bin/bash
# 사용법: ./setup.sh [command]
#
# 이 스크립트는 다음 3가지 설정을 자동화합니다:
#   1. uv 패키지 매니저 설치 확인/안내
#   2. uv sync --frozen으로 .venv 및 의존성 설치
#   3. VSCode Python 인터프리터 설정

set -e

# ============================================================================
# 색상 정의
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ============================================================================
# 스크립트 위치로 이동
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ============================================================================
# 로깅 함수
# ============================================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}  ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_step() {
    echo -e "\n${CYAN}${BOLD}[$1]${NC} $2"
}

# ============================================================================
# 헤더 출력
# ============================================================================
print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}  ${BOLD}FastCampus MCP & A2A 개발환경 설정${NC}                      ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
}

# ============================================================================
# 도움말 출력
# ============================================================================
show_help() {
    echo -e "${BLUE}FastCampus MCP & A2A 개발환경 설정 스크립트${NC}"
    echo ""
    echo "사용법: ./setup.sh [command]"
    echo ""
    echo "Commands:"
    echo "  (없음)       전체 설정 실행 (기본값)"
    echo "  uv           UV 패키지 매니저 설치 확인/안내"
    echo "  sync         uv sync --frozen 실행 (.venv 생성)"
    echo "  vscode       VSCode 설정 파일 생성"
    echo "  help         이 도움말 출력"
    echo ""
    echo "예시:"
    echo "  ./setup.sh              # 전체 설정 (권장)"
    echo "  ./setup.sh uv           # UV 설치 확인만"
    echo "  ./setup.sh sync         # 의존성 설치만"
    echo "  ./setup.sh vscode       # VSCode 설정만"
    echo ""
}

# ============================================================================
# UV 설치 확인
# ============================================================================
check_uv() {
    if command -v uv &> /dev/null; then
        UV_VERSION=$(uv --version 2>/dev/null | head -n1)
        log_success "uv가 설치되어 있습니다. ($UV_VERSION)"
        return 0
    fi
    return 1
}

# ============================================================================
# UV 설치 안내
# ============================================================================
install_uv_guide() {
    log_error "uv가 설치되어 있지 않습니다."
    echo ""
    echo -e "${YELLOW}설치 방법:${NC}"
    echo ""
    echo "  macOS/Linux:"
    echo -e "    ${CYAN}curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
    echo ""
    echo "  Homebrew (macOS):"
    echo -e "    ${CYAN}brew install uv${NC}"
    echo ""
    echo "  Windows (PowerShell):"
    echo -e "    ${CYAN}powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"${NC}"
    echo ""
    echo -e "${YELLOW}설치 후 터미널을 재시작하고 다시 실행해주세요:${NC}"
    echo -e "    ${CYAN}./setup.sh${NC}"
    echo ""
}

# ============================================================================
# UV 설치 단계 실행
# ============================================================================
do_uv() {
    log_step "1/3" "UV 패키지 매니저 확인 중..."

    if check_uv; then
        return 0
    else
        install_uv_guide
        return 1
    fi
}

# ============================================================================
# 의존성 설치 (uv sync --frozen)
# ============================================================================
do_sync() {
    log_step "2/3" "의존성 설치 중..."

    # uv 설치 확인
    if ! command -v uv &> /dev/null; then
        log_error "uv가 설치되어 있지 않습니다. 먼저 ./setup.sh uv를 실행하세요."
        return 1
    fi

    # uv.lock 파일 확인
    if [ ! -f "uv.lock" ]; then
        log_error "uv.lock 파일이 없습니다. 프로젝트 루트 디렉토리에서 실행하세요."
        return 1
    fi

    echo -e "  ${CYAN}\$ uv sync --frozen${NC}"

    # uv sync 실행
    if uv sync --frozen; then
        log_success ".venv 생성 및 의존성 설치 완료"

        # .venv 확인
        if [ -d ".venv" ]; then
            PYTHON_PATH=$(realpath .venv/bin/python 2>/dev/null || echo ".venv/bin/python")
            log_success "Python 경로: $PYTHON_PATH"
        fi
        return 0
    else
        log_error "의존성 설치에 실패했습니다."
        return 1
    fi
}

# ============================================================================
# VSCode 설정 생성
# ============================================================================
do_vscode() {
    log_step "3/3" "VSCode 설정 중..."

    # .vscode 디렉토리 생성
    mkdir -p .vscode

    # settings.json 생성 (이미 존재하면 백업)
    SETTINGS_FILE=".vscode/settings.json"

    if [ -f "$SETTINGS_FILE" ]; then
        log_warn "기존 settings.json을 백업합니다: ${SETTINGS_FILE}.backup"
        cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup"
    fi

    # settings.json 작성
    cat > "$SETTINGS_FILE" << 'EOF'
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": true
}
EOF

    log_success ".vscode/settings.json 생성 완료"
    return 0
}

# ============================================================================
# 완료 메시지 출력
# ============================================================================
print_success() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}[SUCCESS]${NC} ${BOLD}개발환경 설정이 완료되었습니다!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BOLD}다음 단계:${NC}"
    echo "  1. VSCode 재시작 또는 Python 인터프리터 선택 확인"
    echo "     (Cmd/Ctrl + Shift + P → 'Python: Select Interpreter' → .venv 선택)"
    echo ""
    echo "  2. .env 파일 설정:"
    echo -e "     ${CYAN}cp .env.example .env${NC}"
    echo ""
    echo "  3. API 키 입력 (필수):"
    echo "     - OPENAI_API_KEY"
    echo "     - TAVILY_API_KEY"
    echo "     - SERPER_API_KEY"
    echo ""
    echo "  4. Docker 환경 시작 (선택):"
    echo -e "     ${CYAN}./run_docker.sh up${NC}"
    echo ""
}

# ============================================================================
# 전체 설정 실행
# ============================================================================
do_all() {
    print_header

    # Step 1: UV 확인
    if ! do_uv; then
        exit 1
    fi

    # Step 2: 의존성 설치
    if ! do_sync; then
        exit 1
    fi

    # Step 3: VSCode 설정
    if ! do_vscode; then
        exit 1
    fi

    # 완료 메시지
    print_success
}

# ============================================================================
# 메인 로직
# ============================================================================
case "${1:-all}" in
    all|"")
        do_all
        ;;
    uv)
        print_header
        do_uv
        ;;
    sync)
        print_header
        do_sync
        ;;
    vscode)
        print_header
        do_vscode
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "알 수 없는 명령: $1"
        show_help
        exit 1
        ;;
esac
