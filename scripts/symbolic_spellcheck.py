#!/usr/bin/env python3
"""Build synthetic corrupt↔GT pairs and run symbolic spellcheck flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from pdf2muse.spellcheck import (  # noqa: E402
    build_synthetic_training_pairs,
    spellcheck_musicxml,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gt-glob",
        type=str,
        default="evaluation/runs/multi-tier-quality-v1/tier1b-musescore-com/*/_gt_page_scoped.musicxml",
    )
    parser.add_argument(
        "--pairs-out",
        type=Path,
        default=_REPO / "evaluation" / "runs" / "spellcheck-pairs",
    )
    parser.add_argument(
        "--draft",
        type=Path,
        default=None,
        help="Optional OMR draft MusicXML to flag",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=_REPO / "evaluation" / "runs" / "spellcheck-pairs" / "report.json",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    gt_paths = sorted(_REPO.glob(args.gt_glob))[: args.limit]
    if not gt_paths:
        # Fallback: any tiny fixture
        fixture = _REPO / "tests" / "fixtures"
        gt_paths = sorted(fixture.glob("**/*.musicxml"))[: args.limit]

    manifest = {"pairs": [], "rate": 0.08, "seed": 42}
    if gt_paths:
        manifest = build_synthetic_training_pairs(gt_paths, args.pairs_out)

    flags_report = None
    if args.draft and args.draft.exists():
        flags_report = spellcheck_musicxml(args.draft).to_dict()
    elif gt_paths:
        # Demo flags on first corrupt pair
        corrupt = Path(manifest["pairs"][0]["corrupt"]) if manifest["pairs"] else None
        if corrupt and corrupt.exists():
            flags_report = spellcheck_musicxml(corrupt).to_dict()

    report = {
        "n_gt": len(gt_paths),
        "pairs_dir": str(args.pairs_out),
        "n_pairs": len(manifest.get("pairs", [])),
        "spellcheck": flags_report,
        "notes": [
            "Prototype only: flags melodic leaps; full seq2seq StaffGuard training is future work.",
            "Do not claim pitch accuracy improvements without held-out OMR-NED delta.",
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("n_gt", "n_pairs")}, indent=2))
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
