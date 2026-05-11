<#
.SYNOPSIS
    One-time setup: create a self-signed code signing certificate and export to a .pfx file.

.DESCRIPTION
    Creates a 3-year self-signed code signing cert in CurrentUser\My, then exports
    it along with its private key to a password-protected .pfx file at
    tools/codesign.pfx (gitignored). Use tools/sign.ps1 to sign binaries with it.

    NOTE: self-signed certs are NOT trusted by Windows SmartScreen. Users will
    still see "Windows protected your PC" warnings. Removing that warning
    requires a CA-issued cert (paid) or SignPath Foundation (free for OSS).

.PARAMETER Subject
    Certificate subject CN. Defaults to "Shreyas P".

.PARAMETER OutPath
    Path for the exported .pfx, relative to repo root. Defaults to tools/codesign.pfx.

.PARAMETER Years
    Validity period. Defaults to 3.

.EXAMPLE
    .\tools\create-cert.ps1
#>
param(
    [string]$Subject = "Shreyas P",
    [string]$OutPath = "tools/codesign.pfx",
    [int]$Years      = 3
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$OutPath  = Join-Path $repoRoot $OutPath

if (Test-Path $OutPath) {
    $resp = Read-Host "$OutPath already exists. Overwrite? (y/N)"
    if ($resp -ne 'y' -and $resp -ne 'Y') { Write-Host "Aborted."; exit 1 }
    Remove-Item $OutPath -Force
}

Write-Host "Creating self-signed code signing certificate..."
Write-Host "  Subject:  CN=$Subject"
Write-Host "  Validity: $Years year(s)"

$cert = New-SelfSignedCertificate `
    -Subject            "CN=$Subject" `
    -Type               CodeSigningCert `
    -KeySpec            Signature `
    -KeyUsage           DigitalSignature `
    -KeyAlgorithm       RSA `
    -KeyLength          2048 `
    -HashAlgorithm      SHA256 `
    -CertStoreLocation  "Cert:\CurrentUser\My" `
    -NotAfter           (Get-Date).AddYears($Years)

Write-Host ""
Write-Host "Certificate created."
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  Store:      Cert:\CurrentUser\My\$($cert.Thumbprint)"
Write-Host ""

$securePass = Read-Host "Enter a password to protect the .pfx" -AsSecureString
$confirm    = Read-Host "Confirm password"                     -AsSecureString

$bstr1 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePass)
$bstr2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirm)
$pass1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr1)
$pass2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr2)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr1)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr2)

if ($pass1 -ne $pass2) {
    Write-Error "Passwords do not match."
    exit 1
}

Export-PfxCertificate `
    -Cert     "Cert:\CurrentUser\My\$($cert.Thumbprint)" `
    -FilePath $OutPath `
    -Password $securePass | Out-Null

Write-Host ""
Write-Host "Exported to: $OutPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Set these in your shell before building:"
Write-Host "       `$env:SIGN_PFX      = '$OutPath'"
Write-Host "       `$env:SIGN_PASSWORD = '<your pfx password>'"
Write-Host "  2. Run: python build.py"
Write-Host ""
Write-Host "KEEP THE .pfx AND PASSWORD SECRET. Both are gitignored."
