"""Comprehensive tests for PDF2Muse pipeline."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest
import xml.etree.ElementTree as ET

from pdf2muse.core import PDF2MusePipeline
from pdf2muse.oemer_utils import OEMER_CHECKPOINT_ENV
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
    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        output_dir=str(output_dir),
        render_dpi=300,
    )
    assert pipeline.pdf_path == sample_pdf.resolve()
    assert pipeline.output_dir == output_dir.resolve()
    assert pipeline.render_dpi == 300
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

    def _write_output(*_args, **_kwargs):
        output_file.write_text("<mscx/>", encoding="utf-8")
        return MagicMock(stdout="", stderr="")

    mock_sub_run.side_effect = _write_output

    convert_to_musescore_format(input_file, output_file)

    # str(Path) converts paths correctly based on platform
    mock_sub_run.assert_called_once_with(
        [str(Path("/mock/path/mscore")), "-f", "-o", str(output_file), str(input_file)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output_file.exists()
    assert output_file.stat().st_size > 0


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
    
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), render_dpi=200)
    png_files = pipeline.pdf_to_png(output_dir)
    
    # Assert PNGs are saved
    assert len(png_files) == 2
    mock_page.render.assert_called_with(scale=200 / 72)
    assert mock_pil.save.call_count == 2


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer(
    mock_sub_run, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    """Test executing oemer in a per-page subdirectory (concurrency-safe)."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        generated_file = page_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text(mock_xml_content)
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True, oemer_device="cpu")
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    mock_sub_run.assert_called_once_with(
        [sys.executable, "-W", "ignore", "-m", "pdf2muse._oemer_cpu", str(mock_image)],
        cwd=str(page_dir),
        env=ANY,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )

    assert err is None
    assert xml_path == musicxml_dir / "page_000.musicxml"
    assert xml_path.exists()
    assert mock_sub_run.call_args.kwargs["env"]["PDF2MUSE_OEMER_DIAGNOSTICS"] == "1"
    assert mock_sub_run.call_args.kwargs["env"]["OMP_NUM_THREADS"] == "1"


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_can_use_cuda_onnx_path(
    mock_sub_run, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    """CUDA mode should avoid the CPU wrapper and let oemer use ONNX providers."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        generated_file = page_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text(mock_xml_content)
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), oemer_device="cuda")
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    mock_sub_run.assert_called_once_with(
        [sys.executable, "-W", "ignore", "-m", "pdf2muse._oemer_cuda", str(mock_image)],
        cwd=str(page_dir),
        env=ANY,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    env = mock_sub_run.call_args.kwargs["env"]
    assert env["PDF2MUSE_OEMER_DIAGNOSTICS"] == "1"
    assert env["ORT_LOG_SEVERITY_LEVEL"] == "3"
    assert int(env["OMP_NUM_THREADS"]) >= 2
    assert err is None
    assert xml_path.exists()


def test_pipeline_auto_device_prefers_cuda_when_available(sample_pdf, monkeypatch):
    monkeypatch.setattr("pdf2muse.core.resolve_oemer_device", lambda device="auto": "cuda")
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), oemer_device="auto")
    assert pipeline.oemer_device == "cuda"


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_rejects_malformed_musicxml(
    mock_sub_run, sample_pdf, mock_image, tmp_path, monkeypatch
):
    """Malformed page MusicXML should be reported before merge."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        generated_file = page_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text("<score-partwise>", encoding="utf-8")
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True, oemer_device="cpu")
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert xml_path is None
    assert "Invalid MusicXML" in err


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_reports_timeout(
    mock_sub_run, sample_pdf, mock_image, tmp_path, monkeypatch
):
    """Long-running OMR calls should become reportable sample failures."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    mock_sub_run.side_effect = subprocess.TimeoutExpired(
        cmd=["oemer"],
        timeout=5,
        output="PDF2MUSE_DIAG inference_start model=unet_big",
        stderr="",
    )

    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        oemer_timeout_seconds=5,
    )
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert xml_path is None
    assert "timed out after 5 seconds" in err
    assert "PDF2MUSE_DIAG inference_start model=unet_big" in err


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_retries_dewarp_without_deskew(
    mock_sub_run, sample_pdf, mock_image, tmp_path, monkeypatch
):
    """Dewarp empty-grid failures should retry with deskew disabled."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    first_dir = musicxml_dir / mock_image.stem
    retry_dir = first_dir / "quality_no_deskew"

    def side_effect(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        if cwd == first_dir:
            raise subprocess.CalledProcessError(
                1,
                kwargs["args"] if "args" in kwargs else args[0],
                output="",
                stderr="PDF2MUSE_OEMER_STAGE dewarp_empty_grid_groups",
            )
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / f"{mock_image.stem}.musicxml").write_text(
            "<score-partwise><part><measure><note><pitch /></note></measure></part></score-partwise>",
            encoding="utf-8",
        )
        return MagicMock(stdout="Success", stderr="")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True)
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert err is None
    assert xml_path is not None and xml_path.exists()
    assert mock_sub_run.call_count == 2
    assert "--without-deskew" in mock_sub_run.call_args_list[1].args[0]
    attempts = pipeline._page_attempts[mock_image.stem]
    assert attempts[0]["failure_class"] == "dewarp_empty_grid_groups"
    assert attempts[1]["status"] == "succeeded"


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_keeps_attempt_artifacts(
    mock_sub_run, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    """Artifact retention should preserve page image and full attempt output."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    output_dir = tmp_path / "output"
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / f"{mock_image.stem}.musicxml").write_text(mock_xml_content, encoding="utf-8")
        return MagicMock(stdout="full stdout", stderr="full stderr")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        output_dir=str(output_dir),
        keep_page_artifacts=True,
    )
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert err is None
    assert xml_path is not None
    artifact_dir = output_dir / "pages" / mock_image.stem / "quality"
    assert (output_dir / "pages" / mock_image.stem / mock_image.name).exists()
    assert (artifact_dir / "stdout.txt").read_text(encoding="utf-8") == "full stdout"
    assert (artifact_dir / "stderr.txt").read_text(encoding="utf-8") == "full stderr"
    metadata = json.loads((artifact_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "succeeded"
    assert page_dir.exists()


def test_musicxml_structure_quality_metrics(tmp_path):
    """Generated MusicXML reports coarse structural counts."""
    from pdf2muse.musicxml import analyze_musicxml_structure

    xml_path = tmp_path / "sample.musicxml"
    xml_path.write_text(
        """
<score-partwise>
  <part id="P1">
    <measure number="1">
      <note><pitch><step>C</step><octave>4</octave></pitch></note>
      <note><rest /></note>
    </measure>
  </part>
</score-partwise>
""".strip(),
        encoding="utf-8",
    )

    report = analyze_musicxml_structure(xml_path)

    assert report.parse_ok is True
    assert report.root == "score-partwise"
    assert report.parts == 1
    assert report.measures == 1
    assert report.notes == 2
    assert report.pitched_notes == 1
    assert report.rests == 1


def test_oemer_failure_classifier_handles_real_world_postprocessing_crashes():
    """Known oemer post-processing tracebacks should become stable categories."""
    from pdf2muse._oemer_common import classify_oemer_failure

    assert (
        classify_oemer_failure(
            "",
            "filter_line_peaks\nIndexError: index 0 is out of bounds for axis 0",
        )
        == "staffline_empty_peaks"
    )
    assert (
        classify_oemer_failure(
            "",
            "symbol_extraction.py\nparse_clefs_keys\nIndexError: too many indices",
        )
        == "symbol_extraction_empty_candidates"
    )


@patch("pdf2muse.adapters.oemer.subprocess.Popen")
def test_process_image_with_oemer_stream_mode_classifies_captured_output(
    mock_popen, sample_pdf, mock_image, tmp_path, monkeypatch
):
    """Streaming mode must tee and still classify failure_class from captured stderr."""
    monkeypatch.setenv("PDF2MUSE_OEMER_STREAM", "1")
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()

    fail_msg = (
        "PDF2MUSE_OEMER_STAGE symbol_extraction_empty_candidates: "
        "oemer symbol extraction found no bbox candidates\n"
    )

    def _line_stream(lines: list[str]):
        stream = MagicMock()
        stream.readline.side_effect = list(lines) + [""]
        return stream

    def popen_factory(*_args, **_kwargs):
        proc = MagicMock()
        proc.stdout = _line_stream(["Extracting symbols\n"])
        proc.stderr = _line_stream([fail_msg])
        proc.wait.return_value = 1
        return proc

    mock_popen.side_effect = popen_factory

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), oemer_device="cpu")
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert xml_path is None
    assert "symbol_extraction_empty_candidates" in err
    attempts = pipeline._page_attempts[mock_image.stem]
    assert attempts[0]["failure_class"] == "symbol_extraction_empty_candidates"
    assert all(
        attempt["failure_class"] == "symbol_extraction_empty_candidates"
        for attempt in attempts
    )


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_uses_tf_entrypoint_when_requested(
    mock_sub_run, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    """TensorFlow mode should keep using oemer's native --use-tf path."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        generated_file = page_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text(mock_xml_content)
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf), deskew=True, use_tf=True, oemer_device="cpu"
    )
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    mock_sub_run.assert_called_once_with(
        [sys.executable, "-W", "ignore", "-m", "oemer.ete", str(mock_image), "--use-tf"],
        cwd=str(page_dir),
        env=ANY,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )

    assert err is None
    assert xml_path == musicxml_dir / "page_000.musicxml"
    assert xml_path.exists()


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_isolated_page_dirs(
    mock_sub_run, sample_pdf, tmp_path, mock_xml_content, monkeypatch
):
    """Concurrent workers must use separate cwd per page stem."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()
    page_a = tmp_path / "page_000.png"
    page_b = tmp_path / "page_001.png"
    page_a.write_bytes(b"png-a")
    page_b.write_bytes(b"png-b")
    cwds: list[str] = []

    def side_effect(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        cwds.append(str(cwd))
        cwd.mkdir(parents=True, exist_ok=True)
        stem = cwd.name
        (cwd / f"{stem}.musicxml").write_text(mock_xml_content)
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True)
    path_a, err_a = pipeline.process_image_with_oemer(page_a, musicxml_dir)
    path_b, err_b = pipeline.process_image_with_oemer(page_b, musicxml_dir)

    assert err_a is None and err_b is None
    assert path_a == musicxml_dir / "page_000.musicxml"
    assert path_b == musicxml_dir / "page_001.musicxml"
    assert cwds == [str(musicxml_dir / "page_000"), str(musicxml_dir / "page_001")]
    assert path_a != path_b


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_process_image_with_oemer_passes_checkpoint_override(
    mock_sub_run, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    """Custom checkpoint experiments should not mutate package checkpoints."""
    monkeypatch.delenv("PDF2MUSE_OEMER_STREAM", raising=False)
    musicxml_dir = tmp_path / "xmls"
    checkpoint_dir = tmp_path / "checkpoints"
    musicxml_dir.mkdir()
    page_dir = musicxml_dir / mock_image.stem

    def side_effect(*args, **kwargs):
        page_dir.mkdir(parents=True, exist_ok=True)
        generated_file = page_dir / f"{mock_image.stem}.musicxml"
        generated_file.write_text(mock_xml_content)
        return MagicMock(stdout="Success")

    mock_sub_run.side_effect = side_effect

    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        checkpoint_dir=str(checkpoint_dir),
    )
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)

    assert err is None
    assert xml_path is not None
    assert mock_sub_run.call_args.kwargs["env"][OEMER_CHECKPOINT_ENV] == str(
        checkpoint_dir.resolve()
    )


def test_pipeline_accepts_legato_backend(sample_pdf, tmp_path):
    from pdf2muse.adapters import LegatoAdapter

    pipeline = PDF2MusePipeline(
        pdf_path=str(sample_pdf),
        output_dir=str(tmp_path / "out"),
        model_backend="legato-experimental",
    )
    assert pipeline.model_backend.name == "legato-experimental"
    assert isinstance(pipeline._adapter, LegatoAdapter)


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
    xml_path.write_text("<score-partwise></score-partwise>", encoding="utf-8")
    mock_process_oemer.return_value = (xml_path, None)

    def join_side_effect(musicxml_dir, combined_path, *, strict=False):
        Path(combined_path).write_text(
            '<?xml version="1.0"?><score-partwise version="3.1">'
            "<part-list><score-part id=\"P1\"><part-name>P</part-name></score-part></part-list>"
            "<part id=\"P1\"><measure number=\"1\"><note><rest/><duration>1</duration></note></measure></part>"
            "</score-partwise>",
            encoding="utf-8",
        )
        return MagicMock(
            files_seen=1,
            files_joined=1,
            files_skipped=0,
            skipped_files=[],
            warnings=[],
            engine="copy",
            failure_class=None,
        )

    mock_join.side_effect = join_side_effect

    def convert_side_effect(combined, mscx, *, musescore_path=None):
        Path(mscx).write_text("<mscx/>", encoding="utf-8")

    mock_convert_ms.side_effect = convert_side_effect

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
    report = json.loads((output_dir / "conversion_report.json").read_text(encoding="utf-8"))
    assert report["render_dpi"] == 360
    assert report["model_backend"]["name"] == "oemer-stock"
    assert report["pages"][0]["status"] == "completed"
    assert Path(report["pages"][0]["musicxml_path"]).exists()
    assert output_dir in Path(report["pages"][0]["musicxml_path"]).parents
    assert report["final_musicxml"]["status"] in {"ok", "missing"}


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
    xml_path.write_text(
        '<?xml version="1.0"?><score-partwise version="3.1">'
        "<part-list><score-part id=\"P1\"><part-name>P</part-name></score-part></part-list>"
        "<part id=\"P1\"><measure number=\"1\"><note><rest/><duration>1</duration></note></measure></part>"
        "</score-partwise>",
        encoding="utf-8",
    )
    mock_process_oemer.return_value = (xml_path, None)

    def join_side_effect(musicxml_dir, combined_path, *, strict=False):
        Path(combined_path).write_text(xml_path.read_text(encoding="utf-8"), encoding="utf-8")
        return MagicMock(
            files_seen=1,
            files_joined=1,
            files_skipped=0,
            skipped_files=[],
            warnings=[],
            engine="copy",
            failure_class=None,
        )

    mock_join.side_effect = join_side_effect

    # Fail MuseScore conversion
    mock_convert_ms.side_effect = RuntimeError("MuseScore not found")

    # Run pipeline
    result = pipeline.run()

    # Pipeline should not crash, and should return combined.musicxml path as fallback
    assert result == output_dir / "combined.musicxml"


@patch("pdf2muse.core.ensure_checkpoints")
@patch("pdf2muse.core.PDF2MusePipeline.pdf_to_png")
@patch("pdf2muse.core.PDF2MusePipeline.process_image_with_oemer")
@patch("pdf2muse.core.join_musicxml_files")
def test_pipeline_run_writes_report_if_join_fails(
    mock_join,
    mock_process_oemer,
    mock_pdf_to_png,
    mock_ensure,
    sample_pdf,
    tmp_path,
):
    output_dir = tmp_path / "output"
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), output_dir=str(output_dir))
    png_path = tmp_path / "page_000.png"
    xml_path = tmp_path / "page_000.musicxml"
    xml_path.write_text("<score-partwise></score-partwise>", encoding="utf-8")
    mock_pdf_to_png.return_value = [png_path]
    mock_process_oemer.return_value = (xml_path, None)
    mock_join.side_effect = ValueError("join exploded")

    with pytest.raises(ValueError, match="join exploded"):
        pipeline.run()

    report = json.loads((output_dir / "conversion_report.json").read_text(encoding="utf-8"))
    assert report["join"]["status"] == "failed"
    assert "join exploded" in report["join"]["error"]
