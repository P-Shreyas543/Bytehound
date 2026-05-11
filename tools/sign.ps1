<#
.SYNOPSIS
    Sign a Windows .exe (or .dll) with a PFX certificate using signtool.

.DESCRIPTION
    Wraps signtool.exe with: SHA-256 file digest + RFC 3161 timestamp via DigiCert.
    Locates signtool.exe in the installed Windows 10/11 SDK if not on PATH.

.PARAMETER ExePath
    Path to the file to sign.

.PARAMETER PfxPath
    Path to the .pfx file. Defaults to $env:SIGN_PFX.

.PARAMETER Password
    PFX password. Defaults to $env:SIGN_PASSWORD.

.EXAMPLE
    .\tools\sign.ps1 -ExePath dist\Bytehound\Bytehound.exe
#>
param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [string]$PfxPath  = $env:SIGN_PFX,
    [string]$Password = $env:SIGN_PASSWORD
)

$ErrorActionPreference = "Stop"

if (-not $PfxPath)             { Write-Error "PfxPath not provided and `$env:SIGN_PFX is empty.";       exit 1 }
if (-not $Password)            { Write-Error "Password not provided and `$env:SIGN_PASSWORD is empty."; exit 1 }
if (-not (Test-Path $ExePath)) { Write-Error "File not found: $ExePath";                                exit 1 }
if (-not (Test-Path $PfxPath)) { Write-Error "PFX not found: $PfxPath";                                 exit 1 }

$signtool = $env:SIGNTOOL_PATH
if (-not $signtool -or -not (Test-Path $signtool)) {
    $signtool = $null
    $sdkRoot  = 'C:\Program Files (x86)\Windows Kits\10\bin'
    if (Test-Path $sdkRoot) {
        $signtool = Get-ChildItem $sdkRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
                    Where-Object { $_.FullName -match '\\x64\\' } |
                    Sort-Object FullName -Descending |
                    Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $signtool -or -not (Test-Path $signtool)) {
    Write-Error @"
signtool.exe not found.
Install the 'Windows SDK Signing Tools for Desktop Apps' from:
  https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/
Or set `$env:SIGNTOOL_PATH to the full path of signtool.exe.
"@
    exit 1
}

Write-Host "Signing $ExePath"
Write-Host "  signtool: $signtool"

& $signtool sign `
    /f  $PfxPath `
    /p  $Password `
    /fd sha256 `
    /tr http://timestamp.digicert.com `
    /td sha256 `
    /v `
    $ExePath

if ($LASTEXITCODE -ne 0) {
    Write-Error "signtool failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Signed OK."
