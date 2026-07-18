import json
from pathlib import Path

from pdf2muse.quality_scorecard import load_benchmark_summary


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
