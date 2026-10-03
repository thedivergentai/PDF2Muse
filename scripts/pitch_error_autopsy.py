#!/usr/bin/env python3
"""Run pitch-error autopsy over multi-tier evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from pdf2muse.pitch_autopsy import autopsy_sample, summarize_autopsies  # noqa: E402


def _load_results(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "results" in data:
        return list(data["results"])
    if isinstance(data, list):
        return data
    raise ValueError(f"Unexpected evaluation JSON shape: {path}")


def _resolve_musicxml(sample_dir: Path) -> Path | None:
    for name in ("combined.musicxml", "page_001.musicxml"):
        cand = sample_dir / name
        if cand.exists():
            return cand
    return None


def _resolve_gt(sample_dir: Path, result: dict) -> Path | None:
    for name in ("_gt_page_scoped.musicxml", "ground_truth.musicxml"):
        cand = sample_dir / name
        if cand.exists():
            return cand
    gt = result.get("ground_truth_path")
    if gt:
        p = Path(gt)
        if p.exists():
            return p
    return None


def run_autopsy(run_dir: Path) -> dict:
    results_path = run_dir / "evaluation_results.json"
    if not results_path.exists():
        # Nested tier layout: aggregate child evaluation_results.json files.
        samples = []
        for child in sorted(run_dir.glob("**/evaluation_results.json")):
            for result in _load_results(child):
                sample_dir = child.parent / result.get("sample_id", "")
                if not sample_dir.is_dir():
                    sample_dir = child.parent
                metrics = result.get("metrics") or {}
                pred = _resolve_musicxml(sample_dir)
                gt = _resolve_gt(sample_dir, result)
                samples.append(
                    autopsy_sample(
                        sample_id=result.get("sample_id", sample_dir.name),
                        musicdiff_text=str(metrics.get("musicdiff_text") or ""),
                        omr_ned=metrics.get("omr_ned"),
                        predicted_parts=metrics.get("predicted_parts"),
                        gt_parts=metrics.get("gt_parts"),
                        predicted_path=pred,
                        ground_truth_path=gt,
                    )
                )
        summary = summarize_autopsies(samples)
        return {
            "run_dir": str(run_dir),
            "summary": summary,
            "samples": [s.to_dict() for s in samples],
        }

    samples = []
    for result in _load_results(results_path):
        sample_id = result.get("sample_id", "unknown")
        sample_dir = run_dir / sample_id
        metrics = result.get("metrics") or {}
        pred = _resolve_musicxml(sample_dir)
        gt = _resolve_gt(sample_dir, result)
        samples.append(
            autopsy_sample(
                sample_id=sample_id,
                musicdiff_text=str(metrics.get("musicdiff_text") or ""),
                omr_ned=metrics.get("omr_ned"),
                predicted_parts=metrics.get("predicted_parts"),
                gt_parts=metrics.get("gt_parts"),
                predicted_path=pred,
                ground_truth_path=gt,
            )
        )
    summary = summarize_autopsies(samples)
    return {
        "run_dir": str(run_dir),
        "summary": summary,
        "samples": [s.to_dict() for s in samples],
    }


def write_markdown(report: dict, path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# Pitch error autopsy",
        "",
        "Measured subclass attribution for OMR pitch/rhythm disagreements.",
        "This is diagnostic, not a claim of production pitch accuracy.",
        "",
        f"- Run: `{report['run_dir']}`",
        f"- Samples: {summary['samples']}",
        f"- Attributed samples: {summary['attributed_samples']} "
        f"({summary['attribution_rate']:.0%})",
        f"- ≥70% attribution gate: {'PASS' if summary['success_gate_70pct'] else 'FAIL'}",
        "",
        "## Dominant subclasses",
        "",
    ]
    for key, value in sorted(
        summary.get("dominant_distribution", {}).items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Subclass event totals", ""])
    for key, value in sorted(
        summary.get("subclass_totals", {}).items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Interpretation for next work",
            "",
            "- If `staff_off_by_one` / `accidental` dominate → consider `seg_net` FT "
            "with segmentation labels (after no-op checkpoint control).",
            "- If `clef_context` / `part_mismatch` dominate → prefer grand-staff "
            "topology repair and/or layout-aware backends (homr-class), not DPI.",
            "- If `duration_beam` dominates → builder/heuristics and symbolic spellcheck.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=_REPO / "evaluation" / "runs" / "multi-tier-quality-v1" / "tier1b-musescore-com",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=_REPO / "evaluation" / "runs" / "pitch-error-autopsy" / "autopsy.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=_REPO / "docs" / "evaluation" / "pitch-error-autopsy.md",
    )
    args = parser.parse_args()
    report = run_autopsy(args.run_dir)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, args.out_md)
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
