"""Create degraded-PDF benchmark variants from an evaluation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
from PIL import Image

from pdf2muse.degrade import degrade_image
from pdf2muse.evaluation import load_manifest


def create_degraded_benchmark(
    manifest_path: Path,
    output_dir: Path,
    output_manifest: Path,
    *,
    profile: str,
    severity: str,
    seed: int = 0,
    render_dpi: int = 300,
    limit: Optional[int] = None,
) -> int:
    """Render PDF samples, degrade the first page, and write degraded PDFs."""

    samples = load_manifest(manifest_path)
    if limit is not None:
        samples = samples[: max(0, limit)]

    output_dir = Path(output_dir)
    pdf_dir = output_dir / "pdfs"
    image_dir = output_dir / "rendered-images"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)

    manifest_samples = []
    for index, sample in enumerate(samples, start=1):
        first_page = sample.first_page or 1
        last_page = sample.last_page or first_page
        if first_page != last_page:
            raise ValueError(
                "Degraded benchmark generation currently supports single-page "
                f"samples only: {sample.sample_id}"
            )
        image_seed = _derive_seed(seed, sample.sample_id)
        rendered = image_dir / f"{sample.sample_id}.png"
        degraded_pdf = pdf_dir / f"{sample.sample_id}-{profile}-{severity}.pdf"
        _render_pdf_page(
            sample.input_path,
            rendered,
            page_number=first_page,
            render_dpi=render_dpi,
        )
        with Image.open(rendered) as image:
            degraded = degrade_image(
                image.convert("RGB"),
                profile=profile,
                severity=severity,
                seed=image_seed,
            )
            degraded.save(degraded_pdf, "PDF", resolution=float(render_dpi))

        tags = list(sample.difficulty_tags)
        for tag in (f"degraded-{profile}", f"severity-{severity}"):
            if tag not in tags:
                tags.append(tag)

        input_quality = dict(sample.input_quality or {})
        input_quality.update(
            {
                "renderer": "degraded-from-trusted",
                "trusted_for_accuracy": False,
                "degrade_profile": profile,
                "degrade_severity": severity,
            }
        )
        manifest_samples.append(
            {
                "id": f"{sample.sample_id}-{profile}-{severity}",
                "input": _relative(output_manifest, degraded_pdf),
                "ground_truth": _relative(output_manifest, sample.ground_truth_path),
                "source": f"{sample.source or 'unknown'} degraded with {profile}",
                "license_notes": sample.license_notes,
                "difficulty_tags": tags,
                "first_page": 1,
                "last_page": 1,
                "input_quality": input_quality,
            }
        )
        print(f"[{index}/{len(samples)}] wrote {degraded_pdf}")

    output_manifest.write_text(
        json.dumps({"samples": manifest_samples}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return len(manifest_samples)


def _render_pdf_page(
    pdf_path: Path,
    output_image: Path,
    *,
    page_number: int,
    render_dpi: int,
) -> None:
    pdf = pdfium.PdfDocument(str(pdf_path))
    if len(pdf) == 0:
        raise RuntimeError(f"PDF has no pages: {pdf_path}")
    page_index = page_number - 1
    if page_index < 0 or page_index >= len(pdf):
        raise RuntimeError(f"PDF page {page_number} is out of range: {pdf_path}")
    bitmap = pdf[page_index].render(scale=render_dpi / 72)
    bitmap.to_pil().save(output_image, "PNG")


def _relative(base_file: Path, target: Path) -> str:
    import os

    return Path(os.path.relpath(target.resolve(), base_file.parent.resolve())).as_posix()


def _derive_seed(seed: int, sample_id: str) -> int:
    value = seed
    for char in sample_id:
        value = ((value * 33) + ord(char)) % (2**32)
    return value


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--profile", default="scan-noise")
    parser.add_argument("--severity", default="light")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--render-dpi", type=int, default=300)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    count = create_degraded_benchmark(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        output_manifest=args.output_manifest,
        profile=args.profile,
        severity=args.severity,
        seed=args.seed,
        render_dpi=args.render_dpi,
        limit=args.limit,
    )
    print(f"Wrote degraded manifest with {count} samples: {args.output_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
