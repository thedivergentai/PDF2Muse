"""Experimental HOMR adapter scaffold (AGPL-3.0 — non-default).

HOMR (https://github.com/liebharc/homr) targets multi-staff / grand-staff layouts
better than stock oemer for some lyric-between-staff cases. This adapter is
**experimental only**: do not select it as the product default without a
license decision. Enable via ``model_backend=homr-experimental`` after setting
``PDF2MUSE_HOMR_REPO`` (and optionally ``PDF2MUSE_HOMR_PYTHON``).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..musicxml import validate_musicxml_file
from .base import AdapterStatus, OmrOptions, PageResult

logger = logging.getLogger(__name__)

HOMR_REPO_ENV = "PDF2MUSE_HOMR_REPO"
HOMR_PYTHON_ENV = "PDF2MUSE_HOMR_PYTHON"


def _homr_repo() -> Optional[Path]:
    repo = os.environ.get(HOMR_REPO_ENV)
    if not repo:
        return None
    path = Path(repo).resolve()
    # Accept either a checkout with a CLI entry or an installed module marker.
    if (path / "homr").is_dir() or (path / "pyproject.toml").exists():
        return path
    return None


def _homr_python() -> str:
    return os.environ.get(HOMR_PYTHON_ENV, sys.executable)


class HomrAdapter:
    """Optional HOMR OMR backend (AGPL). Scaffold for NED bake-offs."""

    name = "homr"

    def healthcheck(self) -> AdapterStatus:
        repo = _homr_repo()
        if repo is None:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=(
                    "HOMR not configured. Set PDF2MUSE_HOMR_REPO to a local "
                    "liebharc/homr checkout. License: AGPL-3.0 (experimental only)."
                ),
                requires_gpu=False,
            )
        python = _homr_python()
        try:
            proc = subprocess.run(
                [python, "-c", "import homr"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo),
                env={**os.environ, "PYTHONPATH": str(repo)},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=f"HOMR Python env not ready ({python}): {exc}",
                requires_gpu=False,
            )
        if proc.returncode != 0:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=(
                    f"homr import failed in {repo}. Install the AGPL package in a "
                    f"dedicated env, then set PDF2MUSE_HOMR_PYTHON. stderr: "
                    f"{(proc.stderr or '')[:200]}"
                ),
                requires_gpu=False,
            )
        return AdapterStatus(
            name=self.name,
            available=True,
            message=(
                f"HOMR available at {repo} (AGPL-3.0 — experimental; "
                "not a product default)."
            ),
            requires_gpu=False,
        )

    def recognize_page(
        self,
        image_path: Path,
        output_dir: Path,
        options: OmrOptions,
    ) -> PageResult:
        status = self.healthcheck()
        if not status.available:
            return PageResult(
                error=status.message,
                failure_class="homr_unavailable",
                backend=self.name,
            )

        repo = _homr_repo()
        assert repo is not None
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_xml = output_dir / f"{image_path.stem}.musicxml"

        # Preferred: `python -m homr <image> -o <musicxml>` when the package exposes it.
        # Fallbacks try common CLI shapes; bake-offs skip when none work.
        candidates = [
            [
                _homr_python(),
                "-m",
                "homr",
                str(image_path),
                "-o",
                str(out_xml),
            ],
            [
                _homr_python(),
                "-m",
                "homr",
                "predict",
                str(image_path),
                "--output",
                str(out_xml),
            ],
        ]
        last_error = "HOMR CLI entry not found"
        env = {**os.environ, "PYTHONPATH": str(repo)}
        for cmd in candidates:
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=max(60, int(options.timeout_seconds)),
                    cwd=str(repo),
                    env=env,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                last_error = str(exc)
                continue
            if proc.returncode == 0 and out_xml.exists():
                validation = validate_musicxml_file(out_xml)
                if not validation.ok:
                    return PageResult(
                        musicxml_path=out_xml,
                        error=validation.error,
                        failure_class="invalid_musicxml",
                        backend=self.name,
                        metadata={"license": "AGPL-3.0", "experimental": True},
                    )
                return PageResult(
                    musicxml_path=out_xml,
                    backend=self.name,
                    metadata={"license": "AGPL-3.0", "experimental": True},
                )
            # Some CLIs write beside the image; copy if found.
            sibling = image_path.with_suffix(".musicxml")
            if sibling.exists():
                shutil.copy2(sibling, out_xml)
                return PageResult(
                    musicxml_path=out_xml,
                    backend=self.name,
                    metadata={"license": "AGPL-3.0", "experimental": True},
                )
            last_error = (proc.stderr or proc.stdout or f"exit {proc.returncode}")[:500]

        return PageResult(
            error=last_error,
            failure_class="homr_inference_failed",
            backend=self.name,
            metadata={"license": "AGPL-3.0", "experimental": True},
        )
