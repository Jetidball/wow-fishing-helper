@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-gpu\Scripts\python.exe" goto gpu
if not exist ".venv-app\Scripts\python.exe" (
  call "%~dp0Setup Fishing Helper.cmd"
  if errorlevel 1 exit /b 1
)
".venv-app\Scripts\python.exe" -m visual_targeting.app_gui
if errorlevel 1 (
  echo App could not start. Run Setup Fishing Helper.cmd to repair it.
  pause
)

exit /b
:gpu
".venv-gpu\Scripts\python.exe" -m visual_targeting.app_gui
if errorlevel 1 pause
