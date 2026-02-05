@echo off
chcp 65001 >nul
title Stock Recon - 一键启动
cd /d "%~dp0"
python start.py
pause
