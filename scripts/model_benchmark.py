"""Compare oemer and Legato backends on a local evaluation manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pdf2muse.adapters.legato import LegatoAdapter  # noqa: E402
from pdf2muse.legato_env import load_legato_env_defaults  # noqa: E402


@dataclass(frozen=True)
class BenchmarkVariant:
    name: str
    model_backend: str
    oemer_device: str
    oemer_quality_profile: str


DEFAULT_VARIANTS = [
    BenchmarkVariant("oemer-cpu-quality", "oemer-stock", "cpu", "quality"),
    BenchmarkVariant("oemer-cuda-quality", "oemer-stock", "cuda", "quality"),
    BenchmarkVariant("oemer-cuda-balanced", "oemer-stock", "cuda", "balanced"),
    BenchmarkVariant("legato-small", "legato-experimental", "cuda", "quality"),
]


def _load_legato_env() -> None:
    load_legato_env_defaults(REPO_ROOT)


def _dominant_failure_note(out_dir: Path) -> str:
    counts: dict[str, int] = {}
    for report_path in out_dir.glob("*/conversion_report.json"):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for page in report.get("pages", []):
            for attempt in page.get("attempts", []):
                failure_class = attempt.get("failure_class")
                if failure_class:
                    counts[str(failure_class)] = counts.get(str(failure_class), 0) + 1
    if not counts:
        return "no conversion_report failure_class"
    return max(counts, key=counts.get)


def _median_omr_ned(summary_data: dict) -> float | None:
    values: list[float] = []
    for result in summary_data.get("results", []):
        metrics = result.get("metrics", {})
        omr = metrics.get("musicdiff_omrned")
        if isinstance(omr, dict):
            for key in ("omr_ned", "omrned", "OMR-NED"):
                if key in omr:
                    try:
                        values.append(float(omr[key]))
                    except (TypeError, ValueError):
                        pass
    if not values:
        return None
    values.sort()
    return values[len(values) // 2]


def _run_variant(
    manifest: Path,
    output_root: Path,
    variant: BenchmarkVariant,
    *,
    limit: int | None,
    timeout: int,
    render_dpi: int,
) -> dict:
    out_dir = output_root / variant.name
    cmd = [
        sys.executable,
        "-m",
        "pdf2muse.cli",
        "evaluate",
        str(manifest),
        "--output",
        str(out_dir),
        "--model-backend",
        variant.model_backend,
        "--oemer-device",
        variant.oemer_device,
        "--oemer-quality-profile",
        variant.oemer_quality_profile,
        "--render-dpi",
        str(render_dpi),
        "--oemer-timeout",
        str(timeout),
    ]
    if limit is not None:
        cmd.extend(["--limit", str(limit)])

    env = os.environ.copy()
    if variant.model_backend == "legato-experimental":
        _load_legato_env()
        env.setdefault("PDF2MUSE_LEGATO_MODEL", "guangyangmusic/legato-small")

    print(f"\n=== {variant.name} ===")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    summary_path = out_dir / "evaluation_results.json"
    payload: dict = {
        "variant": variant.name,
        "model_backend": variant.model_backend,
        "oemer_device": variant.oemer_device,
        "oemer_quality_profile": variant.oemer_quality_profile,
        "exit_code": completed.returncode,
    }
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        payload.update(
            {
                "total_samples": data.get("total_samples"),
                "completed_samples": data.get("completed_samples"),
                "failed_samples": data.get("failed_samples"),
                "skipped_samples": data.get("skipped_samples", 0),
                "failure_categories": data.get("failure_categories", {}),
                "metric_summaries": data.get("metric_summaries", {}),
                "median_omr_ned": _median_omr_ned(data),
            }
        )
        payload["dominant_failure_class"] = _dominant_failure_note(out_dir)
    return payload


def _variant_score(item: dict) -> tuple[int, float, float]:
    completed = int(item.get("completed_samples") or 0)
    total = int(item.get("total_samples") or 0)
    median_ned = item.get("median_omr_ned")
    ned_score = -float(median_ned) if median_ned is not None else 999.0
    completion = completed / total if total else 0.0
    return (completed, completion, ned_score)


def _write_report(
    output_root: Path,
    results: list[dict],
    *,
    publish_docs: bool = False,
) -> Path:
    report_path = output_root / "model-benchmark-report.md"
    summary_path = output_root / "model-benchmark-summary.json"
    lines = [
        "# OMR model benchmark report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Variants",
        "",
        "| Variant | Backend | Device | Quality | Completed | Failed | Median OMR-NED | Notes |",
        "|---------|---------|--------|---------|-----------|--------|----------------|-------|",
    ]
    viable = [item for item in results if (item.get("completed_samples") or 0) > 0]
    best = max(viable, key=_variant_score) if viable else None

    for item in results:
        completed = item.get("completed_samples") or 0
        total = item.get("total_samples") or 0
        failed = item.get("failed_samples") or 0
        ned = item.get("median_omr_ned")
        ned_text = f"{ned:.4f}" if isinstance(ned, (int, float)) else "—"
        note = item.get("dominant_failure_class") or (
            "ok" if item.get("exit_code") == 0 else f"exit {item.get('exit_code')}"
        )
        lines.append(
            f"| {item['variant']} | {item['model_backend']} | {item['oemer_device']} | "
            f"{item['oemer_quality_profile']} | {completed}/{total} | {failed} | "
            f"{ned_text} | {note} |"
        )

    lines.extend(["", "## Recommended settings", ""])
    if best and (best.get("completed_samples") or 0) > 0:
        lines.append(
            f"- **Best variant in this run:** `{best['variant']}` "
            f"({best.get('completed_samples', 0)}/{best.get('total_samples', 0)} completed)"
        )
        if best["model_backend"].startswith("oemer"):
            lines.append(
                f"- Use `--model-backend oemer-stock --oemer-device {best['oemer_device']} "
                f"--oemer-quality-profile {best['oemer_quality_profile']}` for CLI/UI."
            )
        else:
            lines.append(
                "- Legato completed at least one sample; use `--model-backend legato-experimental` "
                "with `scripts/legato_setup.py` env file."
            )
    else:
        lines.append(
            "- No variant completed samples; inspect `conversion_report.json` under each variant folder."
        )

    lines.extend(["", "## Raw summaries", ""])
    for item in results:
        lines.append(f"### {item['variant']}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(item, indent=2)[:3000])
        lines.append("```")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    summary_path.write_text(
        json.dumps({"results": results, "best_variant": best}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if publish_docs:
        docs_copy = REPO_ROOT / "docs" / "evaluation" / "oemer-vs-legato-benchmark.md"
        docs_copy.write_text("\n".join(lines), encoding="utf-8")
        print(f"Published docs copy: {docs_copy}")
    else:
        print(
            "Docs copy skipped (pass --publish-docs after tier 1 passes, "
            "or let multi_tier_eval.py publish via tier 3)."
        )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "evaluation" / "manifests" / "clean-typeset-openscore.local.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "evaluation" / "runs" / "model-benchmark",
    )
    parser.add_argument("--limit", type=int, default=3, help="Samples per variant (QA default: 3)")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--render-dpi", type=int, default=300)
    parser.add_argument(
        "--variants",
        nargs="*",
        default=[v.name for v in DEFAULT_VARIANTS],
        help="Subset of variant names to run",
    )
    parser.add_argument(
        "--skip-legato",
        action="store_true",
        help="Skip legato-experimental variant",
    )
    parser.add_argument(
        "--also-fixtures",
        action="store_true",
        help="Also run against generated fixture manifest after primary manifest",
    )
    parser.add_argument(
        "--publish-docs",
        action="store_true",
        help=(
            "Overwrite docs/evaluation/oemer-vs-legato-benchmark.md "
            "(use after tier 1 passes; multi_tier_eval enables this for tier 3)"
        ),
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest missing: {args.manifest}. Run scripts/openscore_benchmark.py first.")
        return 1

    _load_legato_env()
    args.output.mkdir(parents=True, exist_ok=True)
    selected = {v.name: v for v in DEFAULT_VARIANTS}
    names = args.variants
    if args.skip_legato:
        names = [n for n in names if n != "legato-small"]

    if "legato-small" in names:
        status = LegatoAdapter().healthcheck()
        if not status.available:
            print(f"Skipping legato-small: {status.message}")
            names = [n for n in names if n != "legato-small"]

    results: list[dict] = []
    for name in names:
        variant = selected.get(name)
        if variant is None:
            print(f"Unknown variant: {name}")
            return 1
        print(f"Running {name}…")
        results.append(
            _run_variant(
                args.manifest,
                args.output,
                variant,
                limit=args.limit,
                timeout=args.timeout,
                render_dpi=args.render_dpi,
            )
        )

    if args.also_fixtures:
        fixture_manifest = REPO_ROOT / "evaluation" / "manifests" / "clean-typeset.local.json"
        if fixture_manifest.exists():
            for name in ("oemer-cuda-quality",):
                variant = selected.get(name)
                if variant is None:
                    continue
                fixture_variant = BenchmarkVariant(
                    f"{variant.name}-fixtures",
                    variant.model_backend,
                    variant.oemer_device,
                    variant.oemer_quality_profile,
                )
                results.append(
                    _run_variant(
                        fixture_manifest,
                        args.output,
                        fixture_variant,
                        limit=min(3, args.limit),
                        timeout=args.timeout,
                        render_dpi=args.render_dpi,
                    )
                )

    report = _write_report(args.output, results, publish_docs=args.publish_docs)
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
