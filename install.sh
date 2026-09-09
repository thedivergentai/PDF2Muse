#!/usr/bin/env bash
set -e

# ANSI Colors
C_GREEN="\033[32m"
C_CYAN="\033[36m"
C_YELLOW="\033[33m"
C_RED="\033[31m"
C_MAGENTA="\033[35m"
C_RESET="\033[0m"
C_BOLD="\033[1m"

clear
echo -e "${C_BOLD}${C_MAGENTA}===================================================${C_RESET}"
echo -e "${C_BOLD}${C_MAGENTA}  🎶  PDF2Muse - Interactive Onboarding Tool       ${C_RESET}"
echo -e "${C_BOLD}${C_MAGENTA}===================================================${C_RESET}"
echo -e ""
echo -e "Welcome! This interactive installer will guide you through setting up"
echo -e "PDF2Muse on your machine."
echo -e ""

# 1. Check Python installation
echo -e "${C_CYAN}[1/4] Checking Python requirements...${C_RESET}"
if ! command -v python3 &> /dev/null; then
    echo -e "${C_RED}[ERROR] python3 is not installed or not in your system PATH.${C_RESET}"
    echo -e "Please install Python 3.9 or higher using your package manager."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ]; then
    echo -e "${C_RED}[ERROR] Python 3.9 or higher is required. Found version $PYTHON_VERSION.${C_RESET}"
    exit 1
fi
if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]; then
    echo -e "${C_RED}[ERROR] Python 3.9 or higher is required. Found version $PYTHON_VERSION.${C_RESET}"
    exit 1
fi
echo -e "${C_GREEN}[OK] Python $PYTHON_VERSION detected.${C_RESET}"
echo -e ""

# 2. Interactive Selection: Install Type
echo -e "${C_CYAN}[2/4] Choose your installation target:${C_RESET}"
echo -e "  [1] ${C_BOLD}Interactive WebUI + CLI${C_RESET} (Default, recommended)"
echo -e "  [2] ${C_BOLD}Lightweight CLI Only${C_RESET} (No Gradio web server)"
echo -e ""
read -p "Select option [1]: " UI_CHOICE
if [ -z "$UI_CHOICE" ]; then
    UI_CHOICE=1
fi

# 3. Interactive Selection: Developer mode
echo -e ""
echo -e "${C_CYAN}[3/4] Choose your installation mode:${C_RESET}"
echo -e "  [1] ${C_BOLD}Standard User Mode${C_RESET} (Default, installs running requirements)"
echo -e "  [2] ${C_BOLD}Developer Mode${C_RESET} (Installs pytest, black, ruff testing suites)"
echo -e ""
read -p "Select option [1]: " DEV_CHOICE
if [ -z "$DEV_CHOICE" ]; then
    DEV_CHOICE=1
fi

# 4. Pre-download models
echo -e ""
echo -e "${C_CYAN}[4/4] Deep learning OMR checkpoints:${C_RESET}"
echo -e "  Would you like to pre-download the OMR model checkpoints now?"
echo -e "  (Checks local cache and fetches if missing - around 400MB)"
echo -e ""
read -p "Pre-download checkpoints? (Y/n) [Y]: " DOWNLOAD_CHOICE
if [ -z "$DOWNLOAD_CHOICE" ]; then
    DOWNLOAD_CHOICE="Y"
fi

# Setup variables
EXTRAS=""
if [ "$UI_CHOICE" -eq 1 ]; then
    if [ "$DEV_CHOICE" -eq 2 ]; then
        EXTRAS="[ui,dev]"
    else
        EXTRAS="[ui]"
    fi
else
    if [ "$DEV_CHOICE" -eq 2 ]; then
        EXTRAS="[dev]"
    fi
fi

echo -e ""
echo -e "${C_MAGENTA}===================================================${C_RESET}"
echo -e "${C_BOLD}Starting installation with selected options...${C_RESET}"
echo -e "${C_MAGENTA}===================================================${C_RESET}"
echo -e ""

# Create Virtual Environment if not exists (prefer venv/, fall back to .venv/)
VENV_DIR=""
if [ -f "venv/bin/activate" ]; then
    VENV_DIR="venv"
elif [ -f ".venv/bin/activate" ]; then
    VENV_DIR=".venv"
else
    echo -e "${C_YELLOW}[INFO] Creating Python virtual environment in venv...${C_RESET}"
    python3 -m venv venv
    VENV_DIR="venv"
fi

if [ -z "$VENV_DIR" ]; then
    echo -e "${C_RED}[ERROR] Could not locate or create a virtual environment.${C_RESET}"
    exit 1
fi

VENV_PATH="$(cd "$VENV_DIR" && pwd)"
echo -e "${C_GREEN}[OK] Using virtual environment ${VENV_DIR}.${C_RESET}"
echo -e "${C_GREEN}[OK] Virtual environment path: ${VENV_PATH}${C_RESET}"

# Activate virtual environment
echo -e "${C_YELLOW}[INFO] Activating virtual environment...${C_RESET}"
source "${VENV_DIR}/bin/activate"

# Upgrade pip
echo -e "${C_YELLOW}[INFO] Upgrading pip...${C_RESET}"
python3 -m pip install --upgrade pip > /dev/null 2>&1

# Install package (oemer --no-deps + platform ONNX Runtime; Mac cannot use onnxruntime-gpu)
echo -e "${C_YELLOW}[INFO] Installing PDF2Muse ${EXTRAS} with platform ONNX Runtime...${C_RESET}"
EXTRAS_CSV="${EXTRAS#[}"
EXTRAS_CSV="${EXTRAS_CSV%]}"
python3 scripts/install_runtime.py --extras "${EXTRAS_CSV}" --no-download
echo -e "${C_GREEN}[OK] Dependencies installed successfully.${C_RESET}"
echo -e ""

# Download models if requested
if [ "$DOWNLOAD_CHOICE" == "Y" ] || [ "$DOWNLOAD_CHOICE" == "y" ]; then
    echo -e "${C_YELLOW}[INFO] Running model checkpoints downloader...${C_RESET}"
    python3 -m pdf2muse.cli download-models
fi

echo -e ""
echo -e "${C_BOLD}${C_GREEN}===================================================${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}🎉 PDF2Muse Onboarding Complete!${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}===================================================${C_RESET}"
echo -e "Virtual environment:"
echo -e "  ${C_CYAN}${VENV_PATH}${C_RESET}"
echo -e ""
echo -e "To activate it manually:"
echo -e "  ${C_CYAN}source ${VENV_DIR}/bin/activate${C_RESET}"
echo -e "To leave the environment later:"
echo -e "  ${C_CYAN}deactivate${C_RESET}"
echo -e "To run the CLI without activating:"
echo -e "  ${C_CYAN}${VENV_DIR}/bin/python -m pdf2muse.cli convert [your_sheet.pdf]${C_RESET}"
echo -e ""
if [ "$UI_CHOICE" -eq 1 ]; then
    echo -e "To run the application:"
    echo -e "  ${C_CYAN}./run-ui.sh${C_RESET}"
else
    echo -e "To use the CLI:"
    echo -e "  ${C_CYAN}pdf2muse convert [your_sheet.pdf]${C_RESET}"
fi
echo -e "==================================================="
