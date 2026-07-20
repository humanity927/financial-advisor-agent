[CmdletBinding()]
param(
    [string]$PythonCommand = "python",
    [switch]$SkipSubmoduleNetwork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$HermesPath = Join-Path $Root "vendor\hermes-agent"
$ExpectedSha = "9de9c25f620ff7f1ce0fd5457d596052d5159596"
$Tsinghua = "https://pypi.tuna.tsinghua.edu.cn/simple"
$Aliyun = "https://mirrors.aliyun.com/pypi/simple"

function Invoke-PipInstall {
    param([string[]]$Arguments)
    & $VenvPython -m pip install --index-url $Tsinghua --timeout 120 @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "清华源安装失败，改用阿里云源重试"
        & $VenvPython -m pip install --index-url $Aliyun --timeout 120 @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "依赖安装失败：$($Arguments -join ' ')"
        }
    }
}

Push-Location $Root
try {
    $VersionText = & $PythonCommand -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); raise SystemExit(not ((3,11) <= sys.version_info[:2] < (3,14)))"
    if ($LASTEXITCODE -ne 0) {
        throw "需要 Python >=3.11,<3.14，当前版本：$VersionText"
    }

    if (-not (Test-Path $VenvPython)) {
        & $PythonCommand -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) { throw "创建 .venv 失败" }
    }

    & $VenvPython -m pip config --site set global.index-url $Tsinghua
    & $VenvPython -m pip config --site set global.timeout 120
    Invoke-PipInstall @("--upgrade", "pip", "setuptools>=77,<83", "wheel")

    $UseVendorHermes = Test-Path (Join-Path $HermesPath "pyproject.toml")
    if (-not $UseVendorHermes -and -not $SkipSubmoduleNetwork) {
        & git submodule update --init --depth 1 vendor/hermes-agent
        $UseVendorHermes = $LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $HermesPath "pyproject.toml"))
        if (-not $UseVendorHermes) {
            Write-Warning "GitHub submodule 初始化失败，将安装国内 PyPI 上的官方 hermes-agent==0.18.2"
        }
    }
    if ($UseVendorHermes) {
        & git -C $HermesPath checkout --detach $ExpectedSha
        if ($LASTEXITCODE -ne 0) { throw "无法检出固定 Hermes 提交" }
        Invoke-PipInstall @("${HermesPath}[mcp,web]")
    } else {
        Invoke-PipInstall @("hermes-agent[mcp,web]==0.18.2")
    }
    Invoke-PipInstall @("-e", "${Root}[dev]")

    $RuntimeHome = Join-Path $Root ".runtime\hermes"
    $CacheDir = Join-Path $Root ".runtime\cache"
    $LogsDir = Join-Path $Root ".runtime\logs"
    New-Item -ItemType Directory -Force $RuntimeHome, $CacheDir, $LogsDir | Out-Null

    $RuntimeEnv = Join-Path $RuntimeHome ".env"
    if (-not (Test-Path $RuntimeEnv)) {
        Copy-Item (Join-Path $Root ".env.example") $RuntimeEnv
    }
    & (Join-Path $PSScriptRoot "sync-hermes-config.ps1")

    $BundledTui = Join-Path $VenvDir "Lib\site-packages\hermes_cli\tui_dist\entry.js"
    if (-not (Test-Path $BundledTui)) { throw "Hermes wheel 缺少预构建 TUI entry.js" }
    $RuntimeTuiDist = Join-Path $Root ".runtime\hermes-tui\dist"
    New-Item -ItemType Directory -Force $RuntimeTuiDist | Out-Null
    Copy-Item -Force $BundledTui (Join-Path $RuntimeTuiDist "entry.js")

    $env:HERMES_HOME = $RuntimeHome
    $env:HERMES_TUI_DIR = Join-Path $Root ".runtime\hermes-tui"
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip check 失败" }
    & (Join-Path $VenvDir "Scripts\hermes.exe") --version
    & (Join-Path $VenvDir "Scripts\hermes.exe") doctor

    & (Join-Path $PSScriptRoot "verify-hermes.ps1")
    Write-Host "环境安装完成。请编辑 $RuntimeEnv 后运行 scripts/run-dashboard.ps1" -ForegroundColor Green
} finally {
    Pop-Location
}
