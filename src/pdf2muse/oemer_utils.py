"""Utilities for working with oemer optical music recognition."""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import requests
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()
OEMER_CHECKPOINT_ENV = "PDF2MUSE_OEMER_CHECKPOINT_DIR"


def cuda_ep_available() -> bool:
    """Return True when onnxruntime exposes CUDAExecutionProvider."""

    try:
        import onnxruntime as ort

        return "CUDAExecutionProvider" in ort.get_available_providers()
    except ImportError:
        return False


def resolve_oemer_device(device: str = "auto") -> str:
    """Resolve oemer device: auto → cuda when CUDA EP exists, else cpu."""

    normalized = (device or "auto").strip().lower()
    if normalized in {"cpu", "cuda"}:
        return normalized
    if normalized == "auto":
        return "cuda" if cuda_ep_available() else "cpu"
    raise ValueError("oemer_device must be 'auto', 'cpu', or 'cuda'")


@dataclass(frozen=True)
class ModelBackendConfig:
    """Configuration for one OMR backend experiment."""

    name: str
    kind: str
    description: str
    checkpoint_dir: Optional[Path] = None
    experimental: bool = False


def get_checkpoint_dir(checkpoint_dir: Optional[Union[Path, str]] = None) -> Path:
    """
    Get the directory where oemer checkpoints should be stored.

    Returns:
        Path to the checkpoints directory
    """
    if checkpoint_dir:
        return Path(checkpoint_dir).resolve()

    env_checkpoint_dir = os.environ.get(OEMER_CHECKPOINT_ENV)
    if env_checkpoint_dir:
        return Path(env_checkpoint_dir).resolve()

    try:
        import oemer
        oemer_path = Path(oemer.__file__).parent
        return oemer_path / "checkpoints"
    except ImportError:
        # Fallback to site-packages location
        if hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        ):
            # We're in a virtual environment
            site_packages = Path(sys.prefix) / "lib" / "site-packages"
        else:
            # System Python
            import site
            site_packages = Path(site.getsitepackages()[0])

        return site_packages / "oemer" / "checkpoints"


def download_checkpoints(
    force: bool = False,
    checkpoint_dir: Optional[Union[Path, str]] = None,
) -> None:
    """
    Download oemer model checkpoints if they don't exist.

    Args:
        force: Force re-download even if checkpoints exist
    """
    base_url = "https://github.com/BreezeWhite/oemer/releases/download/checkpoints/"
    checkpoint_files = {
        "unet_big": {
            "model": {"src": "1st_model.onnx", "dst": "model.onnx"},
            "weights": {"src": "1st_weights.h5", "dst": "weights.h5"},
        },
        "seg_net": {
            "model": {"src": "2nd_model.onnx", "dst": "model.onnx"},
            "weights": {"src": "2nd_weights.h5", "dst": "weights.h5"},
        },
    }

    checkpoint_dir = get_checkpoint_dir(checkpoint_dir)
    logger.info(f"Checkpoint directory: {checkpoint_dir}")

    for checkpoint_name, files in checkpoint_files.items():
        target_dir = checkpoint_dir / checkpoint_name
        target_dir.mkdir(parents=True, exist_ok=True)

        for file_type, file_info in files.items():
            src_filename = file_info["src"]
            dst_filename = file_info["dst"]
            file_path = target_dir / dst_filename

            if file_path.exists() and not force:
                logger.debug(f"{file_path} already exists, skipping download")
                continue

            url = base_url + src_filename
            console.print(f"[cyan]Downloading {src_filename} as {dst_filename}...[/cyan]")
            logger.info(f"Downloading from {url}")

            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()

                # Download with progress
                total_size = int(response.headers.get("content-length", 0))
                
                with open(file_path, "wb") as f:
                    if total_size == 0:
                        f.write(response.content)
                    else:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)

                console.print(f"[green][OK][/green] Downloaded and saved {dst_filename}")
                logger.info(f"Saved to {file_path}")

            except requests.RequestException as e:
                logger.error(f"Failed to download {src_filename}: {e}")
                console.print(f"[red][FAIL][/red] Failed to download {src_filename}")
                raise

    console.print("[green][OK][/green] All checkpoints ready")


def ensure_checkpoints(
    checkpoint_dir: Optional[Union[Path, str]] = None,
    *,
    download_missing: bool = True,
) -> None:
    """
    Ensure oemer checkpoints are available, downloading if necessary.
    """
    checkpoint_dir = get_checkpoint_dir(checkpoint_dir)
    
    # Check if critical files exist with their correct internal names
    critical_files = [
        checkpoint_dir / "unet_big" / "model.onnx",
        checkpoint_dir / "unet_big" / "weights.h5",
        checkpoint_dir / "seg_net" / "model.onnx",
        checkpoint_dir / "seg_net" / "weights.h5",
    ]

    if all(f.exists() for f in critical_files):
        logger.debug("All checkpoints present")
        return

    if not download_missing:
        missing = ", ".join(str(path) for path in critical_files if not path.exists())
        raise FileNotFoundError(f"Custom checkpoint directory is incomplete: {missing}")

    logger.info("Checkpoints missing, downloading...")
    download_checkpoints(checkpoint_dir=checkpoint_dir)


def list_model_backend_configs() -> list[ModelBackendConfig]:
    """Return the supported OMR backend experiment slots."""

    return [
        ModelBackendConfig(
            name="oemer-stock",
            kind="oemer",
            description="Stock oemer checkpoints installed with or downloaded for the package.",
            checkpoint_dir=None,
            experimental=False,
        ),
        ModelBackendConfig(
            name="oemer-custom",
            kind="oemer",
            description=(
                "Custom oemer-compatible checkpoints in a separate directory; useful for "
                "fine-tuning experiments without overwriting package checkpoints."
            ),
            experimental=True,
        ),
        ModelBackendConfig(
            name="legato-experimental",
            kind="adapter",
            description=(
                "Legato VLM end-to-end OMR (GPU). Run scripts/legato_setup.py or set "
                "PDF2MUSE_LEGATO_REPO / PDF2MUSE_LEGATO_PYTHON / PDF2MUSE_LEGATO_MODEL."
            ),
            experimental=True,
        ),
        ModelBackendConfig(
            name="homr",
            kind="homr",
            description=(
                "Optional HOMR end-to-end OMR (AGPL-3.0). Install with "
                "pip install 'pdf2muse[homr]' (requires Python >= 3.11), then "
                "pdf2muse convert score.pdf --model-backend homr. "
                "Set PDF2MUSE_ALLOW_HOMR_AUTO=1 to select HOMR under --model-backend auto."
            ),
            experimental=False,
        ),
    ]


def get_model_backend_config(
    name: str = "oemer-stock",
    *,
    checkpoint_dir: Optional[Union[Path, str]] = None,
) -> ModelBackendConfig:
    """Return a backend config, applying checkpoint overrides for custom oemer runs."""

    configs = {config.name: config for config in list_model_backend_configs()}
    if name not in configs:
        expected = ", ".join(sorted(configs))
        raise ValueError(f"Unknown model backend: {name}. Expected one of: {expected}.")

    config = configs[name]
    if name == "oemer-custom":
        return ModelBackendConfig(
            name=config.name,
            kind=config.kind,
            description=config.description,
            checkpoint_dir=get_checkpoint_dir(checkpoint_dir) if checkpoint_dir else None,
            experimental=config.experimental,
        )
    if checkpoint_dir and name == "oemer-stock":
        return get_model_backend_config("oemer-custom", checkpoint_dir=checkpoint_dir)
    return config
