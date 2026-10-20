@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv and install dependencies first. See docs\APPLICATION.md.
  pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
".venv\Scripts\python.exe" -m visual_targeting.app_gui
if errorlevel 1 pause
