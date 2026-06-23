import io
import pytest
from pathlib import Path
from docx import Document

# Override settings to use a test database and index BEFORE importing app or other components
from app.config import settings
settings.POSTGRES_DB = "test_lemma"
settings.CELERY_ALWAYS_EAGER = True
settings.ENABLE_ONLINE_RETRIEVAL = False

from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def clean_test_db_and_index():
    """Ensures test database tables and ES index are initialized and cleaned up."""
    from app.services.database import DatabaseService
    from app.services.elasticsearch_client import get_es_client, initialize_es
    
    # Initialize DB (creates extension, tables, HNSW index)
    try:
        DatabaseService.initialize_db()
    except Exception as e:
        pytest.skip(f"PostgreSQL connection failed: {e}. Make sure the Docker services are running.")
        
    # Initialize Elasticsearch index
    try:
        initialize_es()
    except Exception as e:
        pytest.skip(f"Elasticsearch connection failed: {e}. Make sure the Docker services are running.")
        
    # Truncate tables before tests
    with DatabaseService.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE sentences, documents CASCADE;")
        conn.commit()
        
    # Delete and recreate index for clean test state
    es = get_es_client()
    index_name = "reference_sentences"
    try:
        if es.indices.exists(index=index_name):
            es.indices.delete(index=index_name)
        initialize_es()
    except Exception as e:
        pytest.skip(f"Elasticsearch re-initialization failed: {e}")
    
    yield
    
    # Teardown: truncate tables again
    try:
        with DatabaseService.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE sentences, documents CASCADE;")
            conn.commit()
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
