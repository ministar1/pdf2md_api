@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo MinerU PDF to Markdown
echo Project: %CD%
echo.

if not exist ".env" (
    echo .env not found. Please paste your MinerU token now.
    uv run python scripts\set_token.py
    if errorlevel 1 (
        echo.
        echo Token was not saved. Stop.
        pause
        exit /b 1
    )
    echo.
)

uv run python scripts\mineru_pdf2md.py

echo.
pause
