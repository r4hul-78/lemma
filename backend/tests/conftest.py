import io
import pytest
from pathlib import Path
from docx import Document

# Override settings to use a test database and index BEFORE importing app or other components
from backend.app.config import settings
TEST_DB_PATH = settings.BASE_DIR / "data" / "test_lemma.db"
TEST_INDEX_PATH = settings.BASE_DIR / "data" / "test_lemma_vectors.index"

settings.SQLITE_DB_PATH = TEST_DB_PATH
settings.FAISS_INDEX_PATH = TEST_INDEX_PATH
settings.CELERY_ALWAYS_EAGER = True

from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture(scope="session", autouse=True)
def clean_test_db_and_index():
    """Ensures test database and index files are cleaned up before and after the test session."""
    # Setup: remove any existing test database or index files
    for p in (TEST_DB_PATH, TEST_INDEX_PATH):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
                
    yield
    
    # Teardown: clean up test database and index files
    for p in (TEST_DB_PATH, TEST_INDEX_PATH):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

@pytest.fixture(scope="module")
def client():
    """Provides a FastAPI TestClient."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_text():
    """Provides a standard multi-sentence plain text string."""
    return (
        "This is the first sentence. It has some text. "
        "Here is the second sentence, which is longer and contains more details! "
        "And this is the third sentence: does it work correctly?"
    )

@pytest.fixture
def create_docx_bytes():
    """Fixture that returns a function to generate DOCX bytes on-the-fly."""
    def _create(paragraphs: list[str]) -> bytes:
        doc = Document()
        for p in paragraphs:
            doc.add_paragraph(p)
        
        doc_io = io.BytesIO()
        doc.save(doc_io)
        return doc_io.getvalue()
    return _create
