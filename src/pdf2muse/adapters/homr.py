"""HOMR adapter (optional AGPL OMR backend).

``model_backend=homr`` uses the optional ``pdf2muse[homr]`` install and
``scripts/homr_convert_wrapper.py``. When ``PDF2MUSE_HOMR_REPO`` points at a
local liebharc/homr checkout, recognition uses that checkout instead
(``model_backend=homr-experimental``). HOMR is AGPL-3.0. ``auto`` selects the
pip backend only when ``PDF2MUSE_ALLOW_HOMR_AUTO=1``; ``homr-experimental`` is
never auto-selected.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..musicxml import analyze_musicxml_structure, validate_musicxml_file
from .base import AdapterStatus, OmrOptions, PageResult

HOMR_REPO_ENV = "PDF2MUSE_HOMR_REPO"
HOMR_PYTHON_ENV = "PDF2MUSE_HOMR_PYTHON"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONVERT_WRAPPER = _REPO_ROOT / "scripts" / "homr_convert_wrapper.py"


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


def _python_version_ok(python: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [
                python,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"Cannot probe Python interpreter {python}: {exc}"
    version = (completed.stdout or "").strip()
    try:
        major_s, minor_s = version.split(".", 1)
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        return False, f"Unexpected Python version output: {version!r}"
    if (major, minor) < (3, 11):
        return (
            False,
            f"HOMR requires Python >= 3.11 (found {version} via {python})",
        )
    return True, version


def _homr_importable(python: str) -> tuple[bool, str]:
    try:
        subprocess.run(
            [python, "-c", "import homr"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out importing homr with {python}"
    except FileNotFoundError:
        return False, f"Python interpreter not found: {python}"
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip() or str(exc)
        return (
            False,
            (
                "HOMR not installed. Install with: pip install 'pdf2muse[homr]' "
                f"(AGPL-3.0, Python >= 3.11). Or set {HOMR_REPO_ENV} to a local "
                "liebharc/homr checkout. "
                f"Detail: {stderr[:400]}"
            ),
        )
    return True, "homr importable"


class HomrAdapter:
    """Optional HOMR end-to-end OMR backend (image → MusicXML)."""

    name = "homr"

    def healthcheck(self) -> AdapterStatus:
        repo = _homr_repo()
        if repo is not None:
            return self._healthcheck_repo(repo)
        return self._healthcheck_package()

    def _healthcheck_repo(self, repo: Path) -> AdapterStatus:
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
                    f"dedicated env, then set {HOMR_PYTHON_ENV}. stderr: "
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

    def _healthcheck_package(self) -> AdapterStatus:
        if not _CONVERT_WRAPPER.exists():
            return AdapterStatus(
                name=self.name,
                available=False,
                message=(
                    f"Missing HOMR convert wrapper: {_CONVERT_WRAPPER}. "
                    f"Or set {HOMR_REPO_ENV} to a local liebharc/homr checkout."
                ),
                requires_gpu=False,
            )
        python = _homr_python()
        ok, detail = _python_version_ok(python)
        if not ok:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=detail,
                requires_gpu=False,
            )
        ok, import_detail = _homr_importable(python)
        if not ok:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=import_detail,
                requires_gpu=False,
            )
        return AdapterStatus(
            name=self.name,
            available=True,
            message=f"HOMR ready (python={python}, version={detail})",
            requires_gpu=False,
        )

    def _device_flag(self, options: OmrOptions) -> str:
        device = (options.device or "auto").lower()
        if device in {"auto", "cpu", "cuda"}:
            return device
        return "auto"

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
        if _homr_repo() is not None:
            return self._recognize_via_repo(image_path, output_dir, options)
        return self._recognize_via_wrapper(image_path, output_dir, options)

    def _recognize_via_wrapper(
        self,
        image_path: Path,
        output_dir: Path,
        options: OmrOptions,
    ) -> PageResult:
        image_path = Path(image_path)
        output_dir = Path(output_dir)
        page_dir = output_dir / image_path.stem
        page_dir.mkdir(parents=True, exist_ok=True)
        work_image = page_dir / image_path.name
        if image_path.resolve() != work_image.resolve():
            shutil.copy2(image_path, work_image)

        musicxml_path = output_dir / f"{image_path.stem}.musicxml"
        python = _homr_python()
        cmd = [
            python,
            str(_CONVERT_WRAPPER),
            str(work_image),
            "--device",
            self._device_flag(options),
        ]
        if options.save_cache:
            cmd.append("--cache")
        try:
            completed = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=options.timeout_seconds,
                cwd=str(_REPO_ROOT),
            )
            produced = page_dir / f"{work_image.stem}.musicxml"
            # HOMR writes next to the image; also accept stdout path if present.
            stdout_path = (completed.stdout or "").strip().splitlines()
            if stdout_path:
                candidate = Path(stdout_path[-1].strip())
                if candidate.exists():
                    produced = candidate
            if not produced.exists():
                return PageResult(
                    error=f"HOMR did not write MusicXML beside {work_image}",
                    failure_class="homr_failed",
                    backend=self.name,
                    attempts=[
                        {
                            "attempt": "homr",
                            "status": "failed",
                            "stderr": (completed.stderr or "")[:800],
                        }
                    ],
                )
            if produced.resolve() != musicxml_path.resolve():
                shutil.copy2(produced, musicxml_path)

            validation = validate_musicxml_file(musicxml_path)
            if not validation.ok:
                return PageResult(
                    error=f"HOMR produced invalid MusicXML: {validation.error}",
                    failure_class="invalid_musicxml",
                    backend=self.name,
                )

            structure = analyze_musicxml_structure(musicxml_path)
            return PageResult(
                musicxml_path=musicxml_path,
                backend=self.name,
                attempts=[
                    {
                        "attempt": "homr",
                        "status": "succeeded",
                        "musicxml": str(musicxml_path),
                        "title_detection": True,
                        "device": self._device_flag(options),
                        "structure": {
                            "parts": structure.parts,
                            "measures": structure.measures,
                            "notes": structure.notes,
                        },
                    }
                ],
            )
        except subprocess.TimeoutExpired:
            return PageResult(
                error=f"HOMR timed out after {options.timeout_seconds}s on {image_path.name}",
                failure_class="timeout",
                backend=self.name,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip() or str(exc)
            return PageResult(
                error=f"HOMR failed on {image_path.name}: {stderr[:800]}",
                failure_class="homr_failed",
                backend=self.name,
            )
        except Exception as exc:
            return PageResult(
                error=f"HOMR error on {image_path.name}: {exc}",
                failure_class="homr_failed",
                backend=self.name,
            )

    def _recognize_via_repo(
        self,
        image_path: Path,
        output_dir: Path,
        options: OmrOptions,
    ) -> PageResult:
        repo = _homr_repo()
        assert repo is not None
        image_path = Path(image_path)
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
