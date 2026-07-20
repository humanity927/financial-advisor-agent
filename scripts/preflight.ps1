[CmdletBinding()]
param(
    [switch]$RequireModel
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Hermes = Join-Path $Root ".venv\Scripts\hermes.exe"
$HermesHome = Join-Path $Root ".runtime\hermes"
$EnvFile = Join-Path $HermesHome ".env"

if (-not (Test-Path $Python)) {
    throw ".venv 不存在，请先运行 scripts/bootstrap.ps1"
}
if (-not (Test-Path (Join-Path $HermesHome "config.yaml"))) {
    throw "项目 Hermes 配置不存在，请先运行 scripts/bootstrap.ps1"
}

& (Join-Path $PSScriptRoot "sync-hermes-config.ps1")
& (Join-Path $PSScriptRoot "verify-hermes.ps1")
& $Python (Join-Path $PSScriptRoot "local_preflight.py")
if ($LASTEXITCODE -ne 0) { throw "本地金融核心预检失败" }

$env:HERMES_HOME = $HermesHome
$env:FINANCE_PROJECT_ROOT = $Root
& $Hermes mcp test finance
if ($LASTEXITCODE -ne 0) { throw "Hermes 无法连接 finance MCP" }

$ModelArgs = @((Join-Path $PSScriptRoot "model_preflight.py"), "--env-file", $EnvFile)
if ($RequireModel) { $ModelArgs += "--require-model" }
& $Python @ModelArgs
if ($LASTEXITCODE -ne 0) { throw "模型预检失败" }

Write-Host "Preflight passed" -ForegroundColor Green
