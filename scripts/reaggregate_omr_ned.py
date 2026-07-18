"""Offline re-aggregate OMR-NED from existing evaluation_results.json (no OMR re-run).

Recovers NED from musicdiff_text when musicdiff_omrned was null due to the brace-parse bug.

Example:
  venv\\Scripts\\python.exe scripts\\reaggregate_omr_ned.py ^
    evaluation\\runs\\multi-tier-quality-v1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.evaluation import (  # noqa: E402
    EvaluationResult,
    EvaluationSummary,
    _extract_omr_ned,
    _parse_omr_ned_from_text,
    _summarize_metrics,
    _write_json_report,
    _write_markdown_report,
)


def _recover_metrics(metrics: dict) -> tuple[dict, bool]:
    metrics = dict(metrics)
    changed = False
    current = _extract_omr_ned(metrics.get("musicdiff_omrned"))
    if current is not None:
        return metrics, False
    text = metrics.get("musicdiff_text")
    if not isinstance(text, str) or not text.strip():
        return metrics, False
    parsed = _parse_omr_ned_from_text(text)
    ned = _extract_omr_ned(parsed)
    if ned is None:
        return metrics, False
    metrics["musicdiff_omrned"] = parsed
    metrics["omr_ned_recovered_offline"] = True
    return metrics, True


def reaggregate_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    results: list[EvaluationResult] = []
    recovered = 0
    for item in data.get("results", []):
        metrics, changed = _recover_metrics(dict(item.get("metrics") or {}))
        if changed:
            recovered += 1
        results.append(
            EvaluationResult(
                sample_id=item["sample_id"],
                source=item.get("source", "local"),
                input_path=item.get("input_path", ""),
                ground_truth_path=item.get("ground_truth_path", ""),
                output_path=item.get("output_path"),
                status=item.get("status", "failed"),
                elapsed_seconds=float(item.get("elapsed_seconds") or 0),
                metrics=metrics,
                error=item.get("error"),
                license_notes=item.get("license_notes"),
                difficulty_tags=list(item.get("difficulty_tags") or []),
                failure_category=item.get("failure_category"),
                severity=item.get("severity", "ok"),
            )
        )

    summary = EvaluationSummary(
        total_samples=len(results),
        completed_samples=sum(1 for r in results if r.status == "completed"),
        failed_samples=sum(1 for r in results if r.status == "failed"),
        skipped_samples=int(data.get("skipped_samples") or 0),
        results=results,
        metric_summaries=_summarize_metrics(results),
        failure_categories=data.get("failure_categories") or {},
        group_summaries=data.get("group_summaries") or {},
        run_metadata={
            **(data.get("run_metadata") or {}),
            "omr_ned_reaggregated": True,
            "omr_ned_recovered_samples": recovered,
        },
    )
    out_json = path.with_name("evaluation_results.reaggregated.json")
    out_md = path.with_name("evaluation_summary.reaggregated.md")
    _write_json_report(out_json, summary)
    _write_markdown_report(out_md, summary)
    # Also overwrite primary files so taxonomy/docs see recovered NED.
    _write_json_report(path, summary)
    _write_markdown_report(path.with_name("evaluation_summary.md"), summary)
    return {
        "path": str(path),
        "recovered_samples": recovered,
        "omr_ned": summary.metric_summaries.get("omr_ned"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Multi-tier or single-eval directory containing evaluation_results.json",
    )
    args = parser.parse_args()
    run_dir = args.run_dir
    files = sorted(run_dir.rglob("evaluation_results.json"))
    if not files:
        print(f"No evaluation_results.json under {run_dir}")
        return 1
    report = {"files": []}
    for path in files:
        print(f"Re-aggregating {path}")
        report["files"].append(reaggregate_file(path))
    out = run_dir / "omr-ned-reaggregate-report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
