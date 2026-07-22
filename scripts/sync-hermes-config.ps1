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
    $ProcessValue = [Environment]::GetEnvironmentVariable($Name)
    if ($ProcessValue) { return $ProcessValue.Trim() }
    if (Test-Path $EnvFile) {
        foreach ($Line in [IO.File]::ReadAllLines($EnvFile, [Text.Encoding]::UTF8)) {
            if ($Line -match "^$([Regex]::Escape($Name))=(.*)$") {
                $Value = $Matches[1].Trim().Trim('"').Trim("'")
                if ($Value) { return $Value }
            }
        }
    }
    return $Default
}

function ConvertTo-YamlSingleQuoted {
    param([string]$Value)
    if ($Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Model configuration values cannot contain newlines"
    }
    return $Value.Replace("'", "''")
}

function Assert-HttpUrl {
    param([string]$Name, [string]$Value)
    $Parsed = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$Parsed) -or
        $Parsed.Scheme -notin @("http", "https")) {
        throw "$Name must be a valid HTTP(S) URL"
    }
}

if (-not (Test-Path $VenvPython)) {
    throw ".venv 不存在，无法生成 Hermes 配置"
}
New-Item -ItemType Directory -Force $RuntimeHome | Out-Null

$RelayBaseUrl = Get-DotEnvValue "RELAY_BASE_URL" "https://example.invalid/v1"
$RelayModelId = Get-DotEnvValue "RELAY_MODEL_ID" "gpt-5.6"
$DeepSeekBaseUrl = Get-DotEnvValue "DEEPSEEK_BASE_URL" "https://api.deepseek.com/v1"
$DeepSeekModelId = Get-DotEnvValue "DEEPSEEK_MODEL_ID" "deepseek-chat"
$RequestTimeoutText = Get-DotEnvValue "MODEL_REQUEST_TIMEOUT_SECONDS" "90"
$TotalTimeoutText = Get-DotEnvValue "HERMES_TOTAL_TIMEOUT_SECONDS" "300"
$MaxRetriesText = Get-DotEnvValue "MODEL_MAX_RETRIES" "1"
$FallbackEnabledText = (Get-DotEnvValue "DEEPSEEK_FALLBACK_ENABLED" "true").ToLowerInvariant()
$FixtureMode = "0"

Assert-HttpUrl "RELAY_BASE_URL" $RelayBaseUrl
Assert-HttpUrl "DEEPSEEK_BASE_URL" $DeepSeekBaseUrl
if (-not $RelayModelId.Trim() -or -not $DeepSeekModelId.Trim()) {
    throw "RELAY_MODEL_ID and DEEPSEEK_MODEL_ID cannot be empty"
}

$RequestTimeout = 0.0
$TotalTimeout = 0.0
$MaxRetries = 0
$Invariant = [Globalization.CultureInfo]::InvariantCulture
$NumberStyle = [Globalization.NumberStyles]::Float
if (-not [double]::TryParse($RequestTimeoutText, $NumberStyle, $Invariant, [ref]$RequestTimeout) -or
    $RequestTimeout -lt 5 -or $RequestTimeout -gt 600) {
    throw "MODEL_REQUEST_TIMEOUT_SECONDS must be between 5 and 600"
}
if (-not [double]::TryParse($TotalTimeoutText, $NumberStyle, $Invariant, [ref]$TotalTimeout) -or
    $TotalTimeout -lt 10 -or $TotalTimeout -gt 1800 -or $TotalTimeout -lt $RequestTimeout) {
    throw "HERMES_TOTAL_TIMEOUT_SECONDS must be between 10 and 1800 and not shorter than the request timeout"
}
if (-not [int]::TryParse($MaxRetriesText, [ref]$MaxRetries) -or $MaxRetries -lt 0 -or $MaxRetries -gt 3) {
    throw "MODEL_MAX_RETRIES must be an integer between 0 and 3"
}
if ($FallbackEnabledText -notin @("1", "true", "yes", "0", "false", "no")) {
    throw "DEEPSEEK_FALLBACK_ENABLED must be true/false, yes/no, or 1/0"
}
$FallbackEnabled = $FallbackEnabledText -in @("1", "true", "yes")

$ForwardRoot = $Root.Replace("\", "/")
$CacheDir = (Join-Path $Root ".runtime\cache").Replace("\", "/")
$FixturePath = (Join-Path $Root "data\fixtures\market_data.json").Replace("\", "/")
$ConfigText = [IO.File]::ReadAllText($TemplatePath, [Text.Encoding]::UTF8)
$ConfigText = $ConfigText.Replace("__PYTHON_EXE__", $VenvPython.Replace("\", "/"))
$ConfigText = $ConfigText.Replace("__PROJECT_ROOT__", $ForwardRoot)
$ConfigText = $ConfigText.Replace("__CACHE_DIR__", $CacheDir)
$ConfigText = $ConfigText.Replace("__FIXTURE_PATH__", $FixturePath)
$ConfigText = $ConfigText.Replace("__RELAY_BASE_URL__", (ConvertTo-YamlSingleQuoted $RelayBaseUrl))
$ConfigText = $ConfigText.Replace("__RELAY_MODEL_ID__", (ConvertTo-YamlSingleQuoted $RelayModelId))
$ConfigText = $ConfigText.Replace("__DEEPSEEK_BASE_URL__", (ConvertTo-YamlSingleQuoted $DeepSeekBaseUrl))
$ConfigText = $ConfigText.Replace("__MODEL_REQUEST_TIMEOUT_SECONDS__", $RequestTimeout.ToString($Invariant))
$ConfigText = $ConfigText.Replace("__MODEL_MAX_RETRIES__", $MaxRetries.ToString($Invariant))
$FallbackBlock = "fallback_providers: []"
if ($FallbackEnabled) {
    $SafeDeepSeekModel = ConvertTo-YamlSingleQuoted $DeepSeekModelId
    $SafeDeepSeekBaseUrl = ConvertTo-YamlSingleQuoted $DeepSeekBaseUrl
    $FallbackBlock = "fallback_providers:`n  - provider: deepseek`n    model: '$SafeDeepSeekModel'`n    base_url: '$SafeDeepSeekBaseUrl'`n    key_env: DEEPSEEK_API_KEY"
}
$ConfigText = $ConfigText.Replace("__FALLBACK_PROVIDERS_BLOCK__", $FallbackBlock)
$ConfigText = $ConfigText.Replace("__FORCE_FIXTURE__", $FixtureMode)
[IO.File]::WriteAllText($ConfigPath, $ConfigText, (New-Object Text.UTF8Encoding($false)))
