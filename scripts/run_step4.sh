#!/usr/bin/env bash

set -euo pipefail

# Project root detection
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# 1) Ensure Redis is up (docker compose)
echo "[Step4] Ensuring Redis is running..."
docker compose -f docker/docker-compose.mcp.yml up -d redis >/dev/null 2>&1 || true

# 2) Run the Step4 demo (which auto-starts HITL web and A2A servers)
echo "[Step4] Starting HITL demo..."
exec python examples/step4_hitl_demo.py


