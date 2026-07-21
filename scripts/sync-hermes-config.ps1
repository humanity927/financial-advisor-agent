[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$RuntimeHome = Join-Path $Root ".runtime\hermes"
$EnvFile = Join-Path $RuntimeHome ".env"
$TemplatePath = Join-Path $Root "config\hermes-config.template.yaml"
$ConfigPath = Join-Path $RuntimeHome "config.yaml"

function Get-DotEnvValue {
    param(
        [string]$Name,
        [string]$Default
    )
    if (-not (Test-Path $EnvFile)) { return $Default }
    foreach ($Line in [IO.File]::ReadAllLines($EnvFile, [Text.Encoding]::UTF8)) {
        if ($Line -match "^$([Regex]::Escape($Name))=(.*)$") {
            $Value = $Matches[1].Trim().Trim('"').Trim("'")
            if ($Value) { return $Value }
        }
    }
    return $Default
}

if (-not (Test-Path $VenvPython)) {
    throw ".venv 不存在，无法生成 Hermes 配置"
}
New-Item -ItemType Directory -Force $RuntimeHome | Out-Null

$RelayBaseUrl = Get-DotEnvValue "RELAY_BASE_URL" "https://example.invalid/v1"
$RelayModelId = Get-DotEnvValue "RELAY_MODEL_ID" "gpt-5.6"
$FixtureMode = "0"

$ForwardRoot = $Root.Replace("\", "/")
$CacheDir = (Join-Path $Root ".runtime\cache").Replace("\", "/")
$FixturePath = (Join-Path $Root "data\fixtures\market_data.json").Replace("\", "/")
$ConfigText = [IO.File]::ReadAllText($TemplatePath, [Text.Encoding]::UTF8)
$ConfigText = $ConfigText.Replace("__PYTHON_EXE__", $VenvPython.Replace("\", "/"))
$ConfigText = $ConfigText.Replace("__PROJECT_ROOT__", $ForwardRoot)
$ConfigText = $ConfigText.Replace("__CACHE_DIR__", $CacheDir)
$ConfigText = $ConfigText.Replace("__FIXTURE_PATH__", $FixturePath)
$ConfigText = $ConfigText.Replace("__RELAY_BASE_URL__", $RelayBaseUrl.Replace('"', ''))
$ConfigText = $ConfigText.Replace("__RELAY_MODEL_ID__", $RelayModelId.Replace('"', ''))
$ConfigText = $ConfigText.Replace("__FORCE_FIXTURE__", $FixtureMode)
[IO.File]::WriteAllText($ConfigPath, $ConfigText, (New-Object Text.UTF8Encoding($false)))
