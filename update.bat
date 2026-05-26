@echo off
echo ===================================================
echo PDF2Muse - Update Script
echo ===================================================

:: Pull latest code from Git
git --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Pulling latest changes from Git repository...
    git pull
    if %errorlevel% neq 0 (
        echo [WARNING] Git pull failed. Continuing update for local code...
    )
) else (
    echo [WARNING] Git is not installed or repository is detached. Skipping git pull...
)

:: Re-run installation
echo [INFO] Re-running installation to update dependencies and checkpoints...
call install.bat

echo ===================================================
echo Update Complete!
echo ===================================================
