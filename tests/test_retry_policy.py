from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf2muse.adapters.oemer import OemerAdapter
from pdf2muse.adapters.base import OmrOptions


def test_timeout_is_not_retryable():
    adapter = OemerAdapter(retries=True)
    nxt = adapter._attempts(OmrOptions())[1]
    assert adapter._should_continue_retries("timeout", nxt) is False


def test_unknown_failure_is_not_retryable():
    adapter = OemerAdapter(retries=True)
    nxt = adapter._attempts(OmrOptions())[1]
    assert adapter._should_continue_retries("something_weird", nxt) is False


@patch("pdf2muse.adapters.oemer.subprocess.run")
def test_valid_musicxml_with_notes_does_not_retry(
    mock_run, tmp_path: Path, mock_xml_content
):
    image = tmp_path / "page_000.png"
    image.write_bytes(b"mock png data")
    out = tmp_path / "xmls"
    out.mkdir()

    def side_effect(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / "page_000.musicxml").write_text(mock_xml_content, encoding="utf-8")
        return MagicMock(stdout="ok", stderr="")

    mock_run.side_effect = side_effect
    result = OemerAdapter(retries=True).recognize_page(
        image, out, OmrOptions(deskew=True, device="cpu")
    )
    assert result.musicxml_path is not None
    assert mock_run.call_count == 1
