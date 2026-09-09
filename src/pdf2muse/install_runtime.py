"""Platform-aware source install helpers.

oemer wheels published from Linux declare ``onnxruntime-gpu`` in METADATA even
though oemer's setup.py would have chosen CPU ``onnxruntime`` on Darwin. Mac
users then fail at pip resolve. Install oemer with ``--no-deps`` and pin the
ONNX Runtime wheel ourselves.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Iterable, Sequence

PDF2MUSE_CORE_DEPS = [
    "pypdfium2>=4.0.0",
    "typer>=0.9.0",
    "rich>=13.0.0",
    "Pillow>=10.0.0",
    "requests>=2.0.0",
    "music21>=9.1.0",
    "pydantic-settings>=2.0.0",
]

OEMER_THIRD_PARTY_DEPS = [
    "opencv-python-headless>=4.5.3.56",
    "matplotlib",
    "scipy",
    "scikit-learn>=1.2",
    "types-Pillow",
    "types-tensorflow",
    "typing-extensions",
]

EXTRA_DEPS = {
    "ui": ["gradio>=4.0.0"],
    "api": ["fastapi>=0.110.0", "uvicorn[standard]>=0.27.0"],
    "dev": ["pytest>=7.0.0", "black>=23.0.0", "ruff>=0.1.0"],
}


def resolve_onnxruntime_requirement(
    platform_name: str | None = None,
    *,
    nvidia_smi: bool | None = None,
) -> str:
    """Return the ONNX Runtime pip requirement for this machine."""

    platform_name = (platform_name or sys.platform).lower()
    if platform_name == "darwin":
        return "onnxruntime"
    if nvidia_smi is None:
        nvidia_smi = shutil.which("nvidia-smi") is not None
    if nvidia_smi:
        return "onnxruntime-gpu"
    return "onnxruntime"


def build_install_plan(
    *,
    platform_name: str | None = None,
    nvidia_smi: bool | None = None,
    extras: Sequence[str] = (),
) -> list[tuple[str, list[str]]]:
    """Return labeled pip argument groups (no subprocess)."""

    extras = tuple(extra.strip() for extra in extras if extra and extra.strip())
    extra_suffix = f"[{','.join(extras)}]" if extras else ""
    ort = resolve_onnxruntime_requirement(platform_name, nvidia_smi=nvidia_smi)
    extra_packages: list[str] = []
    for extra in extras:
        extra_packages.extend(EXTRA_DEPS.get(extra, []))
    return [
        ("editable --no-deps", ["-e", f".{extra_suffix}", "--no-deps"]),
        ("pdf2muse deps", list(PDF2MUSE_CORE_DEPS)),
        ("oemer --no-deps", ["oemer>=0.1.8", "--no-deps"]),
        ("oemer third-party", list(OEMER_THIRD_PARTY_DEPS)),
        ("onnxruntime", [ort]),
        ("extras", extra_packages),
    ]


def _pip(packages: Sequence[str]) -> None:
    if not packages:
        return
    subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])


def install_pdf2muse(
    extras: Iterable[str] = (),
    *,
    upgrade_pip: bool = True,
) -> None:
    extras_tuple = tuple(extras)
    if upgrade_pip:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
        )
    for _label, args in build_install_plan(extras=extras_tuple):
        _pip(args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install PDF2Muse with a platform ONNX Runtime wheel.")
    parser.add_argument(
        "--extras",
        default="",
        help="Comma-separated extras: ui,dev,api",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip checkpoint download (CI / tests).",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download oemer checkpoints after install.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    extras = [part.strip() for part in args.extras.split(",") if part.strip()]
    install_pdf2muse(extras)
    if args.download and not args.no_download:
        from pdf2muse.oemer_utils import download_checkpoints

        download_checkpoints(force=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
