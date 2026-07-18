"""Generate a small local clean-typeset benchmark for PDF2Muse evaluation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pdf2muse.musicxml import find_musescore_binary


PITCH_STEPS = ("C", "D", "E", "F", "G", "A", "B")

# Pattern of (step_offset, duration_divisions, type, is_rest) with divisions=4 (quarter=4).
# One measure of 4/4 = 16 divisions.
_MEASURE_PATTERN = (
    (0, 4, "quarter", False),
    (2, 4, "quarter", False),
    (4, 2, "eighth", False),
    (5, 2, "eighth", False),
    (0, 4, "quarter", True),
)


@dataclass(frozen=True)
class GeneratedSample:
    """Paths and metadata for one generated benchmark sample."""

    sample_id: str
    pdf_path: Path
    musicxml_path: Path
    difficulty_tags: list[str]


def create_clean_typeset_benchmark(
    output_dir: Path,
    manifest_path: Path,
    *,
    sample_count: int = 20,
    musescore_path: Optional[Path] = None,
) -> list[GeneratedSample]:
    """Create deterministic local PDF/MusicXML pairs and a manifest."""

    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")

    musescore = find_musescore_binary(musescore_path)
    if musescore is None:
        raise RuntimeError(
            "MuseScore CLI is required to build trusted benchmark PDFs. "
            "Install MuseScore or run scripts/musescore_setup.py, then retry."
        )

    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)
    pdf_dir = output_dir / "pdfs"
    truth_dir = output_dir / "truth"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    input_quality = {
        "renderer": "musescore-cli",
        "trusted_for_accuracy": True,
    }

    samples: list[GeneratedSample] = []
    manifest_samples: list[dict] = []
    for index in range(1, sample_count + 1):
        sample_id = f"generated-clean-typeset-{index:03d}"
        # Dense enough for oemer symbol extraction (≥12 measures, mixed rhythms).
        measure_count = 12 + ((index - 1) % 4) * 2
        base_step_index = (index - 1) % len(PITCH_STEPS)
        tags = [
            "generated-fixture",
            "musescore-rendered",
            "oemer-smoke",
            "single-staff",
            "multi-measure",
        ]

        pdf_path = pdf_dir / f"{sample_id}.pdf"
        musicxml_path = truth_dir / f"{sample_id}.musicxml"
        _write_musicxml(
            musicxml_path,
            title=sample_id,
            measure_count=measure_count,
            base_step_index=base_step_index,
        )
        _render_musicxml_to_pdf(musescore, musicxml_path, pdf_path)

        samples.append(
            GeneratedSample(
                sample_id=sample_id,
                pdf_path=pdf_path,
                musicxml_path=musicxml_path,
                difficulty_tags=tags,
            )
        )
        manifest_samples.append(
            {
                "id": sample_id,
                "input": _manifest_path(manifest_path, pdf_path),
                "ground_truth": _manifest_path(manifest_path, musicxml_path),
                "source": "generated-local-clean-typeset",
                "license_notes": (
                    "Generated locally by PDF2Muse benchmark fixture script; "
                    "PDF rendered via MuseScore CLI from paired MusicXML."
                ),
                "difficulty_tags": tags,
                "input_quality": input_quality,
                "first_page": 1,
                "last_page": 1,
            }
        )

    manifest_path.write_text(
        json.dumps({"samples": manifest_samples}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return samples


def _render_musicxml_to_pdf(musescore: Path, musicxml_path: Path, pdf_path: Path) -> None:
    subprocess.run(
        [str(musescore), "-f", "-o", str(pdf_path), str(musicxml_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"MuseScore did not write PDF: {pdf_path}")


def _pitch_for(base_step_index: int, offset: int) -> tuple[str, int]:
    absolute = base_step_index + offset
    octave = 4 + (absolute // len(PITCH_STEPS))
    step = PITCH_STEPS[absolute % len(PITCH_STEPS)]
    # Keep pitches on the treble staff for oemer-friendly density.
    if octave < 4:
        octave = 4
    if octave > 5:
        octave = 5
    return step, octave


def _write_musicxml(
    path: Path,
    *,
    title: str,
    measure_count: int,
    base_step_index: int,
) -> None:
    measures = []
    for measure_number in range(1, measure_count + 1):
        attributes = ""
        if measure_number == 1:
            attributes = """
      <attributes>
        <divisions>4</divisions>
        <key><fifths>0</fifths></key>
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>"""
        notes_xml = []
        pattern_shift = (measure_number - 1) % len(PITCH_STEPS)
        for step_offset, duration, note_type, is_rest in _MEASURE_PATTERN:
            if is_rest:
                notes_xml.append(
                    f"""      <note>
        <rest/>
        <duration>{duration}</duration>
        <type>{note_type}</type>
      </note>"""
                )
                continue
            step, octave = _pitch_for(base_step_index, step_offset + pattern_shift)
            notes_xml.append(
                f"""      <note>
        <pitch><step>{step}</step><octave>{octave}</octave></pitch>
        <duration>{duration}</duration>
        <type>{note_type}</type>
      </note>"""
            )
        measures.append(
            f"""    <measure number="{measure_number}">{attributes}
{chr(10).join(notes_xml)}
      <barline location="right"><bar-style>regular</bar-style></barline>
    </measure>"""
        )

    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>{title}</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
{chr(10).join(measures)}
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )


def _manifest_path(manifest_path: Path, target: Path) -> str:
    return Path(os.path.relpath(target.resolve(), manifest_path.parent.resolve())).as_posix()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/cache/clean-typeset-generated"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evaluation/manifests/clean-typeset.local.json"),
    )
    parser.add_argument("--sample-count", type=int, default=20)
    args = parser.parse_args(argv)

    samples = create_clean_typeset_benchmark(
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        sample_count=args.sample_count,
    )
    print(f"Wrote {len(samples)} samples (MuseScore-rendered PDFs)")
    print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
