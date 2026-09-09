from pdf2muse.quality_gate import evaluate_quality_summary


def _summary(ned: float, samples: int = 5, parse_rate: float = 1.0) -> dict:
    passed = int(round(parse_rate * samples))
    return {
        "completed_samples": samples,
        "metric_summaries": {
            "omr_ned": {"average": ned, "count": samples},
            "predicted_parse_ok": {"passed": passed, "failed": samples - passed},
        },
    }


def test_quality_gate_passes_at_baseline():
    result = evaluate_quality_summary(_summary(0.576))
    assert result["passed"] is True


def test_quality_gate_fails_on_regression():
    result = evaluate_quality_summary(_summary(0.62))
    assert result["passed"] is False
    assert any("omr_ned" in reason for reason in result["reasons"])
