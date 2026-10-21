@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-gpu\Scripts\python.exe" goto install
if not exist ".venv-app\Scripts\python.exe" call "Setup Fishing Helper.cmd"
".venv-app\Scripts\python.exe" -m venv .venv-gpu
if errorlevel 1 goto failed
:install
".venv-gpu\Scripts\python.exe" -m pip install -r requirements.lock
if errorlevel 1 goto failed
".venv-gpu\Scripts\python.exe" tools\setup_gpu.py
if errorlevel 1 goto failed
echo GPU setup complete. Reopen Start Fishing.cmd or Start Targeting.cmd.
pause
exit /b 0
:failed
echo GPU setup failed. CPU fallback is disabled. Check the error above.
pause
exit /b 1
