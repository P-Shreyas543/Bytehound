#!/usr/bin/env pwsh
# Run ruff over the codebase. Exits non-zero if any issue is found —
# meant for both manual use and CI/pre-commit wiring.
#
# Usage:
#   .\scripts\lint.ps1            # full check (uses pyproject.toml config)
#   .\scripts\lint.ps1 -Fast      # only F821/F822/F823 — the bug-class that
#                                 # broke the app twice during the mixin refactor

param([switch]$Fast)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$ruff = Join-Path $root ".venv\Scripts\ruff.exe"
if (-not (Test-Path $ruff)) {
    Write-Error "ruff.exe not found at $ruff - activate the venv or run: pip install ruff"
    exit 2
}

$targets = @("app", "tests", "scripts")
if ($Fast) {
    & $ruff check --select F821,F822,F823 @targets
} else {
    & $ruff check @targets
}
exit $LASTEXITCODE
