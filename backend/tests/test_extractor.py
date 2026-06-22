import pytest
from unittest.mock import MagicMock, patch
from backend.app.config import settings
from backend.app.services.extractor import (
    DocumentExtractorService,
    FileSizeExceededError,
    UnsupportedFileTypeError,
    ExtractionError,
)

def test_extract_txt_utf8():
    content = "Hello world! This is a test.".encode("utf-8")
    result = DocumentExtractorService.extract_text("test.txt", content)
    assert result == "Hello world! This is a test."

def test_extract_txt_latin1():
    content = "Héllô wôrld!".encode("latin-1")
    result = DocumentExtractorService.extract_text("test.txt", content)
    assert "Héllô wôrld!" in result

def test_extract_docx(create_docx_bytes):
    paragraphs = ["First paragraph of docx.", "Second paragraph of docx."]
    content = create_docx_bytes(paragraphs)
    result = DocumentExtractorService.extract_text("test.docx", content)
    assert "First paragraph of docx." in result
    assert "Second paragraph of docx." in result

@patch("backend.app.services.extractor.PdfReader")
def test_extract_pdf_success(mock_pdf_reader_class):
    # Setup mock reader and pages
    mock_reader = MagicMock()
    mock_reader.is_encrypted = False
    
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Text on page 1."
    
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Text on page 2."
    
    mock_reader.pages = [mock_page1, mock_page2]
    mock_pdf_reader_class.return_value = mock_reader

    result = DocumentExtractorService.extract_text("test.pdf", b"mock_pdf_bytes")
    
    assert "Text on page 1." in result
    assert "Text on page 2." in result
    mock_pdf_reader_class.assert_called_once()

@patch("backend.app.services.extractor.PdfReader")
def test_extract_pdf_encrypted_fails(mock_pdf_reader_class):
    mock_reader = MagicMock()
    mock_reader.is_encrypted = True
    # Make decrypt throw an error simulating decryption failure
    mock_reader.decrypt.side_effect = Exception("Decryption failed")
    mock_pdf_reader_class.return_value = mock_reader

    with pytest.raises(ExtractionError, match="Encrypted or password-protected"):
        DocumentExtractorService.extract_text("test.pdf", b"mock_pdf_bytes")

def test_file_size_exceeded():
    old_size = settings.MAX_FILE_SIZE_MB
    settings.MAX_FILE_SIZE_MB = 0
    try:
        with pytest.raises(FileSizeExceededError):
            DocumentExtractorService.extract_text("test.txt", b"x")
    finally:
        settings.MAX_FILE_SIZE_MB = old_size


def test_unsupported_file_type():
    with pytest.raises(UnsupportedFileTypeError):
        DocumentExtractorService.extract_text("test.png", b"image data")
