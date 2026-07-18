"""Legato VLM adapter (optional GPU backend)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from ..legato_env import load_legato_env_defaults
from ..musicxml import analyze_musicxml_structure, validate_musicxml_file
from .base import AdapterStatus, OmrOptions, PageResult

logger = logging.getLogger(__name__)

LEGATO_REPO_ENV = "PDF2MUSE_LEGATO_REPO"
LEGATO_MODEL_ENV = "PDF2MUSE_LEGATO_MODEL"
LEGATO_PYTHON_ENV = "PDF2MUSE_LEGATO_PYTHON"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONVERT_WRAPPER = _REPO_ROOT / "scripts" / "legato_convert_wrapper.py"

load_legato_env_defaults()


def _cuda_available() -> bool:
    try:
        import onnxruntime as ort

        return "CUDAExecutionProvider" in ort.get_available_providers()
    except ImportError:
        pass
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


def _legato_repo() -> Optional[Path]:
    repo = os.environ.get(LEGATO_REPO_ENV)
    if not repo:
        return None
    path = Path(repo).resolve()
    if (path / "scripts" / "inference.py").exists():
        return path
    return None


def _legato_python() -> str:
    return os.environ.get(LEGATO_PYTHON_ENV, sys.executable)


def _legato_model() -> str:
    return os.environ.get(LEGATO_MODEL_ENV, "guangyangmusic/legato-small")


def _hf_model_cached(model_id: str) -> bool:
    """Best-effort check whether a Hugging Face model snapshot is cached locally."""

    slug = f"models--{model_id.replace('/', '--')}"
    candidates = []
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        candidates.append(Path(hf_home) / "hub" / slug)
    candidates.append(Path.home() / ".cache" / "huggingface" / "hub" / slug)
    transformers_cache = os.environ.get("TRANSFORMERS_CACHE")
    if transformers_cache:
        candidates.append(Path(transformers_cache) / slug)
    for path in candidates:
        if path.exists() and any(path.rglob("config.json")):
            return True
    return False


def _abc_output_path(page_dir: Path, image_path: Path, model_path: str) -> Path:
    slug = model_path.replace("/", "_")
    return page_dir / f"{image_path.stem}_{slug}_abc.json"


class LegatoAdapter:
    """Optional Legato end-to-end OMR (ABC → MusicXML via PDF2Muse convert wrapper)."""

    name = "legato"

    def healthcheck(self) -> AdapterStatus:
        if not _cuda_available():
            return AdapterStatus(
                name=self.name,
                available=False,
                message="Legato requires a CUDA-capable GPU (not detected)",
                requires_gpu=True,
            )
        repo = _legato_repo()
        if repo is None:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=(
                    "Legato not configured. Run scripts/legato_setup.py or set "
                    "PDF2MUSE_LEGATO_REPO to a checkout with scripts/inference.py."
                ),
                requires_gpu=True,
            )
        for rel in ("scripts/inference.py", "utils/abc2xml.py"):
            if not (repo / rel).exists():
                return AdapterStatus(
                    name=self.name,
                    available=False,
                    message=f"Legato repo missing required file: {rel}",
                    requires_gpu=True,
                )
        if not _CONVERT_WRAPPER.exists():
            return AdapterStatus(
                name=self.name,
                available=False,
                message=f"Missing convert wrapper: {_CONVERT_WRAPPER}",
                requires_gpu=True,
            )
        python = _legato_python()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo)
        try:
            subprocess.run(
                [python, "-c", "from legato.models import LegatoModel"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return AdapterStatus(
                name=self.name,
                available=False,
                message=f"Legato Python env not ready ({python}): {exc}",
                requires_gpu=True,
            )
        model = _legato_model()
        message = f"Legato repo at {repo}; model={model}; python={python}"
        if not _hf_model_cached(model):
            message += (
                f"; WARNING: Hugging Face model '{model}' not found in local cache "
                "(first inference will download weights)"
            )
            logger.warning(message)
        return AdapterStatus(
            name=self.name,
            available=True,
            message=message,
            requires_gpu=True,
        )

    def _run_inference(
        self,
        image_path: Path,
        page_dir: Path,
        options: OmrOptions,
    ) -> Path:
        repo = _legato_repo()
        assert repo is not None
        model_path = _legato_model()
        abc_json = _abc_output_path(page_dir, image_path, model_path)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo)
        cmd = [
            _legato_python(),
            str(repo / "scripts" / "inference.py"),
            "--model_path",
            model_path,
            "--image_path",
            str(image_path),
            "--output_path",
            str(page_dir),
            "--device",
            "cuda" if _cuda_available() else "cpu",
            "--fp16",
        ]
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=options.timeout_seconds,
            cwd=str(repo),
            env=env,
        )
        if not abc_json.exists():
            candidates = list(page_dir.glob(f"{image_path.stem}_*_abc.json"))
            if not candidates:
                raise FileNotFoundError(f"Legato did not write ABC JSON under {page_dir}")
            abc_json = candidates[0]
        return abc_json

    def _abc_to_musicxml(self, abc_json: Path, musicxml_path: Path, page_dir: Path) -> None:
        payload = json.loads(abc_json.read_text(encoding="utf-8"))
        abc_text = ""
        if isinstance(payload.get("abc_transcription"), list) and payload["abc_transcription"]:
            abc_text = payload["abc_transcription"][0]
        elif isinstance(payload.get("abc_transcription"), str):
            abc_text = payload["abc_transcription"]
        if not abc_text.strip():
            raise ValueError("Legato ABC output was empty")

        single_abc = page_dir / f"{abc_json.stem}_single_abc.json"
        single_abc.write_text(
            json.dumps({"abc_transcription": [abc_text], "tokens": payload.get("tokens", [])}),
            encoding="utf-8",
        )

        if not _CONVERT_WRAPPER.exists():
            raise FileNotFoundError(f"Legato convert wrapper missing: {_CONVERT_WRAPPER}")

        env = os.environ.copy()
        subprocess.run(
            [
                sys.executable,
                str(_CONVERT_WRAPPER),
                "--input_file",
                str(single_abc),
                "--tmp_dir",
                str(page_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_REPO_ROOT),
            env=env,
        )
        xml_json_path = Path(str(single_abc).replace("_abc.json", "_xml.json"))
        if not xml_json_path.exists():
            raise FileNotFoundError(f"Legato convert did not write {xml_json_path}")
        xml_payload = json.loads(xml_json_path.read_text(encoding="utf-8"))
        if not xml_payload or not isinstance(xml_payload, list) or not xml_payload[0].strip():
            raise ValueError("Legato MusicXML conversion returned empty content")
        musicxml_path.write_text(xml_payload[0], encoding="utf-8")

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
                failure_class="legato_unavailable",
                backend=self.name,
            )

        page_dir = output_dir / image_path.stem
        page_dir.mkdir(parents=True, exist_ok=True)
        musicxml_path = output_dir / f"{image_path.stem}.musicxml"

        try:
            abc_json = self._run_inference(image_path, page_dir, options)
            self._abc_to_musicxml(abc_json, musicxml_path, page_dir)

            validation = validate_musicxml_file(musicxml_path)
            if not validation.ok:
                return PageResult(
                    error=f"Legato produced invalid MusicXML: {validation.error}",
                    failure_class="invalid_musicxml",
                    backend=self.name,
                )

            structure = analyze_musicxml_structure(musicxml_path)
            return PageResult(
                musicxml_path=musicxml_path,
                backend=self.name,
                attempts=[
                    {
                        "attempt": "legato",
                        "status": "succeeded",
                        "musicxml": str(musicxml_path),
                        "model": _legato_model(),
                        "structure": {
                            "parts": structure.parts,
                            "measures": structure.measures,
                            "notes": structure.notes,
                        },
                    }
                ],
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip() or str(exc)
            return PageResult(
                error=f"Legato failed on {image_path.name}: {stderr[:800]}",
                failure_class="legato_failed",
                backend=self.name,
            )
        except subprocess.TimeoutExpired:
            return PageResult(
                error=f"Legato timed out after {options.timeout_seconds}s on {image_path.name}",
                failure_class="timeout",
                backend=self.name,
            )
        except Exception as exc:
            return PageResult(
                error=f"Legato error on {image_path.name}: {exc}",
                failure_class="legato_failed",
                backend=self.name,
            )
