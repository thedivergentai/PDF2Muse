#!/usr/bin/env bash
set -e

echo "==================================================="
echo "🚀 PDF2Muse - WebUI Launcher"
echo "==================================================="

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "[WARNING] Virtual environment (.venv) not found."
    echo "Running installer first..."
    bash install.sh
fi

# Activate virtual environment
source .venv/bin/activate

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

# Check Poppler
if ! command -v pdftoppm &> /dev/null; then
    echo "[WARNING] 'pdftoppm' (Poppler) was not found in your system PATH."
    echo "If PDF to image conversion fails, please install Poppler via homebrew (brew install poppler) or apt (apt install poppler-utils)."
else
    echo "[OK] Poppler system utility detected."
fi

# Check MuseScore
if ! command -v MuseScore4 &> /dev/null && ! command -v MuseScore &> /dev/null && ! command -v mscore &> /dev/null; then
    echo "[WARNING] MuseScore was not found in your system PATH."
    echo "MuseScore is optional but recommended for native .mscx file export."
else
    echo "[OK] MuseScore detected in system PATH."
fi

echo "[INFO] Launching fully featured WebUI..."
python -m pdf2muse.cli ui
