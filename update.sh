#!/usr/bin/env bash
set -e

echo "==================================================="
echo "🔄 PDF2Muse - Update Script"
echo "==================================================="

# Pull latest code from Git
if command -v git &> /dev/null; then
    echo "[INFO] Pulling latest changes from Git repository..."
    git pull || echo "[WARNING] Git pull failed. Continuing update for local code..."
else
    echo "[WARNING] Git is not installed. Skipping git pull..."
fi

# Re-run installation
echo "[INFO] Re-running installation to update dependencies & checkpoints..."
bash install.sh

echo "==================================================="
echo "🎉 Update Complete!"
echo "==================================================="
