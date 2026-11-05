@echo off
setlocal
set "SMARTORDER_BUILD_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -Command "Get-ChildItem -LiteralPath $env:SMARTORDER_BUILD_ROOT -Filter '*.ps1' -File | Unblock-File; & (Join-Path $env:SMARTORDER_BUILD_ROOT 'Build_SmartOrder.ps1')"
set "BUILD_EXIT=%ERRORLEVEL%"
if not "%BUILD_EXIT%"=="0" echo Build failed. If signatures are required by organization policy, contact your administrator.
pause
exit /b %BUILD_EXIT%
