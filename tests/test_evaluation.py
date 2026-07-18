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
    slice_musicxml_leading_measures,
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


def test_load_manifest_preserves_optional_metadata(tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "clean-typeset",
                "input": "score.pdf",
                "ground_truth": "truth.musicxml",
                "license_notes": "Public domain source, local transcription",
                "difficulty_tags": ["clean-typeset", "single-staff", "easy"],
            }
        ],
    )

    loaded = load_manifest(manifest)

    assert loaded[0].license_notes == "Public domain source, local transcription"
    assert loaded[0].difficulty_tags == ("clean-typeset", "single-staff", "easy")


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


def test_parse_musicxml_rejects_well_formed_non_musicxml(tmp_path):
    path = tmp_path / "not-musicxml.musicxml"
    path.write_text("<root></root>", encoding="utf-8")

    result = parse_musicxml(path)

    assert result.ok is False
    assert "score-partwise" in result.error


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


@patch("pdf2muse.evaluation.importlib.util.find_spec", return_value=None)
def test_compare_musicxml_files_marks_optional_library_parse_unavailable(mock_find_spec, tmp_path):
    predicted = tmp_path / "predicted.musicxml"
    truth = tmp_path / "truth.musicxml"
    predicted.write_text(VALID_MUSICXML, encoding="utf-8")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")

    comparison = compare_musicxml_files(predicted, truth, use_musicdiff=False)

    assert comparison["library_parse_status"] == "unavailable"
    assert comparison["failure_categories"] == ["optional_tool_unavailable"]
    assert mock_find_spec.call_count >= 1


@patch("pdf2muse.evaluation.importlib.util.find_spec", return_value=None)
def test_compare_musicxml_files_reports_missing_musicdiff_as_unavailable(mock_find_spec, tmp_path):
    predicted = tmp_path / "predicted.musicxml"
    truth = tmp_path / "truth.musicxml"
    predicted.write_text(VALID_MUSICXML, encoding="utf-8")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")

    comparison = compare_musicxml_files(predicted, truth, use_musicdiff=True)

    assert comparison["musicdiff_status"] == "unavailable"


def test_normalized_difference_handles_zero_expected():
    assert normalized_difference(0, 0) == 0.0
    assert normalized_difference(3, 0) == 3.0
    assert normalized_difference(5, 10) == 0.5


def test_slice_musicxml_leading_measures_and_page_scoped_compare(tmp_path):
    multi = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<score-partwise version="3.1">\n'
        "  <part-list>\n"
        '    <score-part id="P1"><part-name>Music</part-name></score-part>\n'
        "  </part-list>\n"
        '  <part id="P1">\n'
        '    <measure number="1"><note><rest/><duration>1</duration></note></measure>\n'
        '    <measure number="2"><note><rest/><duration>1</duration></note></measure>\n'
        '    <measure number="3"><note><rest/><duration>1</duration></note></measure>\n'
        "  </part>\n"
        "</score-partwise>\n"
    )
    truth = tmp_path / "truth.musicxml"
    predicted = tmp_path / "predicted.musicxml"
    truth.write_text(multi, encoding="utf-8")
    predicted.write_text(VALID_MUSICXML, encoding="utf-8")

    sliced = tmp_path / "sliced.musicxml"
    slice_musicxml_leading_measures(truth, sliced, measure_count=1)
    assert count_musicxml(sliced).measures == 1

    comparison = compare_musicxml_files(
        predicted,
        truth,
        use_musicdiff=False,
        first_page=1,
        last_page=1,
    )
    assert comparison["gt_page_scope"]["strategy"] == "leading_measures"
    assert comparison["structural_counts"]["ground_truth"]["measures"] == 1


def test_parse_omr_ned_from_text_ignores_trailing_diff_braces():
    from pdf2muse.evaluation import _extract_omr_ned, _parse_omr_ned_from_text

    text = (
        '{\n    "OMR-ED": "12",\n    "numSymbolsInPredicted": "40",\n'
        '    "numSymbolsInGroundTruth": "40",\n    "numSymbolsInBoth": "80",\n'
        '    "OMR-NED": "0.15"\n}\n'
        "Part P1 vs P2\n"
        "changedInfo={something: {nested: true}}\n"
        "more trailing }\n"
    )
    parsed = _parse_omr_ned_from_text(text)
    assert parsed is not None
    assert _extract_omr_ned(parsed) == 0.15


def test_extract_omr_ned_accepts_string_and_recovers_from_mixed_text():
    from pdf2muse.evaluation import _extract_omr_ned

    assert _extract_omr_ned("0.42") == 0.42
    assert _extract_omr_ned({"OMR-NED": "0.33"}) == 0.33
    mixed = '{"OMR-NED": "0.21"}\nchangedInfo={a: {b: 1}}'
    assert _extract_omr_ned(mixed) == 0.21


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_records_metadata_and_grouped_reports(mock_pipeline, tmp_path):
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
                "license_notes": "CC0 local fixture",
                "difficulty_tags": ["clean-typeset", "easy"],
            }
        ],
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
        render_dpi=400,
        oemer_device="cuda",
    )

    assert summary.total_samples == 1
    assert summary.completed_samples == 1
    assert summary.failed_samples == 0
    result = summary.results[0]
    assert result.license_notes == "CC0 local fixture"
    assert result.difficulty_tags == ["clean-typeset", "easy"]
    assert result.failure_category is None
    json_report = json.loads(
        (tmp_path / "evaluation-output" / "evaluation_results.json").read_text(encoding="utf-8")
    )
    assert json_report["metric_summaries"]["predicted_parse_ok"]["passed"] == 1
    assert "failure_categories" in json_report
    assert json_report["group_summaries"]["source"]["local"]["total_samples"] == 1
    assert json_report["group_summaries"]["difficulty_tags"]["clean-typeset"]["total_samples"] == 1
    assert json_report["results"][0]["license_notes"] == "CC0 local fixture"
    markdown = (tmp_path / "evaluation-output" / "evaluation_summary.md").read_text(
        encoding="utf-8"
    )
    assert "## Metric Summary" in markdown
    assert "## Failure Categories" in markdown
    assert "## Grouped Results" in markdown
    assert "CC0 local fixture" in markdown
    assert "clean-typeset, easy" in markdown
    mock_pipeline.assert_called_once()
    assert mock_pipeline.call_args.kwargs["render_dpi"] == 400
    assert mock_pipeline.call_args.kwargs["oemer_device"] == "cuda"


@patch("pdf2muse.evaluation._run_musicdiff")
@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_summarizes_omrned(mock_pipeline, mock_musicdiff, tmp_path):
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
    mock_musicdiff.return_value = {
        "musicdiff_status": "completed",
        "musicdiff_text": '{"OMR-NED": "0.25"}',
        "musicdiff_omrned": {"OMR-NED": "0.25"},
    }
    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        use_musicdiff=True,
    )

    assert summary.metric_summaries["omr_ned"]["count"] == 1
    assert summary.metric_summaries["omr_ned"]["average"] == 0.25


@patch("pdf2muse.evaluation.subprocess.run")
@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_records_musescore_import_status(mock_pipeline, mock_run, tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    musescore = tmp_path / "MuseScore4.exe"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    musescore.write_text("fake executable", encoding="utf-8")
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
    mock_run.return_value = subprocess.CompletedProcess(
        [str(musescore), "-o", "out.mscx", "in.musicxml"],
        0,
        stdout="",
        stderr="",
    )

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        limit=1,
        use_musicdiff=False,
        musescore_path=musescore,
    )

    metrics = summary.results[0].metrics
    assert metrics["musescore_import_status"] == "completed"
    assert mock_run.call_args.args[0][0] == str(musescore)


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


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_preserves_parse_failure_metrics_from_strict_pipeline(
    mock_pipeline, tmp_path
):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [{"id": "sample-1", "input": "score.pdf", "ground_truth": "truth.musicxml"}],
    )
    mock_pipeline.return_value.run.side_effect = RuntimeError(
        "Combined MusicXML is invalid: no element found"
    )

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        use_musicdiff=False,
    )

    result = summary.results[0]
    assert result.failure_category == "parse/import"
    assert result.metrics["predicted_parse_ok"] is False
    assert summary.metric_summaries["predicted_parse_ok"]["failed"] == 1


def test_run_evaluation_skips_untrusted_inputs_unless_allowed(tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "untrusted-1",
                "input": "score.pdf",
                "ground_truth": "truth.musicxml",
                "input_quality": {
                    "renderer": "pil",
                    "trusted_for_accuracy": False,
                },
            }
        ],
    )

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        use_musicdiff=False,
    )
    assert summary.skipped_samples == 1
    assert summary.results[0].status == "skipped"
    assert summary.results[0].failure_category == "untrusted_input"

    with patch("pdf2muse.evaluation.PDF2MusePipeline") as mock_pipeline:
        mock_pipeline.return_value.run.side_effect = RuntimeError("should not run")
        allowed = run_evaluation(
            manifest_path=manifest,
            output_dir=tmp_path / "evaluation-allowed",
            use_musicdiff=False,
            allow_untrusted_inputs=True,
        )
    assert allowed.skipped_samples == 0
    assert allowed.failed_samples == 1


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_propagates_failure_class_from_conversion_report(
    mock_pipeline, tmp_path
):
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
        report = {
            "pages": [
                {
                    "attempts": [
                        {"failure_class": "symbol_extraction_empty_candidates"},
                    ]
                }
            ]
        }
        (output_dir / "conversion_report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        raise RuntimeError("OMR failed")

    mock_pipeline.return_value.run = MagicMock(side_effect=run_side_effect)
    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        use_musicdiff=False,
        oemer_device="cuda",
        oemer_quality_profile="quality",
    )
    result = summary.results[0]
    assert result.failure_category == "symbol_extraction_empty_candidates"
    assert result.metrics["failure_class"] == "symbol_extraction_empty_candidates"
    assert summary.run_metadata["oemer_device"] == "cuda"
    assert summary.run_metadata["oemer_quality_profile"] == "quality"
    assert "model_backend" in summary.run_metadata


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_group_summaries_include_structural_deltas(mock_pipeline, tmp_path):
    pdf = tmp_path / "score.pdf"
    truth = tmp_path / "truth.musicxml"
    pdf.write_bytes(b"%PDF-1.4")
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    predicted = VALID_MUSICXML.replace("<octave>4</octave>", "<octave>5</octave>")
    # Add a second note so structural note delta is non-zero vs truth counts may still match
    # Use identical XML for completed parse; structural_differences will be zeros.
    manifest = write_manifest(
        tmp_path,
        [
            {
                "id": "sample-1",
                "input": "score.pdf",
                "ground_truth": "truth.musicxml",
                "source": "openscore",
                "difficulty_tags": ["clean-real"],
            }
        ],
    )

    def run_side_effect():
        output_dir = Path(mock_pipeline.call_args.kwargs["output_dir"])
        result = output_dir / "combined.musicxml"
        result.write_text(predicted, encoding="utf-8")
        return result

    mock_pipeline.return_value.run = MagicMock(side_effect=run_side_effect)
    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=tmp_path / "evaluation-output",
        use_musicdiff=False,
    )
    group = summary.group_summaries["source"]["openscore"]
    assert group["completed_samples"] == 1
    assert "structural_delta_notes_median" in group
    assert "structural_delta_measures_median" in group
