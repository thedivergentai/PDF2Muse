@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo PDF2Muse - WebUI Launcher
echo ===================================================

:: Activate project virtual environment (prefer venv/, fall back to .venv/)
set "VENV_DIR="
if exist venv\Scripts\activate.bat set "VENV_DIR=venv"
if not defined VENV_DIR if exist .venv\Scripts\activate.bat set "VENV_DIR=.venv"

if not defined VENV_DIR (
    echo [WARNING] Virtual environment not found ^(expected venv\ or .venv\^).
    echo Running installer first...
    call install.bat
    if exist venv\Scripts\activate.bat set "VENV_DIR=venv"
    if not defined VENV_DIR if exist .venv\Scripts\activate.bat set "VENV_DIR=.venv"
)

if not defined VENV_DIR (
    echo [ERROR] Virtual environment activation script not found. Please re-run install.bat.
    exit /b 1
)

call %VENV_DIR%\Scripts\activate.bat

:: Check if Gradio is installed (as this launcher runs the WebUI)
python -c "import gradio" >nul 2>&1
if %errorlevel% neq 0 (
    echo ===================================================
    echo [ERROR] Gradio WebUI component was not found in this environment.
    echo Please install WebUI dependencies by running:
    echo   install.bat
    echo and try again.
    echo ===================================================
    exit /b 1
)

:: Pre-flight Diagnostics
echo [INFO] Performing system environment diagnostics...

:: Check MuseScore
where MuseScore4 >nul 2>&1
if %errorlevel% neq 0 (
    where MuseScore >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARNING] MuseScore was not found in your system PATH.
        echo MuseScore is optional but recommended for native .mscx file export.
    ) else (
        echo [OK] MuseScore detected in system PATH.
    )
) else (
    echo [OK] MuseScore 4 detected in system PATH.
)

echo [INFO] Launching fully featured WebUI...
python -m pdf2muse.cli ui
if %errorlevel% neq 0 (
    echo ===================================================
    echo [ERROR] PDF2Muse WebUI closed with error code %errorlevel%.
    echo Please check the error trace above or contact support.
    echo ===================================================
    exit /b 1
)

echo [INFO] PDF2Muse WebUI closed gracefully.
