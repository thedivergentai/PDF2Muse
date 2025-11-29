"""Utilities for working with oemer optical music recognition."""

import logging
import os
import sys
from pathlib import Path

import requests
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def get_checkpoint_dir() -> Path:
    """
    Get the directory where oemer checkpoints should be stored.

    Returns:
        Path to the checkpoints directory
    """
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


def download_checkpoints(force: bool = False) -> None:
    """
    Download oemer model checkpoints if they don't exist.

    Args:
        force: Force re-download even if checkpoints exist
    """
    base_url = "https://github.com/BreezeWhite/oemer/releases/download/checkpoints/"
    checkpoint_files = {
        "unet_big": {"model": "1st_model.onnx", "weights": "1st_weights.h5"},
        "seg_net": {"model": "2nd_model.onnx", "weights": "2nd_weights.h5"},
    }

    checkpoint_dir = get_checkpoint_dir()
    logger.info(f"Checkpoint directory: {checkpoint_dir}")

    for checkpoint_name, files in checkpoint_files.items():
        target_dir = checkpoint_dir / checkpoint_name
        target_dir.mkdir(parents=True, exist_ok=True)

        for file_type, filename in files.items():
            file_path = target_dir / filename

            if file_path.exists() and not force:
                logger.debug(f"{file_path} already exists, skipping download")
                continue

            url = base_url + filename
            console.print(f"[cyan]Downloading {filename}...[/cyan]")
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

                console.print(f"[green]✓[/green] Downloaded {filename}")
                logger.info(f"Saved to {file_path}")

            except requests.RequestException as e:
                logger.error(f"Failed to download {filename}: {e}")
                console.print(f"[red]✗[/red] Failed to download {filename}")
                raise

    console.print("[green]✓[/green] All checkpoints ready")


def ensure_checkpoints() -> None:
    """
    Ensure oemer checkpoints are available, downloading if necessary.
    """
    checkpoint_dir = get_checkpoint_dir()
    
    # Check if critical files exist
    critical_files = [
        checkpoint_dir / "unet_big" / "1st_model.onnx",
        checkpoint_dir / "seg_net" / "2nd_model.onnx",
    ]

    if all(f.exists() for f in critical_files):
        logger.debug("All checkpoints present")
        return

    logger.info("Checkpoints missing, downloading...")
    download_checkpoints()
