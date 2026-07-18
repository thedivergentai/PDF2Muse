"""Deterministic image degradation helpers for OMR dataset experiments."""

from __future__ import annotations

import json
import random
from io import BytesIO
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Union

from PIL import Image, ImageEnhance, ImageFilter


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED_SEVERITIES = {"light", "medium", "heavy"}


@dataclass(frozen=True)
class DegradedFile:
    """Metadata for one degraded image."""

    input: str
    output: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class DegradationMetadata:
    """Metadata written alongside generated degraded images."""

    profile: str
    severity: str
    seed: int
    profile_parameters: dict[str, Any]
    files: list[DegradedFile]


def degrade_directory(
    input_dir: Union[Path, str],
    output_dir: Union[Path, str],
    *,
    profile: str = "scan-noise",
    seed: int = 0,
    severity: str = "medium",
) -> DegradationMetadata:
    """Apply a deterministic degradation profile to every supported image."""

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    profile_parameters = _profile_parameters(profile, severity)
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
            degraded = degrade_image(
                image.convert("RGB"),
                profile=profile,
                seed=image_seed,
                severity=severity,
            )
            degraded.save(target_path)

        files.append(
            DegradedFile(
                input=relative_path.as_posix(),
                output=relative_path.as_posix(),
                parameters={**profile_parameters, "seed": image_seed},
            )
        )

    metadata = DegradationMetadata(
        profile=profile,
        severity=severity,
        seed=seed,
        profile_parameters=profile_parameters,
        files=files,
    )
    (output_path / "degradation_metadata.json").write_text(
        json.dumps(asdict(metadata), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return metadata


def degrade_image(
    image: Image.Image,
    *,
    profile: str,
    seed: int,
    severity: str = "medium",
) -> Image.Image:
    """Apply a named deterministic degradation profile to one image."""

    rng = random.Random(seed)
    params = _profile_parameters(profile, severity)

    if profile == "scan-noise":
        degraded = (
            ImageEnhance.Contrast(image.convert("L"))
            .enhance(params["contrast_factor"])
            .convert("RGB")
        )
        pixels = degraded.load()
        width, height = degraded.size
        noise_pixels = max(1, int(width * height * params["noise_ratio"]))
        for _ in range(noise_pixels):
            x = rng.randrange(width)
            y = rng.randrange(height)
            value = rng.choice((0, 255))
            pixels[x, y] = (value, value, value)
        return degraded.filter(ImageFilter.GaussianBlur(radius=params["blur_radius"]))

    if profile == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=params["blur_radius"]))

    if profile == "low-contrast":
        return ImageEnhance.Contrast(image).enhance(params["contrast_factor"])

    if profile == "shadow":
        shadow = image.convert("RGB")
        pixels = shadow.load()
        width, height = shadow.size
        for y in range(height):
            factor = params["min_factor"] + (
                (1.0 - params["min_factor"]) * y / max(1, height - 1)
            )
            for x in range(width):
                r, g, b = pixels[x, y]
                pixels[x, y] = (int(r * factor), int(g * factor), int(b * factor))
        return shadow

    if profile == "jpeg-artifacts":
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=params["quality"])
        buffer.seek(0)
        with Image.open(buffer) as compressed:
            return compressed.convert("RGB")

    if profile == "skew":
        return image.rotate(
            rng.choice((-1, 1)) * params["degrees"],
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor="white",
        )

    if profile == "uneven-lighting":
        return degrade_image(image, profile="shadow", seed=seed, severity=severity)

    raise ValueError(
        f"Unknown degradation profile: {profile}. "
        "Expected one of: scan-noise, blur, low-contrast, shadow, "
        "jpeg-artifacts, skew, uneven-lighting."
    )


def _profile_parameters(profile: str, severity: str) -> dict[str, Any]:
    if severity not in SUPPORTED_SEVERITIES:
        raise ValueError(
            f"Unknown severity: {severity}. Expected one of: light, medium, heavy."
        )

    if profile == "scan-noise":
        return {
            "contrast_factor": {"light": 0.92, "medium": 0.85, "heavy": 0.72}[severity],
            "noise_ratio": {"light": 0.006, "medium": 0.0125, "heavy": 0.025}[severity],
            "blur_radius": {"light": 0.15, "medium": 0.25, "heavy": 0.45}[severity],
        }
    if profile == "blur":
        return {"blur_radius": {"light": 0.55, "medium": 1.1, "heavy": 1.8}[severity]}
    if profile == "low-contrast":
        return {"contrast_factor": {"light": 0.7, "medium": 0.45, "heavy": 0.3}[severity]}
    if profile in {"shadow", "uneven-lighting"}:
        return {"min_factor": {"light": 0.8, "medium": 0.65, "heavy": 0.5}[severity]}
    if profile == "jpeg-artifacts":
        return {"quality": {"light": 65, "medium": 42, "heavy": 25}[severity]}
    if profile == "skew":
        return {"degrees": {"light": 0.4, "medium": 0.9, "heavy": 1.6}[severity]}

    raise ValueError(
        f"Unknown degradation profile: {profile}. "
        "Expected one of: scan-noise, blur, low-contrast, shadow, "
        "jpeg-artifacts, skew, uneven-lighting."
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
