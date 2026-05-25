@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

uv run python scripts\set_token.py

echo.
pause

