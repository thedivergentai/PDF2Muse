"""Classify OMR-NED disagreements from a completed evaluation directory.

Buckets: part_collapse, high_edit_dense, sparse_ok, metric_null, pitch_rhythm.

Example:
  venv\\Scripts\\python.exe scripts\\ned_error_taxonomy.py ^
    evaluation\\runs\\multi-tier-quality-v1\\tier1b-musescore-com ^
    --docs-out docs\\evaluation\\ned-error-taxonomy.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.evaluation import _extract_omr_ned, _parse_omr_ned_from_text  # noqa: E402


def _ned_for(metrics: dict) -> float | None:
    ned = _extract_omr_ned(metrics.get("musicdiff_omrned"))
    if ned is not None:
        return ned
    text = metrics.get("musicdiff_text")
    if isinstance(text, str):
        return _extract_omr_ned(_parse_omr_ned_from_text(text))
    return None


def _bucket(sample: dict) -> str:
    metrics = sample.get("metrics") or {}
    ned = _ned_for(metrics)
    status = metrics.get("musicdiff_status")
    if status == "completed" and ned is None:
        return "metric_null"
    if status != "completed":
        return "metric_null"

    counts = metrics.get("structural_counts") or {}
    pred = counts.get("predicted") or {}
    gt = counts.get("ground_truth") or {}
    pred_parts = int(pred.get("parts") or metrics.get("predicted_parts") or 0)
    gt_parts = int(gt.get("parts") or metrics.get("gt_parts") or 0)
    if metrics.get("part_collapse") or (gt_parts > 1 and pred_parts < gt_parts):
        return "part_collapse"

    gt_notes = int(gt.get("notes") or 0)
    notes_rel = abs(float((metrics.get("structural_differences") or {}).get("notes") or 0))
    # Low NED wins regardless of density.
    if ned is not None and ned <= 0.40:
        return "sparse_ok"
    if notes_rel < 0.15 and ned is not None and ned >= 0.45:
        return "pitch_rhythm"
    if ned is not None and ned >= 0.70:
        return "high_edit_dense"
    if gt_notes >= 120 and ned is not None and ned >= 0.55:
        return "high_edit_dense"
    if ned is not None and ned >= 0.45:
        return "pitch_rhythm"
    return "sparse_ok"


def classify(eval_json: Path) -> dict:
    data = json.loads(eval_json.read_text(encoding="utf-8"))
    buckets: dict[str, dict] = {}
    samples_out: list[dict] = []
    for item in data.get("results", []):
        metrics = item.get("metrics") or {}
        ned = _ned_for(metrics)
        bucket = _bucket(item)
        entry = buckets.setdefault(bucket, {"count": 0, "samples": [], "omr_ned_values": []})
        entry["count"] += 1
        entry["samples"].append(item["sample_id"])
        if ned is not None:
            entry["omr_ned_values"].append(ned)
        samples_out.append(
            {
                "sample_id": item["sample_id"],
                "status": item.get("status"),
                "bucket": bucket,
                "omr_ned": ned,
                "predicted_parts": (metrics.get("structural_counts") or {})
                .get("predicted", {})
                .get("parts"),
                "gt_parts": (metrics.get("structural_counts") or {})
                .get("ground_truth", {})
                .get("parts"),
                "notes_rel": (metrics.get("structural_differences") or {}).get("notes"),
            }
        )

    for entry in buckets.values():
        values = entry["omr_ned_values"]
        entry["omr_ned_average"] = (sum(values) / len(values)) if values else None
        del entry["omr_ned_values"]

    return {
        "source": str(eval_json),
        "buckets": buckets,
        "samples": samples_out,
    }


def _to_markdown(payload: dict) -> str:
    lines = [
        "# NED error taxonomy",
        "",
        f"Source: `{payload['source']}`",
        "",
        "| Bucket | Count | Avg OMR-NED | Samples |",
        "|--------|-------|-------------|---------|",
    ]
    for name, entry in sorted(
        payload["buckets"].items(), key=lambda kv: (-kv[1]["count"], kv[0])
    ):
        avg = entry.get("omr_ned_average")
        avg_s = "—" if avg is None else f"{avg:.3f}"
        samples = ", ".join(f"`{s}`" for s in entry.get("samples") or []) or "—"
        lines.append(f"| `{name}` | {entry['count']} | {avg_s} | {samples} |")
    lines.extend(["", "## Per-sample", ""])
    lines.append("| Sample | Bucket | OMR-NED | Parts pred/GT | notes_rel |")
    lines.append("|--------|--------|---------|---------------|-----------|")
    for sample in payload["samples"]:
        ned = sample.get("omr_ned")
        ned_s = "—" if ned is None else f"{ned:.3f}"
        lines.append(
            f"| `{sample['sample_id']}` | `{sample['bucket']}` | {ned_s} | "
            f"{sample.get('predicted_parts')}/{sample.get('gt_parts')} | "
            f"{sample.get('notes_rel')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `part_collapse`: GT has more parts/staves than OMR output; full NED is inflated.",
            "- `pitch_rhythm`: note counts nearly match but NED is high → symbol-level errors.",
            "- `high_edit_dense`: dense scores with very high edit distance.",
            "- `sparse_ok`: relatively low NED on simpler pages.",
            "- `metric_null`: musicdiff completed without a recoverable OMR-NED value.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_dir", type=Path)
    parser.add_argument("--docs-out", type=Path, default=None)
    args = parser.parse_args()
    eval_json = args.eval_dir
    if eval_json.is_dir():
        eval_json = eval_json / "evaluation_results.json"
    if not eval_json.exists():
        print(f"Missing {eval_json}")
        return 1
    payload = classify(eval_json)
    out_json = eval_json.parent / "ned-error-taxonomy.json"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md = _to_markdown(payload)
    (eval_json.parent / "ned-error-taxonomy.md").write_text(md, encoding="utf-8")
    if args.docs_out:
        args.docs_out.parent.mkdir(parents=True, exist_ok=True)
        args.docs_out.write_text(md, encoding="utf-8")
    print(f"Wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
