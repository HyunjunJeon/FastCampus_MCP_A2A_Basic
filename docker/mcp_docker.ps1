Param(
  [Parameter(Position=0)]
  [ValidateSet('build','up','up-fg','down','restart','logs','status','clean','test','help')]
  [string]$Command = 'help',

  [Parameter(Position=1)]
  [string]$Arg1,

  [switch]$WithTools
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }

# Resolve project root (script directory is docker/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

$ComposeFile = Join-Path $ProjectRoot "docker/docker-compose.mcp.yml"

function Show-Help {
  Write-Host @"
MCP 서버 Docker 관리 스크립트 (PowerShell)

사용법:
  .\docker\mcp_docker.ps1 <command> [options]

명령어:
  build         모든 MCP 서버 이미지 빌드
  up            모든 MCP 서버 시작 (백그라운드, 아이덤포턴트)
  up-fg         모든 MCP 서버 시작 (포그라운드)
  down          모든 MCP 서버 중지
  restart       모든 MCP 서버 재시작
  logs          모든 서버 로그 확인
  logs <server> 특정 서버 로그 확인 (tavily, arxiv, serper, redis)
  status        서버 상태 확인
  clean         중지된 컨테이너 및 미사용 이미지 정리
  test          모든 서버 헬스체크 테스트

옵션:
  -WithTools    Redis Commander 포함 실행
"@
}

function Load-EnvFile {
  $envPath = Join-Path $ProjectRoot ".env"
  if (Test-Path $envPath) {
    Write-Info "Loading environment variables from .env"
    Get-Content $envPath | ForEach-Object {
      if ($_ -match '^(#|\s*$)') { return }
      $kv = $_ -split '=', 2
      if ($kv.Length -eq 2) {
        $key = $kv[0].Trim()
        $val = $kv[1].Trim().Trim('"')
        [Environment]::SetEnvironmentVariable($key, $val)
      }
    }
    Write-Ok "환경 변수 로드 완료"
  } else {
    Write-Warn ".env 파일이 없습니다. env.example을 참고하여 생성하세요."
  }
}

# Utilities (parity with bash version)
function Test-HealthOk([int]$Port) {
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 3
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
  } catch { return $false }
}

function Test-PortInUse([int]$Port) {
  try {
    return [bool](Test-NetConnection -ComputerName 'localhost' -Port $Port -InformationLevel Quiet)
  } catch { return $false }
}

function Test-ContainerRunning([string]$Name) {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $false }
  $names = docker ps --format "{{.Names}}" 2>$null
  if (-not $names) { return $false }
  return ($names -split "`r?`n" | Where-Object { $_ -eq $Name }).Count -gt 0
}

function Test-DockerServiceHealthy([string]$Name, [int]$Port) {
  return (Test-ContainerRunning $Name) -and (Test-HealthOk $Port)
}

switch ($Command) {
  'build' {
    Load-EnvFile
    Write-Info "MCP 서버 이미지 빌드 중..."
    & docker-compose -f $ComposeFile build
    Write-Ok "이미지 빌드 완료"
  }

  'up' {
    Load-EnvFile

    $needTools = [int]($WithTools.IsPresent)

    $coreOk = 0
    if ( (Test-DockerServiceHealthy 'mcp_arxiv_server' 3000) -and
         (Test-DockerServiceHealthy 'mcp_tavily_server' 3001) -and
         (Test-DockerServiceHealthy 'mcp_serper_server' 3002) ) { $coreOk = 1 }

    if ($coreOk -eq 1) {
      if ($needTools -eq 1) {
        if (Test-ContainerRunning 'mcp_redis_commander' -or (Test-PortInUse 8081)) {
          Write-Info "코어 MCP 서버와 도구가 이미 실행 중입니다. 재실행을 건너뜁니다."
        } else {
          Write-Info "코어 MCP 서버는 실행 중입니다. 도구 프로필만 시작합니다..."
          & docker-compose -f $ComposeFile --profile tools up -d
          Write-Ok "Redis Commander 가 시작되었습니다"
        }
      } else {
        Write-Info "MCP 코어 서버가 이미 실행 중입니다. 재실행을 건너뜁니다."
      }
      Write-Host
      Write-Info "서버 접속 정보:"
      Write-Host "  - ArXiv MCP Server:  http://localhost:3000"
      Write-Host "  - Tavily MCP Server: http://localhost:3001"
      Write-Host "  - Serper MCP Server: http://localhost:3002"
      if ($needTools -eq 1) { Write-Host "  - Redis Commander:   http://localhost:8081 (admin/mcp2025)" }
    } else {
      $anyPortBusy = 0
      foreach ($p in 3000,3001,3002) {
        if ( (Test-PortInUse $p) -and -not (Test-HealthOk $p) ) { $anyPortBusy = 1 }
      }
      if ($anyPortBusy -eq 1) {
        Write-Warn "일부 포트(3000/3001/3002)가 다른 프로세스에 의해 사용 중인 것으로 보입니다."
        Write-Warn "해당 포트를 점유한 프로세스를 종료하거나 포트를 변경한 뒤 다시 시도하세요."
        Write-Warn "docker-compose up은 충돌을 일으킬 수 있어 생략합니다."
      } else {
        if ($needTools -eq 1) {
          Write-Info "Redis Commander 포함하여 MCP 서버들 시작 중..."
          & docker-compose -f $ComposeFile --profile tools up -d
        } else {
          Write-Info "MCP 서버들 백그라운드 시작 중..."
          & docker-compose -f $ComposeFile up -d
        }
        Write-Ok "MCP 서버들이 시작되었습니다"
        Write-Host
        Write-Info "서버 접속 정보:"
        Write-Host "  - ArXiv MCP Server:  http://localhost:3000"
        Write-Host "  - Tavily MCP Server: http://localhost:3001"
        Write-Host "  - Serper MCP Server: http://localhost:3002"
        if ($needTools -eq 1) { Write-Host "  - Redis Commander:   http://localhost:8081 (admin/mcp2025)" }
      }
    }
  }

  'up-fg' {
    Load-EnvFile
    Write-Info "MCP 서버들 포그라운드 시작 중..."
    & docker-compose -f $ComposeFile up
  }

  'down' {
    Write-Info "MCP 서버들 중지 중..."
    & docker-compose -f $ComposeFile down
    Write-Ok "MCP 서버들이 중지되었습니다"
  }

  'restart' {
    Load-EnvFile
    Write-Info "MCP 서버들 재시작 중..."
    & docker-compose -f $ComposeFile restart
    Write-Ok "MCP 서버들이 재시작되었습니다"
  }

  'logs' {
    if ($Arg1) {
      switch ($Arg1) {
        'tavily' { & docker-compose -f $ComposeFile logs -f tavily-mcp }
        'arxiv'  { & docker-compose -f $ComposeFile logs -f arxiv-mcp }
        'serper' { & docker-compose -f $ComposeFile logs -f serper-mcp }
        'redis'  { & docker-compose -f $ComposeFile logs -f redis }
        default  { Write-Err "알 수 없는 서버: $Arg1"; Write-Info "사용 가능한 서버: tavily, arxiv, serper, redis"; exit 1 }
      }
    } else {
      & docker-compose -f $ComposeFile logs -f
    }
  }

  'status' {
    Write-Info "MCP 서버 상태 확인 중..."
    & docker-compose -f $ComposeFile ps
  }

  'clean' {
    Write-Info "미사용 컨테이너 및 이미지 정리 중..."
    & docker-compose -f $ComposeFile down --remove-orphans
    & docker system prune -f
    Write-Ok "정리 완료"
  }

  'test' {
    Write-Info "MCP 서버 헬스체크 테스트 중..."
    Write-Host

    Write-Info "ArXiv 서버 테스트 (localhost:3000)..."
    if (Test-HealthOk 3000) { Write-Ok "ArXiv 서버 OK" } else { Write-Err "ArXiv 서버 응답 없음" }

    Write-Info "Tavily 서버 테스트 (localhost:3001)..."
    if (Test-HealthOk 3001) { Write-Ok "Tavily 서버 OK" } else { Write-Err "Tavily 서버 응답 없음" }

    Write-Info "Serper 서버 테스트 (localhost:3002)..."
    if (Test-HealthOk 3002) { Write-Ok "Serper 서버 OK" } else { Write-Err "Serper 서버 응답 없음" }

    Write-Host
    Write-Info "전체 서비스 상태:"
    & docker-compose -f $ComposeFile ps
  }

  default { Show-Help }
}


