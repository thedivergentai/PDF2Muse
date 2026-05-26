@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo PDF2Muse - Windows Installation Script
echo ===================================================

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.9 or higher and check "Add Python to PATH" during installation.
    exit /b 1
)

:: Verify Python version (3.9+)
for /f "tokens=2 delims= " %%i in ('python --version') do (
    for /f "tokens=1,2 delims=." %%a in ("%%i") do (
        set /a "major=%%a"
        set /a "minor=%%b"
    )
)
if !major! lss 3 (
    echo [ERROR] Python 3.9 or higher is required. Found version !major!.!minor!.
    exit /b 1
)
if !major! equ 3 (
    if !minor! lss 9 (
        echo [ERROR] Python 3.9 or higher is required. Found version !major!.!minor!.
        exit /b 1
    )
)

echo [OK] Python version !major!.!minor! detected.

:: Parse argument --dev
set INSTALL_DEV=0
if "%1"=="--dev" (
    set INSTALL_DEV=1
    echo [INFO] Running in Developer / Contributor mode.
)

:: Create Virtual Environment if not exists
if not exist .venv (
    echo [INFO] Creating Python virtual environment in .venv...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo [OK] Virtual environment .venv already exists.
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

:: Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

:: Install dependencies
if !INSTALL_DEV! equ 1 (
    echo [INFO] Installing package in editable mode with development extras...
    pip install -e .[ui,dev]
) else (
    echo [INFO] Installing package in editable mode with WebUI extras...
    pip install -e .[ui]
)
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    exit /b 1
)

:: Pre-download model checkpoints
echo [INFO] Pre-downloading oemer machine learning models...
python -m pdf2muse.cli download-models
if %errorlevel% neq 0 (
    echo [WARNING] Model pre-download encountered issues. They will try to auto-download during runtime.
)

echo ===================================================
echo Installation Successful!
echo ===================================================
echo To run the application:
echo   Run: run.bat
echo ===================================================
