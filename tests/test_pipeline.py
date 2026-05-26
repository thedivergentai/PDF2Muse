"""Comprehensive tests for PDF2Muse pipeline."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest
import xml.etree.ElementTree as ET

from pdf2muse.core import PDF2MusePipeline
from pdf2muse.oemer_utils import download_checkpoints, ensure_checkpoints
from pdf2muse.musicxml import join_musicxml_files, find_musescore_binary, convert_to_musescore_format


def test_pipeline_init_fails_if_pdf_missing(tmp_path):
    """Test pipeline raises FileNotFoundError if PDF is missing."""
    missing_pdf = tmp_path / "non_existent.pdf"
    with pytest.raises(FileNotFoundError):
        PDF2MusePipeline(pdf_path=str(missing_pdf))


def test_pipeline_init_succeeds(sample_pdf, tmp_path):
    """Test pipeline initialization resolves paths correctly."""
    output_dir = tmp_path / "output"
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), output_dir=str(output_dir))
    assert pipeline.pdf_path == sample_pdf.resolve()
    assert pipeline.output_dir == output_dir.resolve()
    assert output_dir.exists()


@patch("pdf2muse.oemer_utils.get_checkpoint_dir")
@patch("pdf2muse.oemer_utils.requests.get")
def test_download_checkpoints_mapping(mock_get, mock_get_chk_dir, tmp_path):
    """Test checkpoint downloader downloads files and maps them to correct internal names."""
    # Set up mock directories
    chk_dir = tmp_path / "checkpoints"
    chk_dir.mkdir()
    mock_get_chk_dir.return_value = chk_dir

    # Mock requests response
    mock_response = MagicMock()
    mock_response.headers = {"content-length": "10"}
    mock_response.iter_content.return_value = [b"modeldata"]
    mock_get.return_value = mock_response

    # Run downloader
    download_checkpoints(force=True)

    # Assert requests.get was called for the raw remote file names
    calls = [call[0][0] for call in mock_get.call_args_list]
    assert any("1st_model.onnx" in c for c in calls)
    assert any("1st_weights.h5" in c for c in calls)
    assert any("2nd_model.onnx" in c for c in calls)
    assert any("2nd_weights.h5" in c for c in calls)

    # Assert files are saved with correct internal mapped names (without prefixes)
    assert (chk_dir / "unet_big" / "model.onnx").exists()
    assert (chk_dir / "unet_big" / "weights.h5").exists()
    assert (chk_dir / "seg_net" / "model.onnx").exists()
    assert (chk_dir / "seg_net" / "weights.h5").exists()


@patch("pdf2muse.oemer_utils.get_checkpoint_dir")
@patch("pdf2muse.oemer_utils.download_checkpoints")
def test_ensure_checkpoints_downloads_if_missing(mock_download, mock_get_chk_dir, tmp_path):
    """Test ensure_checkpoints triggers download if files do not exist."""
    chk_dir = tmp_path / "checkpoints"
    mock_get_chk_dir.return_value = chk_dir

    # Should call download_checkpoints because critical files are missing
    ensure_checkpoints()
    mock_download.assert_called_once()


@patch("pdf2muse.oemer_utils.get_checkpoint_dir")
@patch("pdf2muse.oemer_utils.download_checkpoints")
def test_ensure_checkpoints_skips_if_present(mock_download, mock_get_chk_dir, tmp_path):
    """Test ensure_checkpoints skips download if all files are present."""
    chk_dir = tmp_path / "checkpoints"
    (chk_dir / "unet_big").mkdir(parents=True)
    (chk_dir / "seg_net").mkdir(parents=True)
    (chk_dir / "unet_big" / "model.onnx").write_text("data")
    (chk_dir / "unet_big" / "weights.h5").write_text("data")
    (chk_dir / "seg_net" / "model.onnx").write_text("data")
    (chk_dir / "seg_net" / "weights.h5").write_text("data")
    
    mock_get_chk_dir.return_value = chk_dir

    ensure_checkpoints()
    mock_download.assert_not_called()


@patch("pdf2muse.musicxml.shutil.which")
def test_find_musescore_binary_via_path(mock_which):
    """Test finding MuseScore binary through system PATH."""
    mock_which.side_effect = lambda cmd: Path(f"/usr/bin/{cmd}") if cmd == "MuseScore4" else None
    
    binary = find_musescore_binary()
    assert binary == Path("/usr/bin/MuseScore4")


@patch("pdf2muse.musicxml.shutil.which")
@patch("pdf2muse.musicxml.Path.exists")
def test_find_musescore_binary_via_common_paths(mock_exists, mock_which):
    """Test finding MuseScore binary through common Windows pathways if not in PATH."""
    mock_which.return_value = None
    mock_exists.return_value = True  # Instantly match the first candidate path
    
    # Mock OS to be Windows and let Program Files path exist
    with patch("pdf2muse.musicxml.os.name", "nt"):
        binary = find_musescore_binary()
        assert "MuseScore4.exe" in str(binary)


@patch("pdf2muse.musicxml.find_musescore_binary")
@patch("pdf2muse.musicxml.subprocess.run")
def test_convert_to_musescore_format_success(mock_sub_run, mock_find_binary, tmp_path):
    """Test successful MuseScore CLI conversion."""
    input_file = tmp_path / "input.musicxml"
    input_file.write_text("<score-partwise></score-partwise>")
    output_file = tmp_path / "output.mscx"
    
    mock_find_binary.return_value = Path("/mock/path/mscore")
    
    convert_to_musescore_format(input_file, output_file)
    
    # str(Path) converts paths correctly based on platform
    mock_sub_run.assert_called_once_with(
        [str(Path("/mock/path/mscore")), "-o", str(output_file), str(input_file)],
        check=True,
        capture_output=True,
        text=True,
    )


@patch("pdf2muse.musicxml.find_musescore_binary")
def test_convert_to_musescore_format_fails_if_binary_missing(mock_find_binary, tmp_path):
    """Test conversion raises error if MuseScore is missing."""
    input_file = tmp_path / "input.musicxml"
    input_file.write_text("<score-partwise></score-partwise>")
    output_file = tmp_path / "output.mscx"
    
    mock_find_binary.return_value = None
    
    with pytest.raises(RuntimeError, match="MuseScore executable not found"):
        convert_to_musescore_format(input_file, output_file)


def test_join_musicxml_files(tmp_path, mock_xml_content):
    """Test joining multiple MusicXML files by appending measures."""
    input_dir = tmp_path / "input_xmls"
    input_dir.mkdir()
    
    # Create two identical MusicXML files
    (input_dir / "001.musicxml").write_text(mock_xml_content)
    (input_dir / "002.musicxml").write_text(mock_xml_content)
    
    output_file = tmp_path / "combined.musicxml"
    
    join_musicxml_files(input_dir, output_file)
    
    # Verify file was written and parsing it succeeds
    assert output_file.exists()
    tree = ET.parse(str(output_file))
    root = tree.getroot()
    
    # Verify both measures exist in the combined part
    part = root.find("part")
    measures = part.findall("measure")
    assert len(measures) == 2


@patch("pypdfium2.PdfDocument")
def test_pdf_to_png(mock_pdf_doc, sample_pdf, tmp_path):
    """Test converting PDF pages to PNG using pypdfium2."""
    output_dir = tmp_path / "images"
    output_dir.mkdir()
    
    # Mock the converted PIL images
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_bitmap = MagicMock()
    mock_pil = MagicMock()
    
    mock_pdf_doc.return_value = mock_pdf
    mock_pdf.__len__.return_value = 2
    mock_pdf.__getitem__.side_effect = [mock_page, mock_page]
    mock_page.render.return_value = mock_bitmap
    mock_bitmap.to_pil.return_value = mock_pil
    
    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf)
    )
    png_files = pipeline.pdf_to_png(output_dir)
    
    # Assert PNGs are saved
    assert len(png_files) == 2
    assert mock_pil.save.call_count == 2


@patch("pdf2muse.core.subprocess.run")
def test_process_image_with_oemer(mock_sub_run, sample_pdf, mock_image, tmp_path):
    """Test executing oemer as a python module subprocess inside core pipeline."""
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    
    # Mock oemer generating files
    def side_effect(*args, **kwargs):
        generated_file = musicxml_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text("<score></score>")
        return MagicMock(stdout="Success")
    mock_sub_run.side_effect = side_effect
    
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True)
    xml_path = pipeline.process_image_with_oemer(mock_image, musicxml_dir)
    
    # Assert correct command executing oemer as a module via python executable
    mock_sub_run.assert_called_once_with(
        [sys.executable, "-W", "ignore", "-m", "oemer.ete", str(mock_image)],
        cwd=str(musicxml_dir),
        env=ANY,
        check=True,
        capture_output=True,
        text=True,
    )
    
    assert xml_path == musicxml_dir / "page_000.musicxml"
    assert xml_path.exists()


@patch("pdf2muse.core.ensure_checkpoints")
@patch("pdf2muse.core.PDF2MusePipeline.pdf_to_png")
@patch("pdf2muse.core.PDF2MusePipeline.process_image_with_oemer")
@patch("pdf2muse.core.join_musicxml_files")
@patch("pdf2muse.core.convert_to_musescore_format")
def test_pipeline_run_success(
    mock_convert_ms,
    mock_join,
    mock_process_oemer,
    mock_pdf_to_png,
    mock_ensure,
    sample_pdf,
    tmp_path,
):
    """Test full pipeline run success with MuseScore conversion."""
    output_dir = tmp_path / "output"
    
    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        output_dir=str(output_dir),
        musescore_path="/mock/mscore",
    )
    
    # Setup mocks
    png_path = tmp_path / "page_000.png"
    mock_pdf_to_png.return_value = [png_path]
    
    xml_path = tmp_path / "page_000.musicxml"
    mock_process_oemer.return_value = xml_path
    
    # Run pipeline
    result = pipeline.run()
    
    # Check assertions
    mock_ensure.assert_called_once()
    mock_pdf_to_png.assert_called_once()
    mock_process_oemer.assert_called_once_with(png_path, ANY)
    mock_join.assert_called_once()
    mock_convert_ms.assert_called_once_with(
        output_dir / "combined.musicxml",
        output_dir / "combined.mscx",
        musescore_path=Path("/mock/mscore").resolve(),
    )
    
    assert result == output_dir / "combined.mscx"


@patch("pdf2muse.core.ensure_checkpoints")
@patch("pdf2muse.core.PDF2MusePipeline.pdf_to_png")
@patch("pdf2muse.core.PDF2MusePipeline.process_image_with_oemer")
@patch("pdf2muse.core.join_musicxml_files")
@patch("pdf2muse.core.convert_to_musescore_format")
def test_pipeline_run_fallback_if_musescore_missing(
    mock_convert_ms,
    mock_join,
    mock_process_oemer,
    mock_pdf_to_png,
    mock_ensure,
    sample_pdf,
    tmp_path,
):
    """Test pipeline run graceful fallback to MusicXML if MuseScore is missing."""
    output_dir = tmp_path / "output"
    
    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        output_dir=str(output_dir),
    )
    
    # Setup mocks
    png_path = tmp_path / "page_000.png"
    mock_pdf_to_png.return_value = [png_path]
    
    xml_path = tmp_path / "page_000.musicxml"
    mock_process_oemer.return_value = xml_path
    
    # Fail MuseScore conversion
    mock_convert_ms.side_effect = RuntimeError("MuseScore not found")
    
    # Run pipeline
    result = pipeline.run()
    
    # Pipeline should not crash, and should return combined.musicxml path as fallback
    assert result == output_dir / "combined.musicxml"
