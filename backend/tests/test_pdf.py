import io
import pytest
from fastapi.testclient import TestClient
from backend.app.services.pdf_generator import PDFGeneratorService

def test_pdf_generator_service_compiles():
    # Setup dummy completed analysis result payload
    dummy_result = {
        "filename": "academic_paper.txt",
        "text": "This is an academic paper about machine learning and climate action. Transitioning from fossil fuels is key.",
        "char_count": 105,
        "sentence_count": 2,
        "sentences": [
            {
                "text": "This is an academic paper about machine learning and climate action.",
                "start_char": 0,
                "end_char": 68
            },
            {
                "text": "Transitioning from fossil fuels is key.",
                "start_char": 69,
                "end_char": 108
            }
        ],
        "analysis": {
            "plagiarism_score": 0.5,
            "total_sentences": 2,
            "plagiarized_sentences_count": 1,
            "lexical_matches_count": 1,
            "semantic_matches_count": 0,
            "matches": [
                {
                    "query_sentence": {
                        "text": "Transitioning from fossil fuels is key.",
                        "start_char": 69,
                        "end_char": 108
                    },
                    "matched_sentence": {
                        "text": "Transitioning from fossil fuels to renewable energy sources is key.",
                        "doc_id": "ref_climate_change",
                        "doc_title": "The Decisive Decade: Climate Action and Clean Energy",
                        "doc_author": "Marcus Thorne",
                        "doc_source": "Environmental Science Review, 2025"
                    },
                    "match_type": "lexical",
                    "score": 0.85,
                    "highlights": [
                        {
                            "start_char": 69,
                            "end_char": 100,
                            "text": "Transitioning from fossil fuels"
                        },
                        {
                            "start_char": 101,
                            "end_char": 108,
                            "text": "is key."
                        }
                    ]
                }
            ]
        }
    }
    
    # Generate report
    pdf_bytes = PDFGeneratorService.generate_report(dummy_result)
    
    # Assertions
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # Validate PDF magic header
    assert pdf_bytes.startswith(b"%PDF")


def test_download_report_endpoint_success(client: TestClient):
    # Upload and analyze document asynchronously (forces eager mode completion in test environment)
    file_content = b"This is the first sentence. Transitioning from fossil fuels to renewable energy sources is key."
    files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    
    # Trigger task
    response = client.post("/api/v1/analyze", files=files)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    
    # Fetch report PDF
    report_response = client.get(f"/api/v1/documents/report/{job_id}")
    assert report_response.status_code == 200
    assert report_response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in report_response.headers["content-disposition"]
    assert report_response.content.startswith(b"%PDF")


def test_download_report_endpoint_not_found_or_pending(client: TestClient):
    # Retrieve report for non-existent job UUID
    response = client.get("/api/v1/documents/report/invalid-job-uuid-12345")
    # PENDING/non-existent returns 400 because task is not SUCCESS
    assert response.status_code == 400
    assert "still in progress" in response.json()["detail"]
