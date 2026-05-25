@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if not exist ".env" (
    uv run python scripts\set_token.py --create-empty
)

echo Opening .env. Fill or replace MINERU_API_TOKEN, then save.
notepad ".env"
