[CmdletBinding()]
param(
    [switch]$NoOpen,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Hermes = Join-Path $Root ".venv\Scripts\hermes.exe"
if (-not (Test-Path $Hermes)) {
    throw "Hermes 未安装，请先运行 scripts/bootstrap.ps1"
}

$env:HERMES_HOME = Join-Path $Root ".runtime\hermes"
$env:FINANCE_PROJECT_ROOT = $Root
$env:HERMES_TUI_DIR = Join-Path $Root ".runtime\hermes-tui"

& (Join-Path $PSScriptRoot "sync-hermes-config.ps1")

$TuiEntry = Join-Path $env:HERMES_TUI_DIR "dist\entry.js"
if (-not (Test-Path $TuiEntry)) {
    throw "预构建 Hermes TUI 不存在，请重新运行 scripts/bootstrap.ps1"
}

if (-not $SkipPreflight) {
    & (Join-Path $PSScriptRoot "preflight.ps1")
}

$DashboardArgs = @("dashboard", "--host", "127.0.0.1", "--port", "9119")
if ($NoOpen) { $DashboardArgs += "--no-open" }

Push-Location $Root
try {
    Write-Host "Starting Hermes Dashboard at http://127.0.0.1:9119" -ForegroundColor Cyan
    & $Hermes @DashboardArgs
} finally {
    Pop-Location
}
