@echo off
setlocal
set "SMARTORDER_INSTALL_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -Command "$Script=Join-Path $env:SMARTORDER_INSTALL_ROOT 'Install_and_Start_SmartOrder.ps1'; Unblock-File -LiteralPath $Script; & $Script"
pause
