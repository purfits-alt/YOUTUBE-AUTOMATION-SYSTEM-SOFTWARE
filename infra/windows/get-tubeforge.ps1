<#
.SYNOPSIS
  Download (or update) TubeForge into D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app.

.DESCRIPTION
  Uses git if it is installed (recommended: makes updates easy), otherwise downloads the
  branch as a ZIP from GitHub. Nothing else is installed or changed.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File get-tubeforge.ps1 -Branch phase-1-foundation
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE',
    [string]$Branch = 'main',
    [string]$Repository = 'purfits-alt/YOUTUBE-AUTOMATION-SYSTEM-SOFTWARE'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$appDir = Join-Path $InstallRoot 'app'
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    if (Test-Path -LiteralPath (Join-Path $appDir '.git')) {
        & git -C $appDir fetch origin $Branch
        & git -C $appDir checkout $Branch
        & git -C $appDir pull --ff-only origin $Branch
    } else {
        & git clone --branch $Branch "https://github.com/$Repository.git" $appDir
    }
    if ($LASTEXITCODE -ne 0) { throw 'git failed' }
} else {
    if (Test-Path -LiteralPath $appDir) { throw "$appDir exists. Install git for updates, or rename that folder first." }
    $zip = Join-Path $env:TEMP "tubeforge-$Branch.zip"
    $extract = Join-Path $env:TEMP "tubeforge-$Branch"
    Invoke-WebRequest -Uri "https://github.com/$Repository/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path -LiteralPath $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract
    $inner = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    Move-Item -LiteralPath $inner.FullName -Destination $appDir
    Remove-Item -LiteralPath $zip, $extract -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "TubeForge files are in: $appDir" -ForegroundColor Green
Write-Host "Planning documents:     $(Join-Path $appDir 'docs')"
Write-Host "Next step:              & `"$(Join-Path $appDir 'infra\windows\tubeforge.ps1')`" doctor"
