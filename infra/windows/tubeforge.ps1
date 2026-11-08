<#
.SYNOPSIS
  TubeForge management script for Windows (PowerShell 5.1+).

.DESCRIPTION
  Commands:
    doctor  - check this PC (Windows build, RAM, free disk, tools, folders)
    setup   - create the folder layout, config, Python environment, database and web build
    start   - start the API and both workers, then open the dashboard
    stop    - stop the API and workers
    status  - show running processes and readiness

  Install root (owner decision C3): D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE
  The program lives in <root>\app (this repository). Data, models, database and backups
  live next to it. The path contains spaces, so every path below is quoted.

.EXAMPLE
  & "D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE\app\infra\windows\tubeforge.ps1" doctor
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('doctor', 'setup', 'start', 'stop', 'status')]
    [string]$Command = 'status',

    [string]$InstallRoot = '',

    [int]$Port = 8765,

    # CI / unattended mode: never prompt; read the PostgreSQL superuser password from
    # the TUBEFORGE_PG_SUPERUSER_PASSWORD environment variable.
    [switch]$NonInteractive,

    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- paths
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $InstallRoot) {
    if ($env:TUBEFORGE_HOME) {
        $InstallRoot = $env:TUBEFORGE_HOME
    } elseif ((Split-Path $AppDir -Leaf) -eq 'app') {
        $InstallRoot = Split-Path $AppDir -Parent
    } else {
        $InstallRoot = 'D:\YOUTUBE AUTOMATION SYSTEM SOFTWARE'
    }
}
$Paths = [ordered]@{
    Root    = $InstallRoot
    App     = $AppDir
    Tools   = Join-Path $InstallRoot 'tools'
    Models  = Join-Path $InstallRoot 'models'
    Data    = Join-Path $InstallRoot 'data'
    Media   = Join-Path $InstallRoot 'data\media'
    Work    = Join-Path $InstallRoot 'data\work'
    Backups = Join-Path $InstallRoot 'data\backups'
    Logs    = Join-Path $InstallRoot 'data\logs'
    Run     = Join-Path $InstallRoot 'data\run'
    PgData  = Join-Path $InstallRoot 'pgdata'
    Config  = Join-Path $InstallRoot 'config'
}
$ConfigFile = Join-Path $Paths.Config 'tubeforge.toml'
$VenvScripts = Join-Path $AppDir '.venv\Scripts'
$Processes = @(
    @{ Name = 'api';          Exe = 'tubeforge-api.exe';    Args = @() },
    @{ Name = 'worker-light'; Exe = 'tubeforge-worker.exe'; Args = @('--queues', 'light') },
    @{ Name = 'worker-heavy'; Exe = 'tubeforge-worker.exe'; Args = @('--queues', 'heavy') }
)

function Write-Check([string]$Name, [string]$Level, [string]$Detail) {
    $color = @{ OK = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Cyan' }[$Level]
    Write-Host ('[{0,-4}] {1,-28} {2}' -f $Level, $Name, $Detail) -ForegroundColor $color
}

function Find-Psql {
    $cmd = Get-Command psql -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\psql.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }
    return $null
}

function Find-Ffmpeg {
    $local = Join-Path $Paths.Tools 'ffmpeg.exe'
    if (Test-Path -LiteralPath $local) { return $local }
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Set-TubeForgeEnvironment {
    $env:TUBEFORGE_HOME = $Paths.Root
    $env:TUBEFORGE_CONFIG = $ConfigFile
    $env:TUBEFORGE_PORT = "$Port"
    $env:PYTHONUTF8 = '1'
}

# ---------------------------------------------------------------- doctor
function Invoke-Doctor {
    $failed = $false
    Write-Host "TubeForge doctor - install root: $($Paths.Root)" -ForegroundColor Cyan

    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]$os.BuildNumber
    if ($build -ge 19045) { Write-Check 'Windows build' 'OK' "$($os.Caption) build $build" }
    else { Write-Check 'Windows build' 'WARN' "build $build - Windows 10 22H2 (19045) or newer is required for ESU updates" }
    if ($os.Caption -like '*Windows 10*') {
        Write-Check 'Security updates' 'INFO' 'Windows 10: enrol in the free Consumer ESU programme (Settings > Windows Update)'
    }

    $ramGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    if ($ramGb -ge 7.5) { Write-Check 'RAM' 'OK' "$ramGb GB" } else { Write-Check 'RAM' 'WARN' "$ramGb GB (8 GB recommended)" }

    $qualifier = Split-Path -Path $Paths.Root -Qualifier
    $drive = Get-PSDrive -Name $qualifier.TrimEnd(':') -ErrorAction SilentlyContinue
    if (-not $drive) { Write-Check 'Install drive' 'FAIL' "$qualifier not found"; $failed = $true }
    else {
        $freeGb = [math]::Round($drive.Free / 1GB, 1)
        if ($freeGb -ge 60) { Write-Check "Free space on $qualifier" 'OK' "$freeGb GB" }
        else { Write-Check "Free space on $qualifier" 'WARN' "$freeGb GB (60 GB recommended)" }
    }

    if (Test-Path -LiteralPath (Join-Path $AppDir 'pyproject.toml')) { Write-Check 'Program files' 'OK' $AppDir }
    else { Write-Check 'Program files' 'FAIL' "pyproject.toml not found in $AppDir"; $failed = $true }

    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) { Write-Check 'uv (Python manager)' 'OK' (& uv --version) }
    else { Write-Check 'uv (Python manager)' 'FAIL' 'install: winget install --id=astral-sh.uv -e'; $failed = $true }

    $psql = Find-Psql
    if ($psql) { Write-Check 'PostgreSQL client' 'OK' $psql }
    else { Write-Check 'PostgreSQL client' 'FAIL' 'install PostgreSQL 16 from postgresql.org (data directory on D:)'; $failed = $true }
    $svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($svc) { Write-Check 'PostgreSQL service' $(if ($svc.Status -eq 'Running') { 'OK' } else { 'WARN' }) "$($svc.Name): $($svc.Status)" }
    else { Write-Check 'PostgreSQL service' 'WARN' 'no Windows service found' }

    $ffmpeg = Find-Ffmpeg
    if ($ffmpeg) { Write-Check 'FFmpeg' 'OK' $ffmpeg } else { Write-Check 'FFmpeg' 'WARN' 'not found (needed from Phase 9)' }

    $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
    if ($pnpm) { Write-Check 'pnpm (web build)' 'OK' (& pnpm --version) } else { Write-Check 'pnpm (web build)' 'WARN' 'not found - dashboard shows a placeholder until built' }

    try {
        $tz = (Get-TimeZone).Id
        Write-Check 'Time zone' 'INFO' $tz
    } catch { Write-Check 'Time zone' 'WARN' 'unknown' }

    if ($failed) { Write-Host 'Doctor found blocking problems (FAIL).' -ForegroundColor Red; return 1 }
    Write-Host 'Doctor finished: no blocking problems.' -ForegroundColor Green
    return 0
}

# ---------------------------------------------------------------- setup
function New-RandomSecret([int]$Bytes = 24) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    return ([Convert]::ToBase64String($buffer)).Replace('+', 'A').Replace('/', 'B').Replace('=', '')
}

function Write-Config {
    if (Test-Path -LiteralPath $ConfigFile) { Write-Check 'Config' 'OK' "kept existing $ConfigFile"; return }
    $webDist = Join-Path $AppDir 'apps\web\dist'
    # TOML literal strings ('...') keep backslashes as-is. No secrets in this file.
    $content = @(
        '# TubeForge settings (non-secret). Secrets are never stored here.',
        'env = "prod"',
        ("home_dir = '{0}'" -f $Paths.Root),
        ("web_dist_dir = '{0}'" -f $webDist),
        'database_url = "postgresql+psycopg://tubeforge@127.0.0.1:5432/tubeforge"',
        'log_level = "INFO"'
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($ConfigFile, $content + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Check 'Config' 'OK' "created $ConfigFile"
}

function Initialize-Database {
    $psql = Find-Psql
    if (-not $psql) { throw 'PostgreSQL client (psql) not found. Install PostgreSQL 16 first.' }

    # Password for the 'tubeforge' role lives only in the user's libpq password file
    # (%APPDATA%\postgresql\pgpass.conf), never in TubeForge config or the repository.
    $pgpassDir = Join-Path $env:APPDATA 'postgresql'
    $pgpass = Join-Path $pgpassDir 'pgpass.conf'
    New-Item -ItemType Directory -Force -Path $pgpassDir | Out-Null
    $existing = ''
    if (Test-Path -LiteralPath $pgpass) { $existing = Get-Content -LiteralPath $pgpass -Raw }
    if ($existing -match '(?m)^127\.0\.0\.1:5432:tubeforge:tubeforge:') {
        Write-Check 'Database login' 'OK' 'pgpass entry exists'
        return
    }

    if ($NonInteractive) {
        $superPassword = $env:TUBEFORGE_PG_SUPERUSER_PASSWORD
        if (-not $superPassword) { throw 'TUBEFORGE_PG_SUPERUSER_PASSWORD is required with -NonInteractive' }
    } else {
        $secure = Read-Host 'PostgreSQL "postgres" superuser password (used once to create the TubeForge database)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $superPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }

    $rolePassword = New-RandomSecret
    $env:PGPASSWORD = $superPassword
    try {
        $sqlRole = "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tubeforge') THEN CREATE ROLE tubeforge LOGIN; END IF; END `$`$;"
        & $psql -h 127.0.0.1 -p 5432 -U postgres -v ON_ERROR_STOP=1 -q -c $sqlRole | Out-Null
        & $psql -h 127.0.0.1 -p 5432 -U postgres -v ON_ERROR_STOP=1 -q -c ("ALTER ROLE tubeforge PASSWORD '{0}'" -f $rolePassword) | Out-Null
        $exists = & $psql -h 127.0.0.1 -p 5432 -U postgres -tA -c "SELECT 1 FROM pg_database WHERE datname = 'tubeforge'"
        if (-not $exists) {
            & $psql -h 127.0.0.1 -p 5432 -U postgres -v ON_ERROR_STOP=1 -q -c 'CREATE DATABASE tubeforge OWNER tubeforge' | Out-Null
        }
    } finally {
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        $superPassword = $null
    }
    Add-Content -LiteralPath $pgpass -Value ("127.0.0.1:5432:tubeforge:tubeforge:{0}" -f $rolePassword) -Encoding ASCII
    Write-Check 'Database' 'OK' "role and database 'tubeforge' ready; password stored in $pgpass"
}

function Invoke-Setup {
    foreach ($key in $Paths.Keys) {
        if ($key -ne 'App') { New-Item -ItemType Directory -Force -Path $Paths[$key] | Out-Null }
    }
    Write-Check 'Folders' 'OK' "created under $($Paths.Root)"
    Write-Config
    Set-TubeForgeEnvironment

    Push-Location -LiteralPath $AppDir
    try {
        # Keep uv's cache on the same drive as the venv (D:), as DEPLOYMENT_GUIDE §2.4 says.
        # This also lets uv hardlink instead of copying (no 'Failed to hardlink' warning).
        $env:UV_CACHE_DIR = Join-Path $AppDir '.cache\uv'
        & uv sync --frozen --no-dev
        if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
        Write-Check 'Python environment' 'OK' (Join-Path $AppDir '.venv')

        Initialize-Database
        & (Join-Path $VenvScripts 'tubeforge-db.exe') upgrade
        if ($LASTEXITCODE -ne 0) { throw 'database migration failed' }
        Write-Check 'Database schema' 'OK' 'migrations applied'

        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            & pnpm -C (Join-Path $AppDir 'apps\web') install --frozen-lockfile
            & pnpm -C (Join-Path $AppDir 'apps\web') build
            if ($LASTEXITCODE -eq 0) { Write-Check 'Dashboard build' 'OK' 'apps\web\dist' }
        } else {
            Write-Check 'Dashboard build' 'WARN' 'pnpm not found - placeholder page will be shown'
        }
    } finally { Pop-Location }

    if (-not $NonInteractive) { New-DesktopShortcut }
    Write-Host "Setup complete. Start TubeForge with: tubeforge.ps1 start" -ForegroundColor Green
}

function New-DesktopShortcut {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnk = Join-Path $desktop 'TubeForge.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnk)
    $shortcut.TargetPath = 'powershell.exe'
    $shortcut.Arguments = ('-NoProfile -ExecutionPolicy Bypass -File "{0}" start' -f (Join-Path $PSScriptRoot 'tubeforge.ps1'))
    $shortcut.WorkingDirectory = $AppDir
    $shortcut.Save()
    Write-Check 'Desktop shortcut' 'OK' $lnk
}

# ---------------------------------------------------------------- start / stop / status
function Get-PidFile([string]$Name) { return Join-Path $Paths.Run "$Name.pid" }

function Get-RunningProcess([string]$Name) {
    $pidFile = Get-PidFile $Name
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    $procId = [int](Get-Content -LiteralPath $pidFile -Raw)
    return Get-Process -Id $procId -ErrorAction SilentlyContinue
}

function Invoke-Start {
    New-Item -ItemType Directory -Force -Path $Paths.Run, $Paths.Logs | Out-Null
    Set-TubeForgeEnvironment
    foreach ($p in $Processes) {
        if (Get-RunningProcess $p.Name) { Write-Check $p.Name 'OK' 'already running'; continue }
        $exe = Join-Path $VenvScripts $p.Exe
        if (-not (Test-Path -LiteralPath $exe)) { throw "$exe not found - run 'tubeforge.ps1 setup' first" }
        $startArgs = @{
            FilePath               = $exe
            WorkingDirectory       = $AppDir
            RedirectStandardOutput = (Join-Path $Paths.Logs "$($p.Name).log")
            RedirectStandardError  = (Join-Path $Paths.Logs "$($p.Name).err.log")
            WindowStyle            = 'Hidden'
            PassThru               = $true
        }
        if ($p.Args.Count -gt 0) { $startArgs.ArgumentList = $p.Args }
        $proc = Start-Process @startArgs
        Set-Content -LiteralPath (Get-PidFile $p.Name) -Value $proc.Id -Encoding ASCII
        Write-Check $p.Name 'OK' "started (pid $($proc.Id))"
    }
    $url = "http://127.0.0.1:$Port"
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-RestMethod -Uri "$url/healthz" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 1 }
    }
    Invoke-Status | Out-Null
    if (-not $NoBrowser -and -not $NonInteractive) { Start-Process $url }
}

function Invoke-Stop {
    foreach ($p in $Processes) {
        $proc = Get-RunningProcess $p.Name
        if ($proc) {
            Stop-Process -Id $proc.Id -Force
            Write-Check $p.Name 'OK' "stopped (pid $($proc.Id))"
        } else {
            Write-Check $p.Name 'INFO' 'not running'
        }
        Remove-Item -LiteralPath (Get-PidFile $p.Name) -ErrorAction SilentlyContinue
    }
}

function Invoke-Status {
    $allUp = $true
    foreach ($p in $Processes) {
        $proc = Get-RunningProcess $p.Name
        if ($proc) {
            $mb = [math]::Round($proc.WorkingSet64 / 1MB)
            Write-Check $p.Name 'OK' "running (pid $($proc.Id), $mb MB)"
        } else { Write-Check $p.Name 'WARN' 'not running'; $allUp = $false }
    }
    try {
        $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/readyz" -TimeoutSec 3
        Write-Check 'Readiness' 'OK' $ready.status
    } catch {
        Write-Check 'Readiness' 'WARN' 'API not ready (see data\logs)'
        $allUp = $false
    }
    if ($allUp) { return 0 } else { return 1 }
}

# ---------------------------------------------------------------- main
switch ($Command) {
    'doctor' { exit (Invoke-Doctor) }
    'setup'  { Invoke-Setup; exit 0 }
    'start'  { Invoke-Start; exit 0 }
    'stop'   { Invoke-Stop; exit 0 }
    'status' { exit (Invoke-Status) }
}
