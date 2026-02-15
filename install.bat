@echo off
setlocal EnableExtensions

rem Ensure UTF-8 output (best-effort)
rem NOTE: Keep CRLF line endings (see .gitattributes) for best cmd.exe compatibility.
chcp 65001 >nul

title Stock Recon - Install
cd /d "%~dp0"

rem Python UTF-8 output
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

python install.py
endlocal
pause
