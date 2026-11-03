@echo off
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Edit_Update_News.ps1" -NetworkRoot "%~dp0."
if errorlevel 1 pause
