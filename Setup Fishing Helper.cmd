@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_app.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the message above and data\setup.log.
  pause
)
