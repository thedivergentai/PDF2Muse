"""Shared pytest fixtures and configurations."""

import pytest
from pathlib import Path


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
