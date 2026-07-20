[CmdletBinding()]
param(
    [int]$Port = 8123,
    [switch]$NoOpen,
    [switch]$ForceFixture,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $Root ".venv"
$Uvicorn = Join-Path $VenvDir "Scripts\uvicorn.exe"
if (-not (Test-Path $Uvicorn)) {
    throw "Uvicorn 未安装，请先运行 scripts/bootstrap.ps1"
}

$FrontendDir = Join-Path $Root "frontend"
$FrontendDist = Join-Path $FrontendDir "dist"
$FrontendPackage = Join-Path $FrontendDir "package.json"

$env:FINANCE_PROJECT_ROOT = $Root
if ($ForceFixture) {
    $env:FINANCE_FORCE_FIXTURE = "1"
}

if ((Test-Path $FrontendPackage) -and -not (Test-Path (Join-Path $FrontendDist "index.html"))) {
    if ($SkipFrontendBuild) {
        Write-Warning "frontend/dist 不存在，已按参数跳过前端构建"
    } else {
        Push-Location $FrontendDir
        try {
            Write-Host "Building frontend workspace..." -ForegroundColor Cyan
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
        } finally {
            Pop-Location
        }
    }
} elseif (-not (Test-Path $FrontendPackage)) {
    Write-Warning "未找到 frontend/package.json；将仅启动 FastAPI 后端和占位启动页"
}

$Url = "http://127.0.0.1:$Port"
if (-not $NoOpen) {
    Start-Process $Url
}

Push-Location $Root
try {
    Write-Host "Starting finance workspace API at $Url" -ForegroundColor Cyan
    & $Uvicorn "finance_advisor.web.app:app" "--host" "127.0.0.1" "--port" "$Port"
} finally {
    Pop-Location
}
