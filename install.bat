@echo off
chcp 65001 >nul
title Stock Recon - 一键安装依赖
cd /d "%~dp0"
python install.py
pause
