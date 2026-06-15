#!/usr/bin/env bash
set -e

echo "==================================================="
echo "PDF2Muse - WebUI Launcher"
echo "==================================================="

# Activate project virtual environment (prefer venv/, fall back to .venv/)
VENV_DIR=""
if [ -f "venv/bin/activate" ]; then
    VENV_DIR="venv"
elif [ -f ".venv/bin/activate" ]; then
    VENV_DIR=".venv"
fi

if [ -z "$VENV_DIR" ]; then
    echo "[WARNING] Virtual environment not found (expected venv/ or .venv/)."
    echo "Running installer first..."
    bash install.sh
    if [ -f "venv/bin/activate" ]; then
        VENV_DIR="venv"
    elif [ -f ".venv/bin/activate" ]; then
        VENV_DIR=".venv"
    fi
fi

if [ -z "$VENV_DIR" ]; then
    echo "[ERROR] Virtual environment activation script not found. Please re-run install.sh."
    exit 1
fi

source "${VENV_DIR}/bin/activate"

# Check if Gradio is installed (as this launcher runs the WebUI)
if ! python3 -c "import gradio" &> /dev/null; then
    echo "==================================================="
    echo "[ERROR] Gradio WebUI component was not found in this environment."
    echo "Please install WebUI dependencies by running:"
    echo "  ./install.sh"
    echo "and try again."
    echo "==================================================="
    exit 1
fi

# Pre-flight Diagnostics
echo "[INFO] Performing system environment diagnostics..."

# Check MuseScore
if ! command -v MuseScore4 &> /dev/null && ! command -v MuseScore &> /dev/null && ! command -v mscore &> /dev/null; then
    echo "[WARNING] MuseScore was not found in your system PATH."
    echo "MuseScore is optional but recommended for native .mscx file export."
else
    echo "[OK] MuseScore detected in system PATH."
fi

echo "[INFO] Launching fully featured WebUI..."
python -m pdf2muse.cli ui
