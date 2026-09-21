@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 'uv' is not installed. Run setup.bat first to check prerequisites.
    echo         Install uv from https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

uv run python app.py %*
