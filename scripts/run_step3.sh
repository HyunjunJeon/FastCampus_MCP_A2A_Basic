#!/usr/bin/env bash
# Cross-platform (macOS/Linux) runner for Step 3 demo
# - Starts MCP Docker servers (unless --no-docker)
# - Runs examples/step3_multiagent_systems.py with unbuffered output
# - Saves results to reports/comparison_results_{datetime}.json

set -euo pipefail

# Resolve project root (script directory is scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*"; }

NO_DOCKER=0
WITH_TOOLS=0
DOWN_AFTER=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --no-docker     Do not start/stop MCP Docker servers (assume already running)
  --with-tools    Start Redis Commander along with MCP servers
  --down-after    Stop MCP Docker servers after the run
  -h, --help      Show this help

Examples:
  $(basename "$0")
  $(basename "$0") --with-tools
  $(basename "$0") --no-docker
  $(basename "$0") --down-after
EOF
}

for arg in "$@"; do
  case "$arg" in
    --no-docker) NO_DOCKER=1 ;;
    --with-tools) WITH_TOOLS=1 ;;
    --down-after) DOWN_AFTER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) warn "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

# Ensure .env exists
if [[ ! -f ./.env ]]; then
  if [[ -f ./env.example ]]; then
    warn ".env not found. Creating from env.example (please edit your keys)."
    cp ./env.example ./.env
  else
    warn ".env not found and env.example missing. Proceeding without it."
  fi
fi

# Export environment variables from .env if present
if [[ -f ./.env ]]; then
  log "Loading environment variables from .env"
  set -a
  # shellcheck disable=SC1091
  source ./.env
  set +a
fi

# Verify required tools
command -v docker >/dev/null 2>&1 || { err "Docker not found"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { err "docker-compose not found"; exit 1; }
command -v python >/dev/null 2>&1 || { err "python not found"; exit 1; }

# Start MCP servers unless skipped
if [[ "$NO_DOCKER" -eq 0 ]]; then
  log "Starting MCP Docker servers..."
  if [[ "$WITH_TOOLS" -eq 1 ]]; then
    ./docker/mcp_docker.sh up --with-tools
  else
    ./docker/mcp_docker.sh up
  fi

  log "Running MCP health checks..."
  ./docker/mcp_docker.sh test || true
else
  log "Skipping Docker start (--no-docker). Running health checks anyway..."
  ./docker/mcp_docker.sh test || true
fi

log "Running Step 3 demo (unbuffered output)..."
PYTHONUNBUFFERED=1 python examples/step3_multiagent_systems.py
RUN_EXIT=$?

if [[ "$DOWN_AFTER" -eq 1 && "$NO_DOCKER" -eq 0 ]]; then
  log "Stopping MCP Docker servers (--down-after)..."
  ./docker/mcp_docker.sh down || true
fi

if [[ $RUN_EXIT -eq 0 ]]; then
  ok "Step 3 demo completed successfully."
else
  err "Step 3 demo exited with code $RUN_EXIT"
fi

exit $RUN_EXIT


