"""Local OMR-NED quality gate against the locked quality-matrix baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASELINE_OMR_NED = 0.576
NED_TOLERANCE = 0.02
MIN_PARSE_RATE = 1.0
MIN_SAMPLES = 5


def evaluate_quality_summary(
    summary: dict[str, Any],
    *,
    baseline: float = BASELINE_OMR_NED,
    tolerance: float = NED_TOLERANCE,
) -> dict[str, Any]:
    """Return gate fields. Fail if NED regresses or parse rate drops."""

    metrics = summary.get("metric_summaries") or summary
    omr = metrics.get("omr_ned") or {}
    if isinstance(omr, dict):
        average = omr.get("average")
        count = omr.get("count") or summary.get("completed_samples")
    else:
        average = summary.get("average_omr_ned")
        count = summary.get("completed_samples")
    parse = metrics.get("predicted_parse_ok") or {}
    if isinstance(parse, dict):
        passed = parse.get("passed") or 0
        failed = parse.get("failed") or 0
        parse_total = passed + failed
        parse_rate = (passed / parse_total) if parse_total else summary.get("parse_success_rate")
    else:
        parse_rate = summary.get("parse_success_rate")
        parse_total = count
    ned_limit = baseline + tolerance
    reasons: list[str] = []
    if average is None:
        reasons.append("missing_omr_ned_average")
    elif float(average) > ned_limit:
        reasons.append(f"omr_ned {average} > {ned_limit}")
    if parse_rate is None:
        reasons.append("missing_parse_rate")
    elif float(parse_rate) < MIN_PARSE_RATE:
        reasons.append(f"parse_rate {parse_rate} < {MIN_PARSE_RATE}")
    if count is not None and int(count) < MIN_SAMPLES:
        reasons.append(f"sample_count {count} < {MIN_SAMPLES}")
    return {
        "passed": not reasons,
        "average_omr_ned": average,
        "ned_limit": ned_limit,
        "parse_rate": parse_rate,
        "sample_count": count,
        "reasons": reasons,
    }


def evaluate_quality_summary_path(path: Path) -> dict[str, Any]:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    return evaluate_quality_summary(summary)
