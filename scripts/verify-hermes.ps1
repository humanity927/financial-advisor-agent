[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedSha = "9de9c25f620ff7f1ce0fd5457d596052d5159596"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HermesPath = Join-Path $Root "vendor\hermes-agent"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

$GitlinkLine = & git -C $Root ls-files --stage -- vendor/hermes-agent
if ($LASTEXITCODE -ne 0 -or -not $GitlinkLine) {
    throw "Hermes gitlink is missing from the project index"
}
$GitlinkParts = $GitlinkLine -split '\s+'
if ($GitlinkParts[0] -ne "160000" -or $GitlinkParts[1] -ne $ExpectedSha) {
    throw "Hermes gitlink mismatch. Expected $ExpectedSha, got $GitlinkLine"
}

$HermesProjectFile = Join-Path $HermesPath "pyproject.toml"
if (Test-Path $HermesProjectFile) {
    $ActualSha = (& git -C $HermesPath rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $ActualSha -ne $ExpectedSha) {
        throw "Hermes SHA mismatch. Expected $ExpectedSha, got $ActualSha"
    }

    $Dirty = & git -C $HermesPath status --porcelain
    if ($LASTEXITCODE -ne 0 -or $Dirty) {
        throw "Hermes submodule contains local changes. Do not modify upstream code."
    }

    & git -C $HermesPath diff --exit-code
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes submodule diff check failed"
    }
} else {
    Write-Warning "Hermes source checkout is not initialized; verified pinned gitlink and installed package instead"
}

$ImportPattern = '^\s*(from|import)\s+(agent|hermes_cli|gateway|providers|tools)(\.|\s|$)'
$ForbiddenImports = Get-ChildItem (Join-Path $Root "src") -Recurse -Filter "*.py" |
    Select-String -Pattern $ImportPattern
if ($ForbiddenImports) {
    $ForbiddenImports | ForEach-Object { Write-Error $_.ToString() }
    throw "Business code imports private Hermes modules"
}

if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $PSScriptRoot "verify_install.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Hermes installation verification failed"
    }
} else {
    Write-Warning ".venv does not exist; installed-package check skipped"
}

Write-Host "Hermes upstream pin verified at $ExpectedSha" -ForegroundColor Green
