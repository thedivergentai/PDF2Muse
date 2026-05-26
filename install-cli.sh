#!/usr/bin/env bash
set -e

echo "==================================================="
echo "🎶 PDF2Muse - Linux & macOS Installation (CLI Only)"
echo "==================================================="

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed or not in your system PATH."
    echo "Please install Python 3.9 or higher using your package manager (brew or apt)."
    exit 1
fi

# Verify Python version (3.9+)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]; }; then
    echo "[ERROR] Python 3.9 or higher is required. Found version $PYTHON_VERSION."
    exit 1
fi

echo "[OK] Python version $PYTHON_VERSION detected."

# Parse argument --dev
INSTALL_DEV=0
if [ "$1" == "--dev" ]; then
    INSTALL_DEV=1
    echo "[INFO] Running in Developer / Contributor mode."
fi

# Create Virtual Environment if not exists
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating Python virtual environment in .venv..."
    python3 -m venv .venv
else
    echo "[OK] Virtual environment .venv already exists."
fi

# Activate virtual environment
echo "[INFO] Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "[INFO] Upgrading pip..."
python3 -m pip install --upgrade pip > /dev/null 2>&1

# Install dependencies (CLI only)
if [ "$INSTALL_DEV" -eq 1 ]; then
    echo "[INFO] Installing package in editable mode with development extras..."
    pip install -e .[dev]
else
    echo "[INFO] Installing package in editable mode (CLI-only)..."
    pip install -e .
fi

# Pre-download model checkpoints
echo "[INFO] Pre-downloading oemer machine learning models..."
python3 -m pdf2muse.cli download-models || echo "[WARNING] Model pre-download failed. They will try to auto-download during runtime."

echo "==================================================="
echo "🎉 Installation Successful!"
echo "==================================================="
echo "To run the CLI:"
echo "  Run: pdf2muse convert [options]"
echo "==================================================="
