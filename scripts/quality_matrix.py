"""Controlled DPI × profile × tiling matrix for recognition quality experiments.

Example:
  venv\\Scripts\\python.exe scripts\\quality_matrix.py ^
    --manifest evaluation/manifests/clean-typeset-openscore.local.json ^
    --output evaluation/runs/quality-matrix-v1 --limit 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.evaluation import run_evaluation  # noqa: E402


DEFAULT_CELLS = [
    {"render_dpi": 300, "oemer_quality_profile": "quality", "step_size": 128},
    {"render_dpi": 300, "oemer_quality_profile": "quality", "step_size": 192},
    {"render_dpi": 300, "oemer_quality_profile": "balanced", "step_size": 128},
    {"render_dpi": 360, "oemer_quality_profile": "quality", "step_size": 128},
    {"render_dpi": 360, "oemer_quality_profile": "balanced", "step_size": 192},
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--oemer-device", default="cuda")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run cells even when prior outputs exist",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for cell in DEFAULT_CELLS:
        label = (
            f"dpi{cell['render_dpi']}-"
            f"{cell['oemer_quality_profile']}-"
            f"step{cell['step_size']}"
        )
        cell_dir = args.output / label
        print(f"\n=== matrix cell {label} ===")
        os.environ["PDF2MUSE_OEMER_STEP_SIZE"] = str(cell["step_size"])
        os.environ["PDF2MUSE_OEMER_BATCH_SIZE"] = "16" if cell["step_size"] <= 128 else "8"
        summary = run_evaluation(
            manifest_path=args.manifest,
            output_dir=cell_dir,
            limit=args.limit,
            render_dpi=cell["render_dpi"],
            oemer_timeout_seconds=args.timeout,
            oemer_device=args.oemer_device,
            oemer_quality_profile=cell["oemer_quality_profile"],
            use_musicdiff=True,
            force=args.force,
        )
        omr = summary.metric_summaries.get("omr_ned") or {}
        rows.append(
            {
                "label": label,
                **cell,
                "completed": summary.completed_samples,
                "failed": summary.failed_samples,
                "total": summary.total_samples,
                "parse_success_rate": (
                    summary.completed_samples / summary.total_samples
                    if summary.total_samples
                    else 0.0
                ),
                "omr_ned_average": omr.get("average"),
                "omr_ned_count": omr.get("count"),
                "failure_categories": summary.failure_categories,
            }
        )

    rows_sorted = sorted(
        rows,
        key=lambda row: (
            -row["parse_success_rate"],
            row["omr_ned_average"] if row["omr_ned_average"] is not None else 1.0,
        ),
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(args.manifest),
        "limit": args.limit,
        "cells": rows_sorted,
        "winner": rows_sorted[0] if rows_sorted else None,
    }
    out_json = args.output / "quality-matrix-summary.json"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Quality matrix",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "| Cell | Parse | OMR-NED avg |",
        "|------|-------|-------------|",
    ]
    for row in rows_sorted:
        ned = "—" if row["omr_ned_average"] is None else f"{row['omr_ned_average']:.4f}"
        lines.append(
            f"| `{row['label']}` | {row['completed']}/{row['total']} "
            f"({row['parse_success_rate']:.0%}) | {ned} |"
        )
    if payload["winner"]:
        lines.extend(["", f"Ranked winner (parse then OMR-NED): `{payload['winner']['label']}`"])
    (args.output / "quality-matrix-report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
