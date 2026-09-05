"""Robust tests for the PDF2Muse Gradio WebUI."""



import zipfile

from types import SimpleNamespace

from pathlib import Path

from unittest.mock import MagicMock, patch



import pytest

import gradio as gr



from pdf2muse.ui import (

    convert_pdf,

    convert_batch_pdfs,

    run_diagnostics,

    download_checkpoints_ui,

    create_interface,

)





def _final_result(gen):

    """Consume a generator handler and return its last yielded tuple."""

    result = None

    for result in gen:

        pass

    return result





@pytest.fixture

def mock_pdf(tmp_path):

    pdf = tmp_path / "sheet.pdf"

    pdf.write_bytes(b"%PDF-1.4 mock pdf data")



    mock_file = MagicMock()

    mock_file.name = str(pdf)

    return mock_file





VALID_UI_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1"><measure number="1"><note><rest/><duration>1</duration></note></measure></part>
</score-partwise>
"""


def make_pipeline_mock(*args, **kwargs):
    """Mock PDF2MusePipeline that runs via pipeline.run()."""
    output_dir = Path(kwargs.get("output_dir", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    instance = MagicMock()
    instance.output_dir = output_dir
    instance.conversion_report = {
        "model_backend": {"name": kwargs.get("model_backend", "oemer-stock")},
        "pages": [{"status": "completed"}],
        "final_musicxml": {
            "status": "ok",
            "structure": {"parts": 1, "measures": 1, "notes": 1},
        },
        "join": {"files_joined": 1, "files_skipped": 0},
    }

    def mock_run(progress_callback=None):
        combined = output_dir / "combined.musicxml"
        combined.write_text(VALID_UI_MUSICXML, encoding="utf-8")
        mscx = output_dir / "combined.mscx"
        mscx.write_text("<musescore></musescore>", encoding="utf-8")
        if progress_callback:
            progress_callback(0.25, "OMR")
            progress_callback(1.0, "Complete")
        return mscx

    instance.run.side_effect = mock_run
    return instance


@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_success(mock_pipeline_class, mock_pdf):

    """Test successful single PDF conversion in UI."""

    status, xml_path, mscx_path, _skeleton, _btn = _final_result(

        convert_pdf(

            pdf_file=mock_pdf,

            deskew=True,

            use_tf=False,

        )

    )



    assert "conversion complete" in status.lower()
    assert "review" in status.lower()
    assert "quality scorecard" in status.lower()

    assert xml_path is not None

    assert mscx_path is not None

    assert Path(xml_path).name == "pdf2muse_combined.musicxml"

    assert Path(mscx_path).name == "pdf2muse_combined.mscx"



@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_prefers_gradio_file_path(mock_pipeline_class, tmp_path):
    """Newer Gradio FileData objects expose temp file paths via .path."""
    pdf = tmp_path / "uploaded.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf data")
    file_data = SimpleNamespace(path=str(pdf), name="original-filename.pdf")

    status, xml_path, mscx_path, _skeleton, _btn = _final_result(
        convert_pdf(file_data)
    )

    assert "conversion complete" in status.lower()
    assert xml_path is not None
    assert mscx_path is not None
    assert mock_pipeline_class.call_args.kwargs["pdf_path"] == str(pdf)





@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_yields_progress(mock_pipeline_class, mock_pdf):
    """Conversion should emit intermediate loading statuses."""

    statuses = [step[0] for step in convert_pdf(mock_pdf)]

    assert len(statuses) >= 2

    combined = " ".join(s.lower() for s in statuses[:-1])

    assert "preparing" in combined or "omr" in combined or "converting pdf" in combined





def test_convert_pdf_missing():

    """Test single PDF conversion fails gracefully if no file provided."""

    status, xml_path, mscx_path, _skeleton, _btn = _final_result(convert_pdf(None))

    assert "upload a pdf" in status.lower()

    assert xml_path is None

    assert mscx_path is None





@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_batch_pdfs_success(mock_pipeline_class, mock_pdf):
    """Test successful batch conversion of multiple PDFs in UI."""

    status, zip_path, _skeleton, _btn = _final_result(

        convert_batch_pdfs(

            pdf_files=[mock_pdf, mock_pdf],

            deskew=True,

            use_tf=False,

            first_page=1,

            last_page=2,

        )

    )



    assert "batch processing complete" in status.lower()

    assert zip_path is not None

    assert Path(zip_path).exists()



    with zipfile.ZipFile(zip_path, "r") as zipf:

        namelist = zipf.namelist()

        assert "sheet.musicxml" in namelist

        assert "sheet.mscx" in namelist



    assert mock_pipeline_class.call_args.kwargs.get("first_page") == 1

    assert mock_pipeline_class.call_args.kwargs.get("last_page") == 2



@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_batch_pdfs_prefers_gradio_file_path(mock_pipeline_class, tmp_path):
    """Batch conversion should use Gradio FileData.path when present."""
    pdf = tmp_path / "batch-upload.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf data")
    file_data = SimpleNamespace(path=str(pdf), name="original-batch-name.pdf")

    status, zip_path, _skeleton, _btn = _final_result(
        convert_batch_pdfs([file_data])
    )

    assert "batch processing complete" in status.lower()
    assert zip_path is not None
    assert mock_pipeline_class.call_args.kwargs["pdf_path"] == str(pdf)





def test_convert_batch_pdfs_missing():

    """Test batch conversion fails gracefully if no files provided."""

    status, zip_path, _skeleton, _btn = _final_result(convert_batch_pdfs([]))

    assert "upload" in status.lower()

    assert zip_path is None





@patch("pdf2muse.ui.find_musescore_binary")

@patch("pdf2muse.ui.get_checkpoint_dir")

def test_run_diagnostics(mock_chk_dir, mock_find_ms, tmp_path):

    """Test diagnostic report covers required components."""

    mock_find_ms.return_value = Path("/usr/bin/mscore")



    chk_dir = tmp_path / "checkpoints"

    (chk_dir / "unet_big").mkdir(parents=True)

    (chk_dir / "seg_net").mkdir(parents=True)

    (chk_dir / "unet_big" / "model.onnx").write_text("data")

    (chk_dir / "seg_net" / "model.onnx").write_text("data")

    mock_chk_dir.return_value = chk_dir



    report = run_diagnostics()



    assert "pre-flight diagnostics" in report.lower()

    assert "pypdfium2" in report.lower()

    assert "no poppler required" in report.lower()

    assert "MuseScore" in report

    assert "omr models" in report.lower()

    assert "[pass]" in report.lower() or "[ok]" in report.lower()

    assert "[detected]" in report.lower() or "[ready]" in report.lower()





@patch("pdf2muse.ui.download_checkpoints")

def test_download_checkpoints_ui_success(mock_download):

    """Test UI checkpoint manager runs success trigger."""

    status = download_checkpoints_ui()

    mock_download.assert_called_once_with(force=True)

    assert "downloaded" in status.lower() or "ready" in status.lower()





@patch("pdf2muse.ui.download_checkpoints")

def test_download_checkpoints_ui_failure(mock_download):

    """Test UI checkpoint manager handles download errors gracefully."""

    mock_download.side_effect = RuntimeError("Network timeout")

    status = download_checkpoints_ui()

    assert "failed to download" in status.lower()

    assert "Network timeout" in status





@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_passes_homr_backend_and_header_lock(mock_pipeline_class, mock_pdf):
    _final_result(
        convert_pdf(
            pdf_file=mock_pdf,
            deskew=True,
            use_tf=False,
            model_backend="homr",
            header_lock=True,
            peak_quality=True,
        )
    )
    kwargs = mock_pipeline_class.call_args.kwargs
    assert kwargs["model_backend"] == "homr"
    assert kwargs["header_lock_mode"] == "lock"
    # Peak quality must not wipe an explicit HOMR selection.
    assert kwargs["oemer_quality_profile"] == "quality"


@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_batch_pdfs_passes_homr_and_header_lock(mock_pipeline_class, mock_pdf):
    _final_result(
        convert_batch_pdfs(
            pdf_files=[mock_pdf],
            model_backend="homr",
            header_lock=True,
            oemer_device="cpu",
        )
    )
    kwargs = mock_pipeline_class.call_args.kwargs
    assert kwargs["model_backend"] == "homr"
    assert kwargs["header_lock_mode"] == "lock"
    assert kwargs["oemer_device"] == "cpu"


def test_create_interface():

    """Test Gradio Blocks instantiation finishes correctly."""

    interface = create_interface(default_musescore="/mock/msc")

    assert isinstance(interface, gr.Blocks)

    assert interface.title == "PDF2Muse - Sheet Music Converter"

    assert interface.css is not None

    assert "--color-primary: #EA580C" in interface.css

    serialized = interface.get_config_file()
    blob = str(serialized).lower()
    assert "homr" in blob
    assert "lock key" in blob


