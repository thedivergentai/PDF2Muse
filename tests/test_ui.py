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





def make_pipeline_mock(*args, **kwargs):

    """Dynamic instantiator for PDF2MusePipeline mock that intercepts output_dir."""

    output_dir = kwargs.get("output_dir", "output")

    out_path = Path(output_dir)



    instance = MagicMock()

    instance.output_dir = out_path

    instance.musescore_path = None



    def mock_pdf_to_png(image_dir):

        image_dir = Path(image_dir)

        image_dir.mkdir(parents=True, exist_ok=True)

        png = image_dir / "page_000.png"

        png.write_bytes(b"png")

        return [png]



    def mock_process_image_with_oemer(image_path, musicxml_dir):

        musicxml_dir = Path(musicxml_dir)

        musicxml_dir.mkdir(parents=True, exist_ok=True)

        out = musicxml_dir / f"{Path(image_path).stem}.musicxml"

        out.write_text("<score></score>")

        return out, None



    instance.pdf_to_png.side_effect = mock_pdf_to_png

    instance.process_image_with_oemer.side_effect = mock_process_image_with_oemer



    return instance





@patch("pdf2muse.ui.ensure_checkpoints")

@patch("pdf2muse.ui.join_musicxml_files")

@patch("pdf2muse.ui.convert_to_musescore_format")

@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)

def test_convert_pdf_success(

    mock_pipeline_class,

    mock_msc_convert,

    mock_join,

    mock_checkpoints,

    mock_pdf,

):

    """Test successful single PDF conversion in UI."""

    def write_outputs(musicxml_dir, combined_path):

        Path(combined_path).parent.mkdir(parents=True, exist_ok=True)

        Path(combined_path).write_text("<score></score>")



    def write_mscx(xml_path, mscx_path, musescore_path=None):

        Path(mscx_path).write_text("<musescore></musescore>")



    mock_join.side_effect = write_outputs

    mock_msc_convert.side_effect = write_mscx



    status, xml_path, mscx_path, _skeleton, _btn = _final_result(

        convert_pdf(

            pdf_file=mock_pdf,

            deskew=True,

            use_tf=False,

        )

    )



    assert "conversion complete" in status.lower()

    assert xml_path is not None

    assert mscx_path is not None

    assert Path(xml_path).name == "pdf2muse_combined.musicxml"

    assert Path(mscx_path).name == "pdf2muse_combined.mscx"



@patch("pdf2muse.ui.ensure_checkpoints")
@patch("pdf2muse.ui.join_musicxml_files")
@patch("pdf2muse.ui.convert_to_musescore_format")
@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_pdf_prefers_gradio_file_path(
    mock_pipeline_class,
    mock_msc_convert,
    mock_join,
    mock_checkpoints,
    tmp_path,
):
    """Newer Gradio FileData objects expose temp file paths via .path."""
    pdf = tmp_path / "uploaded.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf data")
    file_data = SimpleNamespace(path=str(pdf), name="original-filename.pdf")

    mock_join.side_effect = lambda _dir, path: Path(path).write_text("<score></score>")
    mock_msc_convert.side_effect = lambda xml, mscx, musescore_path=None: Path(
        mscx
    ).write_text("<mscx></mscx>")

    status, xml_path, mscx_path, _skeleton, _btn = _final_result(
        convert_pdf(file_data)
    )

    assert "conversion complete" in status.lower()
    assert xml_path is not None
    assert mscx_path is not None
    assert mock_pipeline_class.call_args.kwargs["pdf_path"] == str(pdf)





@patch("pdf2muse.ui.ensure_checkpoints")

@patch("pdf2muse.ui.join_musicxml_files")

@patch("pdf2muse.ui.convert_to_musescore_format")

@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)

def test_convert_pdf_yields_progress(

    mock_pipeline_class,

    mock_msc_convert,

    mock_join,

    mock_checkpoints,

    mock_pdf,

):

    """Conversion should emit intermediate loading statuses."""

    mock_join.side_effect = lambda _dir, path: Path(path).write_text("<score></score>")

    mock_msc_convert.side_effect = lambda xml, mscx, musescore_path=None: Path(

        mscx

    ).write_text("<mscx></mscx>")



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





@patch("pdf2muse.ui.ensure_checkpoints")

@patch("pdf2muse.ui.join_musicxml_files")

@patch("pdf2muse.ui.convert_to_musescore_format")

@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)

def test_convert_batch_pdfs_success(

    mock_pipeline_class,

    mock_msc_convert,

    mock_join,

    mock_checkpoints,

    mock_pdf,

):

    """Test successful batch conversion of multiple PDFs in UI."""

    mock_join.side_effect = lambda _dir, path: Path(path).write_text("<score></score>")

    mock_msc_convert.side_effect = lambda xml, mscx, musescore_path=None: Path(

        mscx

    ).write_text("<mscx></mscx>")



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



@patch("pdf2muse.ui.ensure_checkpoints")
@patch("pdf2muse.ui.join_musicxml_files")
@patch("pdf2muse.ui.convert_to_musescore_format")
@patch("pdf2muse.ui.PDF2MusePipeline", side_effect=make_pipeline_mock)
def test_convert_batch_pdfs_prefers_gradio_file_path(
    mock_pipeline_class,
    mock_msc_convert,
    mock_join,
    mock_checkpoints,
    tmp_path,
):
    """Batch conversion should use Gradio FileData.path when present."""
    pdf = tmp_path / "batch-upload.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock pdf data")
    file_data = SimpleNamespace(path=str(pdf), name="original-batch-name.pdf")

    mock_join.side_effect = lambda _dir, path: Path(path).write_text("<score></score>")
    mock_msc_convert.side_effect = lambda xml, mscx, musescore_path=None: Path(
        mscx
    ).write_text("<mscx></mscx>")

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





def test_create_interface():

    """Test Gradio Blocks instantiation finishes correctly."""

    interface = create_interface(default_musescore="/mock/msc")

    assert isinstance(interface, gr.Blocks)

    assert interface.title == "PDF2Muse - Sheet Music Converter"

    assert interface.css is not None

    assert "--color-primary: #EA580C" in interface.css


