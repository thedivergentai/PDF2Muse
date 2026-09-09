import json
from pathlib import Path

from pdf2muse.quality_scorecard import format_quality_scorecard, load_benchmark_summary


def test_load_benchmark_summary_prefers_latest_multi_tier_run(tmp_path):
    runs = tmp_path / "evaluation" / "runs"
    older = runs / "multi-tier-20260101-0100"
    newer = runs / "multi-tier-20260102-0200"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    older.joinpath("multi-tier-summary.json").write_text(
        json.dumps(
            {
                "tiers": [
                    {
                        "tier": "tier1a-openscore",
                        "completed_samples": 1,
                        "total_samples": 3,
                        "parse_success_rate": 0.333,
                        "gate_passed": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    newer.joinpath("multi-tier-summary.json").write_text(
        json.dumps(
            {
                "tiers": [
                    {
                        "tier": "tier1a-openscore",
                        "completed_samples": 3,
                        "total_samples": 3,
                        "parse_success_rate": 1.0,
                        "gate_passed": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    line = load_benchmark_summary(tmp_path)
    assert line is not None
    assert "3/3" in line
    assert "gate pass" in line


def test_load_benchmark_summary_returns_none_without_reports(tmp_path):
    assert load_benchmark_summary(tmp_path) is None


def test_format_quality_scorecard_includes_flags():
    markdown = format_quality_scorecard(
        {
            "model_backend": {"name": "oemer-stock"},
            "pages": [{"status": "completed"}],
            "final_musicxml": {
                "status": "ok",
                "structure": {"parts": 1, "measures": 8, "notes": 40},
            },
            "join": {"files_joined": 1, "files_skipped": 0},
            "flags": [{"kind": "underfull_measure", "message": "bar 2 short"}],
            "stage_timings": {"inference": 12.5},
        }
    )
    assert "Review flags" in markdown
    assert "underfull_measure" in markdown


def test_conversion_report_schema_requires_flags_and_stage_timings():
    required = {"flags", "stage_timings", "final_musicxml", "pages", "join"}
    report = {
        "flags": [{"kind": "header_lock", "message": "Locked key fifths=-2"}],
        "stage_timings": {"inference": 1.0},
        "final_musicxml": {"status": "ok"},
        "pages": [],
        "join": {},
    }
    assert required <= set(report)
    assert isinstance(report["flags"], list)
    assert isinstance(report["stage_timings"], dict)
