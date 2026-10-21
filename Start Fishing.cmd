@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-gpu\Scripts\python.exe" goto gpu
if not exist ".venv-app\Scripts\python.exe" goto setup
".venv-app\Scripts\python.exe" -c "import loguru, pynput, pywinauto, pyautogui, PIL, pytesseract" >nul 2>&1
if errorlevel 1 goto setup
goto launch
:setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_app.ps1" -Fishing
if errorlevel 1 (
  pause
  exit /b 1
)
:launch
".venv-app\Scripts\python.exe" "%~dp0src\state_machine.py"
if errorlevel 1 pause

exit /b
:gpu
".venv-gpu\Scripts\python.exe" "%~dp0src\state_machine.py"
if errorlevel 1 pause
