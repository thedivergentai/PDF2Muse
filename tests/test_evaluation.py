import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf2muse.evaluation import (
    EvaluationManifestError,
    compare_musicxml_files,
    count_musicxml,
    load_manifest,
    normalized_difference,
    parse_musicxml,
    run_evaluation,
)


VALID_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>quarter</type>
      </note>
      <note>
        <rest/>
        <duration>1</duration>
        <type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


def write_manifest(tmp_path: Path, samples: list[dict]) -> Path:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    return manifest


def test_load_manifest_resolves_relative_paths(tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "sample-1",
                "input": "score.pdf",
                "ground_truth": "truth.musicxml",
                "source": "local-smoke",
                "first_page": 1,
                "last_page": 1,
            }
        ],
    )

    loaded = load_manifest(manifest)

    assert loaded[0].sample_id == "sample-1"
    assert loaded[0].input_path == pdf
    assert loaded[0].ground_truth_path == truth
    assert loaded[0].source == "local-smoke"
    assert loaded[0].first_page == 1
    assert loaded[0].last_page == 1


def test_load_manifest_rejects_missing_files(tmp_path):
    manifest = write_manifest(
        tmp_path,
        [{"id": "missing", "input": "missing.pdf", "ground_truth": "missing.musicxml"}],
    )

    with pytest.raises(EvaluationManifestError, match="Input file not found"):
        load_manifest(manifest)


def test_parse_musicxml_reports_valid_and_malformed(tmp_path):
    valid = tmp_path / "valid.musicxml"
    invalid = tmp_path / "invalid.musicxml"
    valid.write_text(VALID_MUSICXML, encoding="utf-8")
    invalid.write_text("<score-partwise>", encoding="utf-8")

    valid_result = parse_musicxml(valid)
    invalid_result = parse_musicxml(invalid)

    assert valid_result.ok is True
    assert valid_result.error is None
    assert invalid_result.ok is False
    assert "no element found" in invalid_result.error


def test_count_musicxml_collects_structural_counts(tmp_path):
    path = tmp_path / "score.musicxml"
    path.write_text(VALID_MUSICXML, encoding="utf-8")

    counts = count_musicxml(path)

    assert counts.parts == 1
    assert counts.measures == 1
    assert counts.notes == 2
    assert counts.rests == 1
    assert counts.pitched_notes == 1


def test_compare_musicxml_files_uses_structural_fallback(tmp_path):
    predicted = tmp_path / "predicted.musicxml"
    truth = tmp_path / "truth.musicxml"
    predicted.write_text(VALID_MUSICXML.replace("<rest/>", ""), encoding="utf-8")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")

    comparison = compare_musicxml_files(predicted, truth, use_musicdiff=False)

    assert comparison["predicted_parse_ok"] is True
    assert comparison["ground_truth_parse_ok"] is True
    assert comparison["musicdiff_status"] == "disabled"
    assert comparison["structural_differences"]["rests"] == 1.0


@patch("pdf2muse.evaluation.subprocess.run")
def test_compare_musicxml_files_reports_missing_musicdiff_as_unavailable(mock_run, tmp_path):
    predicted = tmp_path / "predicted.musicxml"
    truth = tmp_path / "truth.musicxml"
    predicted.write_text(VALID_MUSICXML, encoding="utf-8")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        ["python", "-m", "musicdiff"],
        stderr="No module named musicdiff",
    )

    comparison = compare_musicxml_files(predicted, truth, use_musicdiff=True)

    assert comparison["musicdiff_status"] == "unavailable"


def test_normalized_difference_handles_zero_expected():
    assert normalized_difference(0, 0) == 0.0
    assert normalized_difference(3, 0) == 3.0
    assert normalized_difference(5, 10) == 0.5


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_records_failures_and_writes_reports(mock_pipeline, tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [{"id": "sample-1", "input": "score.pdf", "ground_truth": "truth.musicxml"}],
    )

    def run_side_effect():
        output_dir = Path(mock_pipeline.call_args.kwargs["output_dir"])
        result = output_dir / "combined.musicxml"
        result.write_text(VALID_MUSICXML, encoding="utf-8")
        return result

    mock_pipeline.return_value.run = MagicMock(side_effect=run_side_effect)

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        limit=1,
        use_musicdiff=False,
    )

    assert summary.total_samples == 1
    assert summary.completed_samples == 1
    assert summary.failed_samples == 0
    assert (tmp_path / "evaluation-output" / "evaluation_results.json").exists()
    assert (tmp_path / "evaluation-output" / "evaluation_summary.md").exists()
    mock_pipeline.assert_called_once()


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_compares_combined_musicxml_when_mscx_is_primary(mock_pipeline, tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [{"id": "sample-1", "input": "score.pdf", "ground_truth": "truth.musicxml"}],
    )

    def run_side_effect():
        output_dir = Path(mock_pipeline.call_args.kwargs["output_dir"])
        musicxml = output_dir / "combined.musicxml"
        mscx = output_dir / "combined.mscx"
        musicxml.write_text(VALID_MUSICXML, encoding="utf-8")
        mscx.write_text("<museScore></museScore>", encoding="utf-8")
        return mscx

    mock_pipeline.return_value.run = MagicMock(side_effect=run_side_effect)

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        limit=1,
        use_musicdiff=False,
    )

    metrics = summary.results[0].metrics
    assert summary.completed_samples == 1
    assert metrics["comparison_path"].endswith("combined.musicxml")
    assert metrics["predicted_parse_ok"] is True
