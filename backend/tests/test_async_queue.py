import io
import pytest
from fastapi.testclient import TestClient
from backend.app.config import settings

def test_async_analyze_flow_txt(client: TestClient):
    # Prepare dummy txt content
    file_content = b"This is a sample document for testing the async Celery tasks."
    files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    
    # POST to upload/analyze
    response = client.post("/api/v1/analyze", files=files)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    
    job_id = data["job_id"]
    
    # GET status
    status_response = client.get(f"/api/v1/status/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["job_id"] == job_id
    assert status_data["status"] == "completed"
    assert "result" in status_data
    
    result = status_data["result"]
    assert result["filename"] == "test.txt"
    assert "text" in result
    assert "sentences" in result
    assert "analysis" in result
    assert result["char_count"] == len(file_content)

def test_async_analyze_unsupported_type(client: TestClient):
    files = {"file": ("test.png", io.BytesIO(b"dummy image data"), "image/png")}
    response = client.post("/api/v1/analyze", files=files)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]

def test_async_analyze_large_file(client: TestClient):
    # Set size limit to 0MB to force error
    old_size = settings.MAX_FILE_SIZE_MB
    settings.MAX_FILE_SIZE_MB = 0
    try:
        files = {"file": ("test.txt", io.BytesIO(b"some content"), "text/plain")}
        response = client.post("/api/v1/analyze", files=files)
        assert response.status_code == 413
        assert "File size exceeds limit" in response.json()["detail"]
    finally:
        settings.MAX_FILE_SIZE_MB = old_size

def test_invalid_job_status(client: TestClient):
    response = client.get("/api/v1/status/non-existent-job-uuid-12345")
    assert response.status_code == 200
    # Celery result backend returns PENDING for unknown IDs
    assert response.json()["status"] == "pending"
