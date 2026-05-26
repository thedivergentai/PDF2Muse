import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from pdf2muse.core import PDF2MusePipeline

@pytest.fixture
def mock_pdf_path(tmp_path):
    pdf_file = tmp_path / "test.pdf"
    pdf_file.touch()
    return pdf_file

@pytest.fixture
def pipeline(mock_pdf_path, tmp_path):
    return PDF2MusePipeline(str(mock_pdf_path), str(tmp_path / "output"))

def test_pipeline_initialization(pipeline, mock_pdf_path):
    assert pipeline.pdf_path == mock_pdf_path
    assert pipeline.output_dir.name == "output"
    assert pipeline.deskew is True

def test_pipeline_initialization_file_not_found():
    with pytest.raises(FileNotFoundError):
        PDF2MusePipeline("nonexistent.pdf")


@patch("pypdfium2.PdfDocument")
def test_pdf_to_png_pypdfium2(mock_pdf_doc, pipeline, tmp_path):
    # Mock PDF document and page
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_bitmap = MagicMock()
    mock_pil = MagicMock()
    
    mock_pdf_doc.return_value = mock_pdf
    mock_pdf.__len__.return_value = 1
    mock_pdf.__getitem__.return_value = mock_page
    mock_page.render.return_value = mock_bitmap
    mock_bitmap.to_pil.return_value = mock_pil
    
    # Run method
    images = pipeline.pdf_to_png(tmp_path)
    
    # Verify
    assert len(images) == 1
    assert images[0].name == "page_000.png"
    mock_pil.save.assert_called_once()
