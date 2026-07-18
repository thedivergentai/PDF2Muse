"""Tests for the warm oemer worker client and eval resume."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf2muse.evaluation import _sample_has_successful_conversion, run_evaluation
from pdf2muse.oemer_worker_client import worker_enabled_for_device


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
    </measure>
  </part>
</score-partwise>
"""


def test_worker_enabled_defaults_cuda_on_cpu_off(monkeypatch):
    monkeypatch.delenv("PDF2MUSE_OEMER_WORKER", raising=False)
    assert worker_enabled_for_device("cuda") is True
    assert worker_enabled_for_device("cpu") is False
    assert worker_enabled_for_device("cuda", use_tf=True) is False
    monkeypatch.setenv("PDF2MUSE_OEMER_WORKER", "0")
    assert worker_enabled_for_device("cuda") is False
    monkeypatch.setenv("PDF2MUSE_OEMER_WORKER", "1")
    assert worker_enabled_for_device("cpu") is True


def test_sample_has_successful_conversion_requires_ok_musicxml(tmp_path):
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    assert _sample_has_successful_conversion(sample_dir) is False

    musicxml = sample_dir / "combined.musicxml"
    musicxml.write_text(VALID_MUSICXML, encoding="utf-8")
    assert _sample_has_successful_conversion(sample_dir) is True

    (sample_dir / "conversion_report.json").write_text(
        json.dumps(
            {
                "final_musicxml": {"status": "not_run"},
                "join": {"status": "failed"},
            }
        ),
        encoding="utf-8",
    )
    assert _sample_has_successful_conversion(sample_dir) is False

    (sample_dir / "conversion_report.json").write_text(
        json.dumps({"final_musicxml": {"status": "ok"}}),
        encoding="utf-8",
    )
    assert _sample_has_successful_conversion(sample_dir) is True


@patch("pdf2muse.evaluation.PDF2MusePipeline")
def test_run_evaluation_resumes_successful_sample_unless_force(mock_pipeline, tmp_path):
    truth = tmp_path / "truth.musicxml"
    truth.write_text(VALID_MUSICXML, encoding="utf-8")
    pdf = tmp_path / "score.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "id": "resume-me",
                        "input": str(pdf),
                        "ground_truth": str(truth),
                        "source": "test",
                        "input_quality": {"trusted_for_accuracy": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    sample_out = out / "resume-me"
    sample_out.mkdir(parents=True)
    (sample_out / "combined.musicxml").write_text(VALID_MUSICXML, encoding="utf-8")
    (sample_out / "conversion_report.json").write_text(
        json.dumps({"final_musicxml": {"status": "ok"}}),
        encoding="utf-8",
    )

    summary = run_evaluation(
        manifest_path=manifest,
        output_dir=out,
        use_musicdiff=False,
        force=False,
    )
    assert summary.completed_samples == 1
    assert summary.results[0].metrics.get("resumed") is True
    mock_pipeline.assert_not_called()

    mock_pipeline.return_value.run.return_value = sample_out / "combined.mscx"
    summary_forced = run_evaluation(
        manifest_path=manifest,
        output_dir=out,
        use_musicdiff=False,
        force=True,
    )
    assert mock_pipeline.called
    assert summary_forced.results[0].metrics.get("resumed") is not True


@patch("pdf2muse.adapters.oemer.get_oemer_worker")
def test_adapter_uses_worker_when_enabled(
    mock_get_worker, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    monkeypatch.setenv("PDF2MUSE_OEMER_WORKER", "1")
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    worker = MagicMock()
    worker.run_page.return_value = {
        "ok": True,
        "returncode": 0,
        "stdout": "ok",
        "stderr": "",
        "stages": {"session_load": 0.0, "inference_unet_big": 1.2, "total_page": 3.4},
        "musicxml_paths": [],
        "error": None,
    }

    def _side_effect(**kwargs):
        cwd = Path(kwargs["cwd"])
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / f"{mock_image.stem}.musicxml").write_text(mock_xml_content, encoding="utf-8")
        return worker.run_page.return_value

    worker.run_page.side_effect = _side_effect
    mock_get_worker.return_value = worker

    from pdf2muse.core import PDF2MusePipeline

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), oemer_device="cpu")
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert err is None
    assert xml_path is not None and xml_path.exists()
    mock_get_worker.assert_called_once_with("cpu")
    assert worker.run_page.called
    attempts = pipeline._page_attempts[mock_image.stem]
    assert attempts[0]["stages"]["session_load"] == 0.0
