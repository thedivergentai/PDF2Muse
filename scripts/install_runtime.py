#!/usr/bin/env python3
"""Repo-root entry for platform-aware PDF2Muse installs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "pdf2muse" / "install_runtime.py"

# Load the helper by path so this script does not import pdf2muse/__init__.py.
# That package init pulls in runtime dependencies this installer is about to install.
spec = importlib.util.spec_from_file_location("pdf2muse_install_runtime", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load installer module: {MODULE_PATH}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

if __name__ == "__main__":
    raise SystemExit(module.main())
