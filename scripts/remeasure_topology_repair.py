#!/usr/bin/env python3
"""Remeasure part_collapse after topology repair on existing eval MusicXML."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from pdf2muse.musicxml import analyze_musicxml_structure  # noqa: E402
from pdf2muse.topology import repair_musicxml_topology  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=_REPO
        / "evaluation"
        / "runs"
        / "multi-tier-quality-v1"
        / "tier1b-musescore-com",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_REPO
        / "evaluation"
        / "runs"
        / "topology-repair-remeasure"
        / "remeasure.json",
    )
    parser.add_argument(
        "--expand-for-eval",
        action="store_true",
        help="Split grand-staff single parts into two simultaneous parts for GT part matching",
    )
    args = parser.parse_args()

    rows = []
    for sample_dir in sorted(p for p in args.run_dir.iterdir() if p.is_dir()):
        src = sample_dir / "combined.musicxml"
        if not src.exists():
            continue
        gt_path = sample_dir / "_gt_page_scoped.musicxml"
        gt_parts = (
            analyze_musicxml_structure(gt_path).parts if gt_path.exists() else None
        )
        work = args.out.parent / "samples" / sample_dir.name
        work.mkdir(parents=True, exist_ok=True)
        dst = work / "combined.musicxml"
        shutil.copy2(src, dst)
        before = analyze_musicxml_structure(dst)
        expand = bool(args.expand_for_eval and gt_parts is not None and gt_parts >= 2)
        report = repair_musicxml_topology(dst, expand_for_eval=expand)
        after = analyze_musicxml_structure(dst)
        part_match = gt_parts is not None and after.parts == gt_parts
        rows.append(
            {
                "sample_id": sample_dir.name,
                "gt_parts": gt_parts,
                "parts_before": before.parts,
                "parts_after": after.parts,
                "part_topology_match": part_match,
                "changed": report.changed,
                "actions": report.actions,
            }
        )

    collapsed = [
        r
        for r in rows
        if r["gt_parts"] is not None
        and r["gt_parts"] >= 2
        and r["parts_before"] == 1
    ]
    collapsed_fixed = sum(1 for r in collapsed if r["part_topology_match"])
    summary = {
        "samples": len(rows),
        "part_collapse_before": len(collapsed),
        "part_collapse_fixed": collapsed_fixed,
        "grand_staff_merges": sum(
            1
            for r in rows
            if any(a.startswith("grand_staff_merge:") for a in r["actions"])
        ),
        "normalized_or_expanded": sum(1 for r in rows if r["changed"]),
        "part_topology_matches": sum(1 for r in rows if r["part_topology_match"]),
    }
    payload = {"summary": summary, "samples": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
