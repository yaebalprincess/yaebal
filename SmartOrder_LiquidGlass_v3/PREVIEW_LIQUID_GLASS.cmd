@echo off
setlocal
cd /d "%~dp0"
set "GLASS_VENV=%LOCALAPPDATA%\SmartOrder\glass-preview-venv-py312"
set "GLASS_PYTHON=%GLASS_VENV%\Scripts\python.exe"
if exist "%GLASS_PYTHON%" goto dependencies
py.exe -3.12 -m venv "%GLASS_VENV%"
if errorlevel 1 goto failed
:dependencies
"%GLASS_PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
"%GLASS_PYTHON%" tools\preview_liquid_glass.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Preview could not start. Python 3.12 x64 and the listed dependencies are required.
pause
exit /b 1
