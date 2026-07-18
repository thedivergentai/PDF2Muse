"""Load persisted Legato environment defaults from local setup."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

LEGATO_ENV_FILENAME = "legato.env.json"
ENV_KEYS = (
    "PDF2MUSE_LEGATO_REPO",
    "PDF2MUSE_LEGATO_PYTHON",
    "PDF2MUSE_LEGATO_MODEL",
)


def legato_env_path(repo_root: Optional[Path] = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "datasets" / "vendor" / LEGATO_ENV_FILENAME


def load_legato_env_defaults(repo_root: Optional[Path] = None) -> dict[str, str]:
    """Apply legato.env.json values when env vars are unset."""

    path = legato_env_path(repo_root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    applied: dict[str, str] = {}
    if not isinstance(data, dict):
        return applied
    for key in ENV_KEYS:
        value = data.get(key)
        if value and key not in os.environ:
            os.environ[key] = str(value)
            applied[key] = str(value)
    return applied


def write_legato_env_file(
    *,
    repo: Path,
    python: Path,
    model: str = "guangyangmusic/legato-small",
    repo_root: Optional[Path] = None,
) -> Path:
    path = legato_env_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "PDF2MUSE_LEGATO_REPO": str(repo.resolve()),
        "PDF2MUSE_LEGATO_PYTHON": str(python.resolve()),
        "PDF2MUSE_LEGATO_MODEL": model,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
