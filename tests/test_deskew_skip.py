from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf2muse.core import PDF2MusePipeline


@patch("pdf2muse.core.page_needs_deskew", return_value=False)
@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_aligned_pages_disable_deskew(
    mock_run, _needs, sample_pdf, mock_image, tmp_path, mock_xml_content, monkeypatch
):
    monkeypatch.setenv("PDF2MUSE_SYSTEM_CROP", "0")
    musicxml_dir = tmp_path / "xmls"
    musicxml_dir.mkdir()

    def side_effect(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / f"{mock_image.stem}.musicxml").write_text(mock_xml_content, encoding="utf-8")
        return MagicMock(stdout="ok", stderr="")

    mock_run.side_effect = side_effect
    pipeline = PDF2MusePipeline(pdf_path=str(sample_pdf), deskew=True)
    xml_path, err = pipeline.process_image_with_oemer(mock_image, musicxml_dir)
    assert err is None
    assert xml_path is not None
    command = mock_run.call_args.args[0]
    assert "--without-deskew" in command
