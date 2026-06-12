import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from backend.app.services.llm import LLMService

def test_llm_service_get_available_models():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3:latest"},
            {"name": "mistral:latest"}
        ]
    }
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        models = asyncio.run(LLMService.get_available_models())
        assert "llama3:latest" in models
        assert "mistral:latest" in models

def test_llm_service_rewrite_text_success():
    # Mock tags response
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"models": [{"name": "llama3:latest"}]}
    
    # Mock generate response
    mock_gen = MagicMock()
    mock_gen.status_code = 200
    mock_gen.json.return_value = {"response": "This is a clean, rewritten sentence."}
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = mock_tags
        mock_post.return_value = mock_gen
        
        rewritten = asyncio.run(LLMService.rewrite_text("This is a plagiarized sentence."))
        assert rewritten == "This is a clean, rewritten sentence."

def test_rewrite_endpoint(client: TestClient):
    # Mock tags and generate in one go for the route integration test
    mock_tags = MagicMock()
    mock_tags.status_code = 200
    mock_tags.json.return_value = {"models": [{"name": "llama3:latest"}]}
    
    mock_gen = MagicMock()
    mock_gen.status_code = 200
    mock_gen.json.return_value = {"response": "This is the rewritten version."}
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_get.return_value = mock_tags
        mock_post.return_value = mock_gen
        
        response = client.post(
            "/api/v1/rewrite",
            json={
                "text": "Original text segment to rewrite.",
                "tone": "creative"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["original_text"] == "Original text segment to rewrite."
        assert data["rewritten_text"] == "This is the rewritten version."
