#!/usr/bin/env pwsh

$ErrorActionPreference = "Stop"

# Project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

Write-Host "[Step4] Ensuring Redis is running..."
try {
  docker compose -f docker/docker-compose.mcp.yml up -d redis | Out-Null
} catch {}

Write-Host "[Step4] Starting HITL demo..."
python examples/step4_hitl_demo.py


