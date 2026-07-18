"""Run multi-tier OMR evaluation with production gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.evaluation import run_evaluation  # noqa: E402


@dataclass(frozen=True)
class EvalTier:
    name: str
    manifest: Path
    description: str
    min_parse_success: float = 0.0
    requires_prior_tier: str | None = None
    kind: str = "evaluate"  # evaluate | degrade | model_benchmark


DEFAULT_TIERS = [
    EvalTier(
        "tier0-fixtures",
        REPO_ROOT / "evaluation" / "manifests" / "clean-typeset.local.json",
        "Pipeline smoke on MuseScore-rendered fixtures",
        min_parse_success=0.0,
    ),
    EvalTier(
        "tier1a-openscore",
        REPO_ROOT / "evaluation" / "manifests" / "clean-typeset-openscore.local.json",
        "CC0 clean real scores (OpenScore)",
        min_parse_success=0.8,
    ),
    EvalTier(
        "tier1b-musescore-com",
        REPO_ROOT / "evaluation" / "manifests" / "musescore-com-manual.local.json",
        "User-like clean scores (MuseScore.com manual)",
        min_parse_success=0.8,
    ),
    EvalTier(
        "tier2-degraded",
        REPO_ROOT / "evaluation" / "manifests" / "clean-typeset-openscore-degraded.local.json",
        "Degraded forks of OpenScore (paired robustness)",
        min_parse_success=0.0,
        requires_prior_tier="tier1a-openscore",
        kind="degrade",
    ),
    EvalTier(
        "tier3-model-benchmark",
        REPO_ROOT / "evaluation" / "manifests" / "clean-typeset-openscore.local.json",
        "Backend compare (oemer vs Legato) after tier 1 passes",
        min_parse_success=0.0,
        requires_prior_tier="tier1a-openscore",
        kind="model_benchmark",
    ),
]


def _overall_release_passed(gate_status: dict[str, bool]) -> bool:
    """Release gate: tier0 smoke and tier1 accuracy lanes must both pass."""

    return bool(gate_status.get("tier0-fixtures", False)) and _tier1_passed(gate_status)


def _limit_for_tier(tier: EvalTier, *, limit: int, full_gates: bool) -> int:
    """Sample limit per tier; --full-gates uses full release-set sizes for 1a/1b."""

    if not full_gates:
        return limit
    if tier.name == "tier0-fixtures":
        return min(limit, 3) if limit > 0 else 3
    if tier.name == "tier1a-openscore":
        return 0  # no limit → all OpenScore samples (expected 3)
    if tier.name == "tier1b-musescore-com":
        return 0  # no limit → all MuseScore.com samples (expected 15)
    return limit


def _parse_rate(summary) -> float:
    if summary.total_samples == 0:
        return 0.0
    return summary.completed_samples / summary.total_samples


def _failure_taxonomy(summary) -> dict[str, dict]:
    """Bucket failures into join / errno / OMR / other for Observed reports."""

    buckets: dict[str, dict] = {}
    for result in summary.results:
        if result.status == "completed":
            continue
        category = result.failure_category or "unknown"
        metrics = result.metrics or {}
        raw = str(metrics.get("failure_class") or category)
        lowered = raw.lower()
        error = (result.error or "").lower()
        if "join" in lowered or "streamexception" in error or "music21" in error:
            bucket = "join_export"
        elif "errno22" in lowered or "errno 22" in error or "invalid argument" in error:
            bucket = "errno22_infra"
        elif lowered.startswith("symbol_") or lowered.startswith("staffline_") or lowered.startswith(
            "dewarp_"
        ):
            bucket = f"omr:{raw}"
        else:
            bucket = raw
        entry = buckets.setdefault(bucket, {"count": 0, "samples": []})
        entry["count"] += 1
        entry["samples"].append(result.sample_id)
    return buckets


def _musicdiff_completed_count(summary) -> int:
    count = 0
    for result in summary.results:
        if (result.metrics or {}).get("musicdiff_status") == "completed":
            count += 1
    return count


def _tier_passed(summary, tier: EvalTier) -> bool:
    if tier.min_parse_success <= 0:
        return summary.completed_samples >= 1
    return _parse_rate(summary) >= tier.min_parse_success


def _tier1_passed(gate_status: dict[str, bool]) -> bool:
    """Tier 1 gate: OpenScore required; MuseScore.com required when manifest exists."""

    if not gate_status.get("tier1a-openscore", False):
        return False
    musescore_manifest = (
        REPO_ROOT / "evaluation" / "manifests" / "musescore-com-manual.local.json"
    )
    if musescore_manifest.exists():
        return gate_status.get("tier1b-musescore-com", False)
    return True


def _ensure_degraded_manifest(source_manifest: Path, degraded_manifest: Path, *, limit: int) -> Path:
    degraded_manifest.parent.mkdir(parents=True, exist_ok=True)
    if degraded_manifest.exists():
        return degraded_manifest
    output_dir = REPO_ROOT / "datasets" / "cache" / "openscore-degraded"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "degrade_benchmark.py"),
        str(source_manifest),
        "--output-dir",
        str(output_dir),
        "--output-manifest",
        str(degraded_manifest),
        "--profile",
        "low-contrast",
        "--severity",
        "light",
        "--limit",
        str(limit),
    ]
    print(f"Generating degraded manifest: {degraded_manifest}")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    return degraded_manifest


def _run_model_benchmark(output_dir: Path, *, limit: int, timeout: int, render_dpi: int) -> dict:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "model_benchmark.py"),
        "--output",
        str(output_dir),
        "--limit",
        str(limit),
        "--timeout",
        str(timeout),
        "--render-dpi",
        str(render_dpi),
        "--publish-docs",
    ]
    print("Running model_benchmark.py (tier 3)…")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT))
    report = output_dir / "model-benchmark-report.md"
    summary_json = output_dir / "model-benchmark-summary.json"
    payload: dict = {
        "tier": "tier3-model-benchmark",
        "status": "completed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "report": str(report) if report.exists() else None,
    }
    if summary_json.exists():
        try:
            payload["summary"] = json.loads(summary_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT
        / "evaluation"
        / "runs"
        / f"multi-tier-{datetime.now().strftime('%Y%m%d-%H%M')}",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--oemer-device", default="cuda")
    parser.add_argument("--oemer-quality-profile", default="quality")
    parser.add_argument("--oemer-timeout", type=int, default=900)
    parser.add_argument("--render-dpi", type=int, default=300)
    parser.add_argument("--model-backend", default="oemer-stock")
    parser.add_argument(
        "--tiers",
        nargs="*",
        default=[tier.name for tier in DEFAULT_TIERS],
    )
    parser.add_argument(
        "--skip-tier-gates",
        action="store_true",
        help="Run all tiers even if prior tier gate fails",
    )
    parser.add_argument(
        "--full-gates",
        action="store_true",
        help=(
            "Use full release-set sizes: tier0 up to 3 samples; "
            "tier1a/1b unrestricted (all manifest samples)"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run samples even when prior combined.musicxml/conversion already succeeded",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    tier_map = {tier.name: tier for tier in DEFAULT_TIERS}
    tier_results: list[dict] = []
    gate_status: dict[str, bool] = {}
    tier1a_summary = None

    for tier_name in args.tiers:
        tier = tier_map.get(tier_name)
        if tier is None:
            print(f"Unknown tier: {tier_name}")
            return 1

        tier_limit = _limit_for_tier(tier, limit=args.limit, full_gates=args.full_gates)

        if tier.kind == "model_benchmark":
            if not args.skip_tier_gates and not _tier1_passed(gate_status):
                print(f"Skipping {tier_name}: tier 1 gate not passed")
                tier_results.append(
                    {
                        "tier": tier_name,
                        "status": "blocked_by_prior_tier",
                        "blocked_by": "tier1",
                    }
                )
                continue
            out_dir = args.output / tier_name
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = _run_model_benchmark(
                out_dir,
                limit=tier_limit if tier_limit > 0 else args.limit,
                timeout=args.oemer_timeout,
                render_dpi=args.render_dpi,
            )
            gate_status[tier_name] = payload.get("exit_code") == 0
            tier_results.append(payload)
            continue

        manifest = tier.manifest
        if tier.kind == "degrade":
            source = REPO_ROOT / "evaluation" / "manifests" / "clean-typeset-openscore.local.json"
            if not source.exists():
                print(f"Skipping {tier_name}: source OpenScore manifest missing")
                tier_results.append(
                    {
                        "tier": tier_name,
                        "status": "skipped_missing_manifest",
                        "manifest": str(source),
                    }
                )
                continue
            if (
                tier.requires_prior_tier
                and not args.skip_tier_gates
                and not gate_status.get(tier.requires_prior_tier, False)
            ):
                print(f"Skipping {tier_name}: blocked by failed gate on {tier.requires_prior_tier}")
                tier_results.append(
                    {
                        "tier": tier_name,
                        "status": "blocked_by_prior_tier",
                        "blocked_by": tier.requires_prior_tier,
                    }
                )
                continue
            try:
                degrade_limit = tier_limit if tier_limit > 0 else args.limit
                manifest = _ensure_degraded_manifest(
                    source, tier.manifest, limit=degrade_limit
                )
            except subprocess.CalledProcessError as exc:
                tier_results.append(
                    {
                        "tier": tier_name,
                        "status": "degrade_generation_failed",
                        "error": str(exc),
                    }
                )
                continue

        if not manifest.exists():
            print(f"Skipping {tier_name}: manifest missing ({manifest})")
            tier_results.append(
                {
                    "tier": tier_name,
                    "status": "skipped_missing_manifest",
                    "manifest": str(manifest),
                }
            )
            continue
        if (
            tier.requires_prior_tier
            and not args.skip_tier_gates
            and not gate_status.get(tier.requires_prior_tier, False)
        ):
            print(f"Skipping {tier_name}: blocked by failed gate on {tier.requires_prior_tier}")
            tier_results.append(
                {
                    "tier": tier_name,
                    "status": "blocked_by_prior_tier",
                    "blocked_by": tier.requires_prior_tier,
                }
            )
            continue

        out_dir = args.output / tier_name
        print(f"\n=== {tier_name}: {tier.description} ===")
        eval_limit = None if tier_limit == 0 else tier_limit
        summary = run_evaluation(
            manifest_path=manifest,
            output_dir=out_dir,
            limit=eval_limit,
            model_backend=args.model_backend,
            render_dpi=args.render_dpi,
            oemer_timeout_seconds=args.oemer_timeout,
            oemer_device=args.oemer_device,
            oemer_quality_profile=args.oemer_quality_profile,
            use_musicdiff=True,
            # Tier 2 degraded samples are intentionally untrusted for accuracy.
            allow_untrusted_inputs=(tier.kind == "degrade"),
            force=args.force,
        )
        passed = _tier_passed(summary, tier)
        gate_status[tier_name] = passed
        item = {
            "tier": tier_name,
            "description": tier.description,
            "manifest": str(manifest),
            "completed_samples": summary.completed_samples,
            "failed_samples": summary.failed_samples,
            "skipped_samples": summary.skipped_samples,
            "total_samples": summary.total_samples,
            "parse_success_rate": round(_parse_rate(summary), 3),
            "gate_passed": passed,
            "min_parse_success": tier.min_parse_success,
            "failure_categories": summary.failure_categories,
            "failure_taxonomy": _failure_taxonomy(summary),
            "metric_summaries": summary.metric_summaries,
            "musicdiff_completed": _musicdiff_completed_count(summary),
        }
        if tier_name == "tier1a-openscore":
            tier1a_summary = summary
        if tier_name == "tier2-degraded" and tier1a_summary is not None:
            clean_rate = _parse_rate(tier1a_summary)
            degraded_rate = _parse_rate(summary)
            item["paired_delta"] = {
                "clean_parse_success_rate": round(clean_rate, 3),
                "degraded_parse_success_rate": round(degraded_rate, 3),
                "parse_rate_drop": round(clean_rate - degraded_rate, 3),
            }
            clean_ned = (tier1a_summary.metric_summaries.get("omr_ned") or {}).get("average")
            degraded_ned = (summary.metric_summaries.get("omr_ned") or {}).get("average")
            if clean_ned is not None and degraded_ned is not None:
                item["paired_delta"]["omr_ned_average_clean"] = clean_ned
                item["paired_delta"]["omr_ned_average_degraded"] = degraded_ned
                item["paired_delta"]["omr_ned_increase"] = degraded_ned - clean_ned
        tier_results.append(item)

    overall_passed = _overall_release_passed(gate_status)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_backend": args.model_backend,
        "oemer_device": args.oemer_device,
        "oemer_quality_profile": args.oemer_quality_profile,
        "limit": args.limit,
        "full_gates": args.full_gates,
        "tier0_passed": gate_status.get("tier0-fixtures", False),
        "tier1_passed": _tier1_passed(gate_status),
        "overall_release_passed": overall_passed,
        "tiers": tier_results,
    }
    json_path = args.output / "multi-tier-summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Multi-tier evaluation report",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        f"- Backend: `{args.model_backend}`",
        f"- Device: `{args.oemer_device}`",
        f"- Quality profile: `{args.oemer_quality_profile}`",
        f"- Limit per tier: {args.limit}",
        f"- Full gates: {args.full_gates}",
        f"- Tier 0 gate: {'pass' if payload['tier0_passed'] else 'fail'}",
        f"- Tier 1 gate: {'pass' if payload['tier1_passed'] else 'fail'}",
        f"- Overall release gate: {'pass' if overall_passed else 'fail'}",
        "",
        "## Tier results",
        "",
        "| Tier | Completed | Parse rate | Gate |",
        "|------|-----------|------------|------|",
    ]
    for item in tier_results:
        status = item.get("status")
        if status in {
            "skipped_missing_manifest",
            "blocked_by_prior_tier",
            "degrade_generation_failed",
        }:
            lines.append(f"| {item['tier']} | — | — | {status} |")
            continue
        if item.get("tier") == "tier3-model-benchmark":
            lines.append(
                f"| {item['tier']} | — | — | "
                f"{'pass' if item.get('exit_code') == 0 else 'fail'} |"
            )
            continue
        lines.append(
            f"| {item['tier']} | {item['completed_samples']}/{item['total_samples']} | "
            f"{item.get('parse_success_rate', 0):.0%} | "
            f"{'pass' if item.get('gate_passed') else 'fail'} |"
        )
        taxonomy = item.get("failure_taxonomy") or {}
        if taxonomy:
            lines.append("")
            lines.append(f"### Failure taxonomy (`{item['tier']}`)")
            lines.append("")
            lines.append("| Class | Count | Samples |")
            lines.append("|-------|-------|---------|")
            for class_name, payload in sorted(taxonomy.items(), key=lambda kv: (-kv[1]["count"], kv[0])):
                samples = ", ".join(payload.get("samples") or []) or "—"
                lines.append(f"| `{class_name}` | {payload['count']} | {samples} |")
        omr = (item.get("metric_summaries") or {}).get("omr_ned") or {}
        if omr.get("count"):
            lines.append("")
            lines.append(
                f"OMR-NED (`{item['tier']}`): n={omr['count']}, "
                f"avg={omr['average']:.4f}, min={omr['minimum']:.4f}, max={omr['maximum']:.4f}; "
                f"musicdiff completed on {item.get('musicdiff_completed', 0)} sample(s)."
            )
        paired = item.get("paired_delta")
        if paired:
            lines.append("")
            lines.append(
                f"Paired delta for `{item['tier']}`: parse drop "
                f"{paired.get('parse_rate_drop', 0):.0%} "
                f"(clean {paired.get('clean_parse_success_rate', 0):.0%} → "
                f"degraded {paired.get('degraded_parse_success_rate', 0):.0%})"
            )
    report_path = args.output / "multi-tier-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    docs_copy = REPO_ROOT / "docs" / "evaluation" / "multi-tier-eval-report.md"
    docs_copy.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSummary: {json_path}")
    print(f"Report: {report_path}")
    print(f"Overall release gate: {'pass' if overall_passed else 'fail'}")
    return 0 if overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
