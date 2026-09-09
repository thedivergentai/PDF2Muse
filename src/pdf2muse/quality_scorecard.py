"""Format conversion quality metrics for UI and reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def load_conversion_report(output_dir: Path) -> Optional[dict[str, Any]]:
    """Load conversion_report.json when present."""

    report_path = Path(output_dir) / "conversion_report.json"
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def format_quality_scorecard(report: dict[str, Any]) -> str:
    """Render a markdown quality scorecard from a conversion report."""

    backend = report.get("model_backend", {})
    backend_name = backend.get("name", "unknown")
    final = report.get("final_musicxml", {})
    structure = final.get("structure", {})
    join = report.get("join", {})
    pages = report.get("pages", [])
    ok_pages = sum(1 for page in pages if page.get("status") == "completed")
    total_pages = len(pages)

    lines = [
        "### Quality scorecard",
        "",
        f"- **Backend:** `{backend_name}`",
        f"- **Pages recognized:** {ok_pages}/{total_pages}",
        f"- **Combined MusicXML gate:** `{final.get('status', 'unknown')}`",
    ]
    if structure:
        lines.extend(
            [
                f"- **Parts:** {structure.get('parts', 0)}",
                f"- **Measures:** {structure.get('measures', 0)}",
                f"- **Notes:** {structure.get('notes', 0)}",
            ]
        )
    if join:
        lines.append(
            f"- **Join:** {join.get('files_joined', 0)} page(s) merged"
            f" ({join.get('files_skipped', 0)} skipped)"
        )
    flags = report.get("flags") or []
    if flags:
        lines.append("")
        lines.append("**Review flags:**")
        for flag in flags[:12]:
            kind = flag.get("kind", "flag")
            message = flag.get("message", "")
            lines.append(f"- `{kind}`: {message}")
        if len(flags) > 12:
            lines.append(f"- …and {len(flags) - 12} more")
    lines.append("")
    lines.append(
        "*Review generated notation in MuseScore or another editor before "
        "performance, teaching, or publication.*"
    )
    return "\n".join(lines)


def _latest_multi_tier_summary(root: Path) -> Optional[Path]:
    runs = root / "evaluation" / "runs"
    if not runs.exists():
        return None
    candidates = list(runs.glob("multi-tier-*/multi-tier-summary.json"))
    if not candidates:
        return None
    # Prefer timestamped directory name, then mtime (Windows mtime can collide).
    candidates.sort(
        key=lambda path: (path.parent.name, path.stat().st_mtime),
        reverse=True,
    )
    return candidates[0]


def load_benchmark_summary(repo_root: Optional[Path] = None) -> Optional[str]:
    """Return a short benchmark summary line from the latest multi-tier run."""

    root = repo_root or Path(__file__).resolve().parents[2]
    summary_json = _latest_multi_tier_summary(root)
    if summary_json is not None:
        try:
            payload = json.loads(summary_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            for tier in payload.get("tiers", []):
                if tier.get("tier") == "tier1a-openscore" and "parse_success_rate" in tier:
                    completed = tier.get("completed_samples", 0)
                    total = tier.get("total_samples", 0)
                    rate = tier.get("parse_success_rate", 0)
                    gate = "pass" if tier.get("gate_passed") else "fail"
                    return (
                        f"OpenScore tier1a: {completed}/{total} "
                        f"({rate:.0%} parse, gate {gate})"
                    )
    # Fallback: docs copy of the multi-tier markdown report
    multi_tier = root / "docs" / "evaluation" / "multi-tier-eval-report.md"
    if multi_tier.exists():
        for line in multi_tier.read_text(encoding="utf-8").splitlines():
            if line.startswith("| tier1a-openscore |"):
                return f"OpenScore tier: {line.strip('| ')}"
    summary_path = root / "docs" / "evaluation" / "clean-typeset-baseline-report-v2.md"
    if not summary_path.exists():
        return None
    text = summary_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("- **Parse success"):
            return line.lstrip("- ").strip()
    return None
