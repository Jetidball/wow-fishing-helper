param([switch]$VerifyOnly, [switch]$Fishing)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
$logDir = Join-Path $repo 'data'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'setup.log'
$started = $false
try {
    Start-Transcript -Path $log -Append | Out-Null
    $started = $true
    Write-Host 'FISHING HELPER SETUP' -ForegroundColor Cyan
    Write-Host 'This installs the preview app locally. It never enables mouse input.'
    Write-Host '[1/4] Checking Python 3.12 and the Windows GUI components...'
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $launcher) {
        Start-Process 'https://www.python.org/downloads/windows/'
        throw 'Install Python 3.12 (64-bit) with Python Launcher and Tcl/Tk enabled, then double-click Setup Fishing Helper again. The download page has been opened.'
    }
    & $launcher.Source -3.12 -c "import tkinter, venv; import struct; assert struct.calcsize('P') == 8, '64-bit Python required'"
    if ($LASTEXITCODE -ne 0) {
        Start-Process 'https://www.python.org/downloads/windows/'
        throw 'Python 3.12 (64-bit), Python Launcher and Tcl/Tk are required. Install them and run Setup again.'
    }
    $envDir = Join-Path $repo '.venv-app'
    $python = Join-Path $envDir 'Scripts\python.exe'
    if (-not $VerifyOnly) {
        Write-Host '[2/4] Creating the private app environment...'
        if (-not (Test-Path -LiteralPath $python)) {
            & $launcher.Source -3.12 -m venv $envDir
            if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv-app. Check folder permissions.' }
        }
        Write-Host '[3/4] Installing the app (internet required on first setup)...'
        & $python -m pip install --disable-pip-version-check -r (Join-Path $repo 'requirements-inference.txt') "$repo[inference]"
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access and data\setup.log, then run Setup again.' }
        if ($Fishing) {
            Write-Host 'Installing the existing fishing GUI dependencies...'
            & $python -m pip install --disable-pip-version-check -r (Join-Path $repo 'requirements.lock')
            if ($LASTEXITCODE -ne 0) { throw 'Fishing dependencies failed to install. See data\setup.log.' }
        }

    }
    if (-not (Test-Path -LiteralPath $python)) { throw 'App environment missing. Run Setup without -VerifyOnly first.' }
    Write-Host '[4/4] Checking the installed app and GUI...'
    & $python (Join-Path $repo 'tools\install_smoke.py') (Join-Path $logDir 'setup-verification.json')
    if ($LASTEXITCODE -ne 0) { throw 'App verification failed. See data\setup.log.' }
    Write-Host 'SETUP COMPLETE. Use Start Targeting.cmd to open the app.' -ForegroundColor Green
    if (-not $VerifyOnly) { Start-Process (Join-Path $repo 'START HERE.html') }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if ($started) { Stop-Transcript | Out-Null }
}

