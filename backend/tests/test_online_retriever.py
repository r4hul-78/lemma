import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.online_retriever import OnlineRetrieverService
from app.services.database import DatabaseService
from app.services.elasticsearch_client import get_es_client

# Mock arXiv XML response
MOCK_ARXIV_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture, the Transformer, based solely on attention mechanisms.</summary>
    <author>
      <name>Ashish Vaswani</name>
    </author>
    <author>
      <name>Noam Shazeer</name>
    </author>
    <id>http://arxiv.org/abs/1706.03762v7</id>
  </entry>
</feed>
"""

# Mock Semantic Scholar JSON response
MOCK_SEMANTIC_SCHOLAR_JSON = {
    "data": [
        {
            "paperId": "a1b2c3d4e5f6",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers.",
            "authors": [
                {"name": "Jacob Devlin"},
                {"name": "Ming-Wei Chang"}
            ],
            "venue": "NAACL",
            "year": 2019
        }
    ]
}

def test_extract_search_queries():
    text = (
        "Deep learning is a subset of machine learning that is based on artificial neural networks. "
        "Historically, neural networks were limited in depth due to computational constraints. "
        "Today, modern transformer architectures solve these issues."
    )
    queries = OnlineRetrieverService.extract_search_queries(text, num_queries=3)
    assert len(queries) > 0
    # The queries should be sub-phrases of the text
    for q in queries:
        assert isinstance(q, str)
        assert len(q.split()) >= 1

@pytest.mark.anyio
@patch("httpx.AsyncClient.get")
async def test_fetch_arxiv_candidates(mock_get):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = MOCK_ARXIV_XML.encode("utf-8")
    mock_get.return_value = mock_response

    candidates = await OnlineRetrieverService.fetch_arxiv_candidates("attention mechanism", limit=1)
    
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand["doc_id"] == "arxiv_1706.03762"
    assert cand["title"] == "Attention Is All You Need"
    assert "Transformer" in cand["text"]
    assert cand["author"] == "Ashish Vaswani, Noam Shazeer"
    assert "arXiv Preprint" in cand["source"]

@pytest.mark.anyio
@patch("httpx.AsyncClient.get")
async def test_fetch_semantic_scholar_candidates(mock_get):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_SEMANTIC_SCHOLAR_JSON
    mock_get.return_value = mock_response

    candidates = await OnlineRetrieverService.fetch_semantic_scholar_candidates("bert", limit=1)
    
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand["doc_id"] == "semschol_a1b2c3d4e5f6"
    assert cand["title"] == "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
    assert "Bidirectional Encoder" in cand["text"]
    assert cand["author"] == "Jacob Devlin, Ming-Wei Chang"
    assert "NAACL, 2019" in cand["source"]

@pytest.mark.anyio
@patch("httpx.AsyncClient.get")
async def test_get_online_candidates_merged(mock_get):
    # Setup mock response
    mock_response_arxiv = MagicMock()
    mock_response_arxiv.status_code = 200
    mock_response_arxiv.content = MOCK_ARXIV_XML.encode("utf-8")
    
    mock_response_semsch = MagicMock()
    mock_response_semsch.status_code = 200
    mock_response_semsch.json.return_value = MOCK_SEMANTIC_SCHOLAR_JSON
    
    mock_get.side_effect = [mock_response_arxiv, mock_response_semsch]

    candidates = await OnlineRetrieverService.get_online_candidates(["transformer"], limit_per_query=1)
    
    assert len(candidates) == 2
    ids = [c["doc_id"] for c in candidates]
    assert "arxiv_1706.03762" in ids
    assert "semschol_a1b2c3d4e5f6" in ids

@pytest.mark.anyio
async def test_seed_and_prune_ephemeral_candidates():
    job_id = "testjob123"
    candidates = [
        {
            "doc_id": "test_doc_a",
            "title": "Ephemeral Candidate Paper A",
            "author": "Author A",
            "source": "Journal A",
            "text": "This is the first sentence of the abstract. This is the second sentence."
        }
    ]

    # Seed candidates
    await OnlineRetrieverService.seed_ephemeral_candidates(job_id, candidates)

    # Verify candidate document exists in PostgreSQL
    with DatabaseService.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, title FROM documents WHERE id = %s;", (f"job_{job_id}_test_doc_a",))
            row = cursor.fetchone()
            assert row is not None
            assert row[1] == "Ephemeral Candidate Paper A"

            # Verify sentences exist in PostgreSQL
            cursor.execute("SELECT COUNT(*) FROM sentences WHERE document_id = %s;", (f"job_{job_id}_test_doc_a",))
            count = cursor.fetchone()[0]
            assert count == 2

    # Verify sentences exist in Elasticsearch
    es = get_es_client()
    index_name = "reference_sentences"
    res = es.search(index=index_name, body={
        "query": {
            "prefix": {
                "document_id": f"job_{job_id}_"
            }
        }
    })
    assert res["hits"]["total"]["value"] == 2

    # Prune candidates
    OnlineRetrieverService.prune_cache(job_id)

    # Verify records deleted in PostgreSQL
    with DatabaseService.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM documents WHERE id = %s;", (f"job_{job_id}_test_doc_a",))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM sentences WHERE document_id = %s;", (f"job_{job_id}_test_doc_a",))
            assert cursor.fetchone()[0] == 0

    # Verify records deleted in Elasticsearch
    res = es.search(index=index_name, body={
        "query": {
            "prefix": {
                "document_id": f"job_{job_id}_"
            }
        }
    })
    assert res["hits"]["total"]["value"] == 0
