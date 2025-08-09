# PowerShell runner for Step 3 demo (Windows)
# - Starts MCP Docker servers (unless --no-docker)
# - Runs examples/step3_multiagent_systems.py with unbuffered output
# - Saves results to reports/comparison_results_{datetime}.json

param(
  [switch]$NoDocker,
  [switch]$WithTools,
  [switch]$DownAfter
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Resolve project root (script directory is scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

function Show-Usage {
  Write-Host "Usage: run_step3.ps1 [-NoDocker] [-WithTools] [-DownAfter]" -ForegroundColor Yellow
  Write-Host "  -NoDocker   : Do not start/stop MCP Docker servers (assume running)"
  Write-Host "  -WithTools  : Start Redis Commander along with MCP servers"
  Write-Host "  -DownAfter  : Stop MCP Docker servers after the run"
}

try {
  # Ensure .env exists
  if (-not (Test-Path ".env")) {
    if (Test-Path "env.example") {
      Write-Warn ".env not found. Creating from env.example (please edit your keys)."
      Copy-Item "env.example" ".env"
    } else {
      Write-Warn ".env not found and env.example missing. Proceeding without it."
    }
  }

  # Load environment variables from .env if present
  if (Test-Path ".env") {
    Write-Info "Loading environment variables from .env"
    foreach ($line in Get-Content ".env") {
      if ($line -match '^(#|\s*$)') { continue }
      $kv = $line -split '=', 2
      if ($kv.Length -eq 2) {
        $key = $kv[0].Trim()
        $val = $kv[1].Trim().Trim('"')
        [Environment]::SetEnvironmentVariable($key, $val)
      }
    }
  }

  # Verify required tools
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Err "Docker not found"; exit 1 }
  if (-not (Get-Command docker-compose -ErrorAction SilentlyContinue)) { Write-Err "docker-compose not found"; exit 1 }
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Err "python not found"; exit 1 }

  # Start/verify MCP servers unless skipped
  if (-not $NoDocker) {
    Write-Info "Starting or verifying MCP Docker servers (idempotent)..."
    # PowerShell 버전이 존재하면 우선 사용, 없으면 bash 스크립트 사용
    if (Test-Path ./docker/mcp_docker.ps1) {
      if ($WithTools) { & ./docker/mcp_docker.ps1 up -WithTools }
      else { & ./docker/mcp_docker.ps1 up }
    } else {
      if ($WithTools) { & ./docker/mcp_docker.sh up --with-tools }
      else { & ./docker/mcp_docker.sh up }
    }
    Write-Info "Running MCP health checks..."
    if (Test-Path ./docker/mcp_docker.ps1) { & ./docker/mcp_docker.ps1 test }
    else { & ./docker/mcp_docker.sh test }
  } else {
    Write-Info "Skipping Docker start (-NoDocker). Running health checks anyway..."
    if (Test-Path ./docker/mcp_docker.ps1) { & ./docker/mcp_docker.ps1 test }
    else { & ./docker/mcp_docker.sh test }
  }

  Write-Info "Running Step 3 demo (unbuffered output)..."
  $env:PYTHONUNBUFFERED = "1"
  & python examples/step3_multiagent_systems.py
  $runExit = $LASTEXITCODE

  if ($DownAfter -and -not $NoDocker) {
    Write-Info "Stopping MCP Docker servers (-DownAfter)..."
    if (Test-Path ./docker/mcp_docker.ps1) { & ./docker/mcp_docker.ps1 down }
    else { & ./docker/mcp_docker.sh down }
  }

  if ($runExit -eq 0) {
    Write-Ok "Step 3 demo completed successfully."
  } else {
    Write-Err "Step 3 demo exited with code $runExit"
  }

  exit $runExit
} catch {
  Write-Err $_
  exit 1
}


