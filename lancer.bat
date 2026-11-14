@echo off
cd /d "%~dp0"
title LMU Dash
python server.py %*
pause
