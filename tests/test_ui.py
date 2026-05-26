"""Robust tests for the PDF2Muse Gradio WebUI."""

import zipfile
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


@pytest.fixture
def mock_pdf(tmp_path):
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf data")
    
    mock_file = MagicMock()
    mock_file.name = str(pdf)
    return mock_file


def make_pipeline_mock(*args, **kwargs):
    """Dynamic instantiator for PDF2MusePipeline mock that intercepts output_dir."""
    output_dir = kwargs.get("output_dir", "output")
    out_path = Path(output_dir)
    
    instance = MagicMock()
    instance.output_dir = out_path
    
    def mock_run():
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "combined.musicxml").write_text("<score></score>")
        (out_path / "combined.mscx").write_text("<musescore></musescore>")
        return out_path / "combined.mscx"
        
    instance.run.side_effect = mock_run
    return instance


@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_success(mock_pipeline_class, mock_pdf):
    """Test successful single PDF conversion in UI."""
    # Run conversion handler
    status, xml_path, mscx_path = convert_pdf(
        pdf_file=mock_pdf,
        deskew=True,
        use_tf=False,
    )
    
    assert "Conversion Complete" in status
    assert xml_path is not None
    assert mscx_path is not None
    assert Path(xml_path).name == "pdf2muse_combined.musicxml"
    assert Path(mscx_path).name == "pdf2muse_combined.mscx"


def test_convert_pdf_missing():
    """Test single PDF conversion fails gracefully if no file provided."""
    status, xml_path, mscx_path = convert_pdf(None)
    assert "Please upload a PDF file first" in status
    assert xml_path is None
    assert mscx_path is None


@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_batch_pdfs_success(mock_pipeline_class, mock_pdf):
    """Test successful batch conversion of multiple PDFs in UI."""
    # Run batch conversion
    status, zip_path = convert_batch_pdfs(
        pdf_files=[mock_pdf, mock_pdf],
        deskew=True,
        use_tf=False,
    )
    
    assert "Batch Processing Complete" in status
    assert zip_path is not None
    assert Path(zip_path).exists()
    
    # Verify contents of zip
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        namelist = zipf.namelist()
        assert "sheet.musicxml" in namelist
        assert "sheet.mscx" in namelist


def test_convert_batch_pdfs_missing():
    """Test batch conversion fails gracefully if no files provided."""
    status, zip_path = convert_batch_pdfs([])
    assert "Please upload one or more PDF files first" in status
    assert zip_path is None


@patch("pdf2muse.ui.shutil.which")
@patch("pdf2muse.ui.find_musescore_binary")
@patch("pdf2muse.ui.get_checkpoint_dir")
def test_run_diagnostics(mock_chk_dir, mock_find_ms, mock_which, tmp_path):
    """Test diagnostic report covers all system utilities."""
    mock_which.return_value = "/usr/bin/pdftoppm"
    mock_find_ms.return_value = Path("/usr/bin/mscore")
    
    # Mock checkpoints folder
    chk_dir = tmp_path / "checkpoints"
    (chk_dir / "unet_big").mkdir(parents=True)
    (chk_dir / "seg_net").mkdir(parents=True)
    (chk_dir / "unet_big" / "model.onnx").write_text("data")
    (chk_dir / "seg_net" / "model.onnx").write_text("data")
    mock_chk_dir.return_value = chk_dir
    
    report = run_diagnostics()
    
    assert "System Pre-Flight Diagnostics" in report
    assert "Poppler PDF Engine" in report
    assert "MuseScore Interface" in report
    assert "Deep Learning OMR Models" in report
    assert "✅ PASS" in report
    assert "✅ DETECTED" in report


@patch("pdf2muse.ui.download_checkpoints")
def test_download_checkpoints_ui_success(mock_download):
    """Test UI checkpoint manager runs success trigger."""
    status = download_checkpoints_ui()
    mock_download.assert_called_once_with(force=True)
    assert "successfully" in status


@patch("pdf2muse.ui.download_checkpoints")
def test_download_checkpoints_ui_failure(mock_download):
    """Test UI checkpoint manager handles download errors gracefully."""
    mock_download.side_effect = RuntimeError("Network timeout")
    status = download_checkpoints_ui()
    assert "Failed to download" in status
    assert "Network timeout" in status


def test_create_interface():
    """Test Gradio Blocks instantiation finishes correctly."""
    interface = create_interface(
        default_poppler="/mock/poppler",
        default_musescore="/mock/msc",
    )
    assert isinstance(interface, gr.Blocks)
    assert interface.title == "PDF2Muse - Sheet Music Converter"
