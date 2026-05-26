@echo off
setlocal enabledelayedexpansion

:: Enable ANSI support in Windows 10+ CMD
for /f "tokens=2 delims=[]" %%i in ('ver') do (
    for /f "tokens=2,3 delims=. " %%a in ("%%i") do (
        set "winver_major=%%a"
    )
)
if !winver_major! geq 10 (
    reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
)

:: ANSI Colors
set "ESC="
set "C_GREEN=!ESC![32m"
set "C_CYAN=!ESC![36m"
set "C_YELLOW=!ESC![33m"
set "C_RED=!ESC![31m"
set "C_MAGENTA=!ESC![35m"
set "C_RESET=!ESC![0m"
set "C_BOLD=!ESC![1m"

cls
echo !C_BOLD!!C_MAGENTA!===================================================!C_RESET!
echo !C_BOLD!!C_MAGENTA!  🎶  PDF2Muse - Interactive Onboarding Tool       !C_RESET!
echo !C_BOLD!!C_MAGENTA!===================================================!C_RESET!
echo.
echo Welcome! This interactive installer will guide you through setting up
echo PDF2Muse on your machine.
echo.

:: 1. Check Python installation
echo !C_CYAN![1/4] Checking Python requirements...!C_RESET!
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo !C_RED![ERROR] Python is not installed or not in your system PATH.!C_RESET!
    echo Please install Python 3.9 or higher and check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%i in ('python --version') do (
    for /f "tokens=1,2 delims=." %%a in ("%%i") do (
        set /a "major=%%a"
        set /a "minor=%%b"
    )
)
if !major! lss 3 (
    echo !C_RED![ERROR] Python 3.9 or higher is required. Found !major!.!minor!.!C_RESET!
    pause
    exit /b 1
)
if !major! equ 3 (
    if !minor! lss 9 (
        echo !C_RED![ERROR] Python 3.9 or higher is required. Found !major!.!minor!.!C_RESET!
        pause
        exit /b 1
    )
)
echo !C_GREEN![OK] Python !major!.!minor! detected.!C_RESET!
echo.

:: 2. Interactive Selection: Install Type
echo !C_CYAN![2/4] Choose your installation target:!C_RESET!
echo   [1] !C_BOLD!Interactive WebUI + CLI!C_RESET! (Default, recommended)
echo   [2] !C_BOLD!Lightweight CLI Only!C_RESET! (No Gradio web server)
echo.
set /p "UI_CHOICE=Select option [1]: "
if "!UI_CHOICE!"=="" set "UI_CHOICE=1"

:: 3. Interactive Selection: Developer mode
echo.
echo !C_CYAN![3/4] Choose your installation mode:!C_RESET!
echo   [1] !C_BOLD!Standard User Mode!C_RESET! (Default, installs running requirements)
echo   [2] !C_BOLD!Developer Mode!C_RESET! (Installs pytest, black, ruff testing suites)
echo.
set /p "DEV_CHOICE=Select option [1]: "
if "!DEV_CHOICE!"=="" set "DEV_CHOICE=1"

:: 4. Pre-download models
echo.
echo !C_CYAN![4/4] Deep learning OMR checkpoints:!C_RESET!
echo   Would you like to pre-download the OMR model checkpoints now?
echo   (Checks local cache and fetches if missing - around 400MB)
echo.
set /p "DOWNLOAD_CHOICE=Pre-download checkpoints? (Y/n) [Y]: "
if "!DOWNLOAD_CHOICE!"=="" set "DOWNLOAD_CHOICE=Y"

:: Setup variables
set "EXTRAS="
if "!UI_CHOICE!"=="1" (
    if "!DEV_CHOICE!"=="2" (
        set "EXTRAS=[ui,dev]"
    ) else (
        set "EXTRAS=[ui]"
    )
) else (
    if "!DEV_CHOICE!"=="2" (
        set "EXTRAS=[dev]"
    )
)

echo.
echo !C_MAGENTA!===================================================!C_RESET!
echo !C_BOLD!Starting installation with selected options...!C_RESET!
echo !C_MAGENTA!===================================================!C_RESET!
echo.

:: Create Virtual Environment if not exists
if not exist .venv (
    echo !C_YELLOW![INFO] Creating Python virtual environment in .venv...!C_RESET!
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo !C_RED![ERROR] Failed to create virtual environment.!C_RESET!
        pause
        exit /b 1
    )
) else (
    echo !C_GREEN![OK] Virtual environment .venv already exists.!C_RESET!
)

:: Activate virtual environment
echo !C_YELLOW![INFO] Activating virtual environment...!C_RESET!
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo !C_RED![ERROR] Failed to activate virtual environment.!C_RESET!
    pause
    exit /b 1
)

:: Upgrade pip
echo !C_YELLOW![INFO] Upgrading pip...!C_RESET!
python -m pip install --upgrade pip >nul 2>&1

:: Install package
echo !C_YELLOW![INFO] Installing PDF2Muse !EXTRAS!...!C_RESET!
pip install -e .!EXTRAS!
if %errorlevel% neq 0 (
    echo !C_RED![ERROR] Installation failed.!C_RESET!
    pause
    exit /b 1
)
echo !C_GREEN![OK] Dependencies installed successfully.!C_RESET!
echo.

:: Download models if requested
if /i "!DOWNLOAD_CHOICE!"=="Y" (
    echo !C_YELLOW![INFO] Running model checkpoints downloader...!C_RESET!
    python -m pdf2muse.cli download-models
)

echo.
echo !C_BOLD!!C_GREEN!===================================================!C_RESET!
echo !C_BOLD!!C_GREEN!🎉 PDF2Muse Onboarding Complete!!C_RESET!
echo !C_BOLD!!C_GREEN!===================================================!C_RESET!
if "!UI_CHOICE!"=="1" (
    echo To run the application:
    echo   !C_CYAN!run-ui.bat!C_RESET!
) else (
    echo To use the CLI:
    echo   !C_CYAN!pdf2muse convert [your_sheet.pdf]!C_RESET!
)
echo ===================================================
pause
