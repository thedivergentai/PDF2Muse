"""Shared pytest fixtures and configurations."""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _default_cold_oemer_subprocess(monkeypatch):
    """Unit tests mock subprocess; keep warm worker off unless a test enables it."""

    monkeypatch.setenv("PDF2MUSE_OEMER_WORKER", "0")


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    """Create a temporary empty PDF file for unit tests."""
    pdf_file = tmp_path / "test_music.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock pdf data")
    return pdf_file


@pytest.fixture
def mock_image(tmp_path) -> Path:
    """Create a temporary PNG file for testing OMR."""
    png_file = tmp_path / "page_000.png"
    png_file.write_bytes(b"mock png data")
    return png_file


@pytest.fixture
def mock_xml_content() -> str:
    """Return a simple valid MusicXML structure."""
    return """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC
    "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
    "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note>
        <pitch>
          <step>C</step>
          <octave>4</octave>
        </pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


@pytest.fixture
def mock_musescore(monkeypatch, tmp_path):
    """Stub MuseScore CLI for benchmark scripts that render PDFs from MusicXML."""
    musescore = tmp_path / "MuseScore4.exe"
    musescore.write_text("", encoding="utf-8")

    def fake_render(musescore_path, musicxml_path, pdf_path):
        from PIL import Image

        Image.new("RGB", (200, 200), "white").save(pdf_path, "PDF")

    monkeypatch.setattr(
        "scripts.clean_typeset_benchmark.find_musescore_binary",
        lambda *_args, **_kwargs: musescore,
    )
    monkeypatch.setattr(
        "scripts.clean_typeset_benchmark._render_musicxml_to_pdf",
        fake_render,
    )
    return musescore
