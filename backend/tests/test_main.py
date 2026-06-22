import pytest
from backend.app.config import settings

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert b"<!DOCTYPE html>" in response.content

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    response_v1 = client.get(f"{settings.API_V1_STR}/health")
    assert response_v1.status_code == 200
    assert response_v1.json()["status"] == "ok"

def test_upload_txt_success(client):
    file_content = "This is sentence one. And sentence two is here."
    files = {"file": ("test_doc.txt", file_content, "text/plain")}
    
    response = client.post(
        f"{settings.API_V1_STR}/documents/upload",
        files=files
    )
    
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["filename"] == "test_doc.txt"
    assert json_data["text"] == file_content
    assert json_data["char_count"] == len(file_content)
    assert json_data["sentence_count"] == 2
    
    sentences = json_data["sentences"]
    assert len(sentences) == 2
    assert sentences[0]["text"] == "This is sentence one."
    assert sentences[0]["start_char"] == 0
    assert sentences[0]["end_char"] == 21
    
    assert sentences[1]["text"] == "And sentence two is here."
    assert sentences[1]["start_char"] == 22
    assert sentences[1]["end_char"] == 47

def test_upload_unsupported_type(client):
    files = {"file": ("test_doc.png", b"image bytes", "image/png")}
    response = client.post(
        f"{settings.API_V1_STR}/documents/upload",
        files=files
    )
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]

def test_upload_oversized_file(client):
    old_size = settings.MAX_FILE_SIZE_MB
    settings.MAX_FILE_SIZE_MB = 0
    try:
        files = {"file": ("huge_file.txt", b"x", "text/plain")}
        response = client.post(
            f"{settings.API_V1_STR}/documents/upload",
            files=files
        )
        assert response.status_code == 413
        assert "exceeds the maximum limit" in response.json()["detail"]
    finally:
        settings.MAX_FILE_SIZE_MB = old_size

