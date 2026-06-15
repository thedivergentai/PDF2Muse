"""Deterministic image degradation helpers for OMR dataset experiments."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Union

from PIL import Image, ImageEnhance, ImageFilter


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class DegradedFile:
    """Metadata for one degraded image."""

    input: str
    output: str


@dataclass(frozen=True)
class DegradationMetadata:
    """Metadata written alongside generated degraded images."""

    profile: str
    seed: int
    files: list[DegradedFile]


def degrade_directory(
    input_dir: Union[Path, str],
    output_dir: Union[Path, str],
    *,
    profile: str = "scan-noise",
    seed: int = 0,
) -> DegradationMetadata:
    """Apply a deterministic degradation profile to every supported image."""

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_path}")
    if not input_path.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_path}")

    output_path.mkdir(parents=True, exist_ok=True)
    files: list[DegradedFile] = []

    for image_path in sorted(_iter_images(input_path)):
        relative_path = image_path.relative_to(input_path)
        target_path = output_path / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        image_seed = _derive_seed(seed, str(relative_path))
        with Image.open(image_path) as image:
            degraded = degrade_image(image.convert("RGB"), profile=profile, seed=image_seed)
            degraded.save(target_path)

        files.append(
            DegradedFile(
                input=relative_path.as_posix(),
                output=relative_path.as_posix(),
            )
        )

    metadata = DegradationMetadata(profile=profile, seed=seed, files=files)
    (output_path / "degradation_metadata.json").write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata


def degrade_image(image: Image.Image, *, profile: str, seed: int) -> Image.Image:
    """Apply a named deterministic degradation profile to one image."""

    rng = random.Random(seed)

    if profile == "scan-noise":
        degraded = ImageEnhance.Contrast(image.convert("L")).enhance(0.85).convert("RGB")
        pixels = degraded.load()
        width, height = degraded.size
        noise_pixels = max(1, (width * height) // 80)
        for _ in range(noise_pixels):
            x = rng.randrange(width)
            y = rng.randrange(height)
            value = rng.choice((0, 255))
            pixels[x, y] = (value, value, value)
        return degraded.filter(ImageFilter.GaussianBlur(radius=0.25))

    if profile == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=1.1))

    if profile == "low-contrast":
        return ImageEnhance.Contrast(image).enhance(0.45)

    if profile == "shadow":
        shadow = image.convert("RGB")
        pixels = shadow.load()
        width, height = shadow.size
        for y in range(height):
            factor = 0.65 + (0.35 * y / max(1, height - 1))
            for x in range(width):
                r, g, b = pixels[x, y]
                pixels[x, y] = (int(r * factor), int(g * factor), int(b * factor))
        return shadow

    raise ValueError(
        f"Unknown degradation profile: {profile}. "
        "Expected one of: scan-noise, blur, low-contrast, shadow."
    )


def _iter_images(input_dir: Path) -> list[Path]:
    return [
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]


def _derive_seed(seed: int, relative_path: str) -> int:
    value = seed
    for char in relative_path:
        value = ((value * 33) + ord(char)) % (2**32)
    return value
