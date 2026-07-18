"""Build a small local OpenScore CC0 benchmark for PDF2Muse."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import xml.etree.ElementTree as ET

from pdf2muse.musicxml import find_musescore_binary


OPEN_SCORE_RAW_BASE = "https://raw.githubusercontent.com/OpenScore/Lieder/main"


@dataclass(frozen=True)
class OpenScoreSample:
    sample_id: str
    title: str
    mxl_url: str
    source_path: str
    difficulty_tags: list[str]


DEFAULT_SAMPLES = [
    OpenScoreSample(
        sample_id="openscore-lieder-just-for-today",
        title="Just for Today",
        mxl_url=(
            f"{OPEN_SCORE_RAW_BASE}/scores/Abbott,_Jane_Bingham/_/"
            "Just_for_Today/lc6583477.mxl"
        ),
        source_path="scores/Abbott,_Jane_Bingham/_/Just_for_Today/lc6583477.mscx",
        difficulty_tags=["clean-typeset", "cc0", "voice-piano", "lyrics"],
    ),
    OpenScoreSample(
        sample_id="openscore-lieder-think-of-today",
        title="Think of Today",
        mxl_url=(
            f"{OPEN_SCORE_RAW_BASE}/scores/Abbott,_Jane_Bingham/_/"
            "Think_of_Today/lc6583512.mxl"
        ),
        source_path="scores/Abbott,_Jane_Bingham/_/Think_of_Today/lc6583512.mscx",
        difficulty_tags=["clean-typeset", "cc0", "voice-piano", "lyrics"],
    ),
    OpenScoreSample(
        sample_id="openscore-lieder-crazy-jane",
        title="Crazy Jane",
        mxl_url=(
            f"{OPEN_SCORE_RAW_BASE}/scores/Abrams,_Harriett/_/"
            "Crazy_Jane/lc6583907.mxl"
        ),
        source_path="scores/Abrams,_Harriett/_/Crazy_Jane/lc6583907.mscx",
        difficulty_tags=["clean-typeset", "cc0", "voice-piano", "lyrics"],
    ),
]


def create_openscore_benchmark(
    output_dir: Path,
    manifest_path: Path,
    *,
    samples: Optional[Iterable[OpenScoreSample]] = None,
) -> list[Path]:
    """Download CC0 OpenScore MXL files, render PDFs, and write a manifest."""

    selected_samples = list(samples or DEFAULT_SAMPLES)
    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    musescore = find_musescore_binary()
    if musescore is None:
        raise RuntimeError(
            "MuseScore CLI is required for trusted OpenScore benchmark PDFs. "
            "Install MuseScore or run scripts/musescore_setup.py, then retry."
        )

    created_pdfs: list[Path] = []
    manifest_samples = []
    renderer = "musescore-cli"
    input_quality = {
        "renderer": renderer,
        "trusted_for_accuracy": True,
    }
    for sample in selected_samples:
        sample_dir = output_dir / sample.sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)
        mxl_path = sample_dir / "source.mxl"
        musicxml_path = sample_dir / "ground_truth.musicxml"
        pdf_path = sample_dir / "input.pdf"
        metadata_path = sample_dir / "metadata.json"

        _download_file(sample.mxl_url, mxl_path)
        extract_musicxml_from_mxl(mxl_path, musicxml_path)
        _render_mxl_to_pdf(mxl_path, pdf_path)

        metadata = {
            "id": sample.sample_id,
            "title": sample.title,
            "source": "OpenScore Lieder",
            "source_url": "https://github.com/OpenScore/Lieder",
            "source_path": sample.source_path,
            "mxl_url": sample.mxl_url,
            "license": "CC0-1.0",
            "license_notes": (
                "OpenScore Lieder GitHub repository is licensed CC0-1.0; "
                "PDF and MusicXML were generated locally from the same MXL source."
            ),
            "difficulty_tags": sample.difficulty_tags,
            "renderer": renderer,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        manifest_samples.append(
            {
                "id": sample.sample_id,
                "input": _relative(manifest_path, pdf_path),
                "ground_truth": _relative(manifest_path, musicxml_path),
                "source": "OpenScore Lieder",
                "license_notes": metadata["license_notes"],
                "difficulty_tags": sample.difficulty_tags,
                "input_quality": input_quality,
                "first_page": 1,
                "last_page": 1,
            }
        )
        created_pdfs.append(pdf_path)

    manifest_path.write_text(
        json.dumps({"samples": manifest_samples}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return created_pdfs


def extract_musicxml_from_mxl(mxl_path: Path, output_path: Path) -> None:
    """Extract the first MusicXML score file from a compressed MXL archive."""

    with zipfile.ZipFile(mxl_path) as archive:
        rootfile = _mxl_rootfile(archive)
        if rootfile is None:
            candidates = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".xml", ".musicxml"))
                and not name.lower().startswith("meta-inf/")
            ]
            rootfile = candidates[0] if candidates else None
        if rootfile is None:
            raise ValueError(f"No MusicXML file found in {mxl_path}")
        output_path.write_bytes(archive.read(rootfile))


def _mxl_rootfile(archive: zipfile.ZipFile) -> Optional[str]:
    try:
        container = archive.read("META-INF/container.xml")
    except KeyError:
        return None
    root = ET.fromstring(container)
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "rootfile":
            full_path = element.attrib.get("full-path")
            if full_path:
                return full_path
    return None


def _render_mxl_to_pdf(mxl_path: Path, pdf_path: Path) -> None:
    musescore = find_musescore_binary()
    if musescore is None:
        raise RuntimeError("MuseScore CLI is required to render trusted OpenScore PDFs.")

    import subprocess

    subprocess.run(
        [str(musescore), "-f", "-o", str(pdf_path), str(mxl_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"MuseScore did not write PDF: {pdf_path}")


def _download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, target)


def _relative(base_file: Path, target: Path) -> str:
    return Path(os.path.relpath(target.resolve(), base_file.parent.resolve())).as_posix()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/benchmark-sources/clean-typeset/openscore-lieder"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evaluation/manifests/clean-typeset-openscore.local.json"),
    )
    parser.add_argument("--limit", type=int, default=len(DEFAULT_SAMPLES))
    args = parser.parse_args(argv)

    created = create_openscore_benchmark(
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        samples=DEFAULT_SAMPLES[: max(0, args.limit)],
    )
    print(f"Wrote {len(created)} OpenScore benchmark samples")
    print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
