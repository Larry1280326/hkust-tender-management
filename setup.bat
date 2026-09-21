@echo off
setlocal
cd /d "%~dp0"

set PASS=0
set FAIL=0
set WARN=0

echo.
echo  ==================================================
echo   HKUST e-Tendering Automation - Setup Check
echo  ==================================================
echo.

rem ---- 1) Python 3.11+ ----
where python >nul 2>&1
if errorlevel 1 goto py_missing
python -c "import sys; sys.exit(sys.version_info < (3,11))" >nul 2>&1
if errorlevel 1 goto py_old
echo  [OK]  Python 3.11+ found
set /a PASS+=1
goto uv_check
:py_missing
echo  [FAIL] Python not found on PATH - install Python 3.11+
echo         https://www.python.org/downloads/
set /a FAIL+=1
goto uv_check
:py_old
echo  [FAIL] Python 3.11+ required - found an older version
echo         https://www.python.org/downloads/
set /a FAIL+=1

:uv_check
rem ---- 2) uv ----
uv --version >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] 'uv' not found - install it
    echo         https://docs.astral.sh/uv/getting-started/installation/
    set /a FAIL+=1
) else (
    echo  [OK]  uv found
    set /a PASS+=1
)

rem ---- 3) Playwright Chromium ----
set "MS_PW=%LOCALAPPDATA%\ms-playwright"
if not defined LOCALAPPDATA set "MS_PW=%USERPROFILE%\AppData\Local\ms-playwright"
if exist "%MS_PW%\chromium-*" (
    echo  [OK]  Playwright Chromium found
    set /a PASS+=1
) else (
    echo  [FAIL] Playwright Chromium not found - run: uv run playwright install chromium
    set /a FAIL+=1
)

rem ---- 4) .env file ----
if exist ".env" (
    echo  [OK]  .env file found
    set /a PASS+=1
) else (
    echo  [FAIL] .env missing - copy .env.example to .env and fill in the values
    set /a FAIL+=1
    goto summary
)

rem ---- 5-7) .env variables ----
call :check_env "HKUST_VENDOR_ID" HARD
call :check_env "HKUST_PASSWORD" HARD
call :check_env "GMAIL_APP_PASSWORD" WARN

rem ---- 8) BR certificate ----
set "BR_PATH=assets\br_certificate.pdf"
for /f "usebackq tokens=2 delims==" %%A in (`findstr /B /C:"BR_CERTIFICATE_PATH=" .env`) do set "BR_PATH=%%A"
if exist "%BR_PATH%" (
    echo  [OK]  BR certificate found: %BR_PATH%
    set /a PASS+=1
) else (
    echo  [WARN] BR certificate not found at "%BR_PATH%" - attachment will be skipped
    set /a WARN+=1
)

goto summary

:check_env
rem  %~1 = variable name, %~2 = HARD or WARN
set "val="
for /f "usebackq tokens=2 delims==" %%A in (`findstr /B /C:"%~1=" .env`) do set "val=%%A"
if defined val (
    echo  [OK]  %~1 is set
    set /a PASS+=1
) else (
    if /I "%~2"=="WARN" (
        echo  [WARN] %~1 is not set
        set /a WARN+=1
    ) else (
        echo  [FAIL] %~1 is not set in .env
        set /a FAIL+=1
    )
)
exit /b 0

:summary
echo.
echo  --------------------------------------------------
echo   Summary: %PASS% passed, %FAIL% failed, %WARN% warnings
echo  --------------------------------------------------
if %FAIL% GTR 0 (
    echo   Fix the FAIL items above, then re-run this script.
    exit /b 1
)
echo   All required checks passed.
exit /b 0
