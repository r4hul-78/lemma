import logging
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from app.config import settings

logger = logging.getLogger(__name__)

_es_client = None

def get_es_client() -> Elasticsearch:
    """Returns the Elasticsearch client singleton instance."""
    global _es_client
    if _es_client is None:
        headers = {
            "Accept": "application/vnd.elasticsearch+json; compatible-with=8",
            "Content-Type": "application/vnd.elasticsearch+json; compatible-with=8"
        }
        _es_client = Elasticsearch(settings.ELASTICSEARCH_URL, headers=headers)
    return _es_client

def initialize_es() -> None:
    """Creates the reference_sentences Elasticsearch index with custom BM25 mappings if it doesn't exist."""
    es = get_es_client()
    index_name = "reference_sentences"
    try:
        if not es.indices.exists(index=index_name):
            mappings = {
                "mappings": {
                    "properties": {
                        "document_id": { "type": "keyword" },
                        "sentence_index": { "type": "integer" },
                        "text": { "type": "text" }
                    }
                }
            }
            es.indices.create(index=index_name, body=mappings)
            logger.info(f"Created Elasticsearch index: '{index_name}' with mappings.")
        else:
            logger.info(f"Elasticsearch index '{index_name}' already exists.")
    except Exception as e:
        logger.error(f"Failed to initialize Elasticsearch index: {e}")
        # Re-raise so that startup fails fast if ES is configured but unavailable
        raise e

def index_sentence_bulk(sentences: list[dict]) -> None:
    """
    Bulk indexes sentences into Elasticsearch.
    Each item in sentences list must contain:
    {
        "document_id": str,
        "sentence_index": int,
        "text": str
    }
    """
    es = get_es_client()
    index_name = "reference_sentences"
    actions = [
        {
            "_index": index_name,
            "_source": {
                "document_id": s["document_id"],
                "sentence_index": s["sentence_index"],
                "text": s["text"]
            }
        }
        for s in sentences
    ]
    try:
        success, failed = bulk(es, actions)
        es.indices.refresh(index=index_name)
        logger.info(f"Successfully indexed {success} sentences to Elasticsearch (failed: {len(failed) if isinstance(failed, list) else failed})")
    except Exception as e:
        logger.error(f"Bulk indexing to Elasticsearch failed: {e}")
        raise e

def search_sentences_bm25(query_text: str, k: int = 20, job_id: str = None) -> list[dict]:
    """
    Performs BM25 keyword matching against the reference sentences index.
    Returns the top K matches with document references and raw BM25 scores.
    """
    if not query_text.strip():
        return []
        
    es = get_es_client()
    index_name = "reference_sentences"
    
    if job_id:
        query = {
            "query": {
                "bool": {
                    "must": {
                        "match": {
                            "text": query_text
                        }
                    },
                    "filter": {
                        "bool": {
                            "should": [
                                { "prefix": { "document_id": "ref_" } },
                                { "prefix": { "document_id": f"job_{job_id}_" } }
                            ]
                        }
                    }
                }
            },
            "size": k
        }
    else:
        query = {
            "query": {
                "match": {
                    "text": query_text
                }
            },
            "size": k
        }
    
    try:
        response = es.search(index=index_name, body=query)
        hits = response["hits"]["hits"]
        results = []
        for hit in hits:
            results.append({
                "document_id": hit["_source"]["document_id"],
                "sentence_index": hit["_source"]["sentence_index"],
                "text": hit["_source"]["text"],
                "score": hit["_score"]
            })
        return results
    except Exception as e:
        logger.error(f"Elasticsearch BM25 query failed: {e}")
        # Return empty list to avoid breaking the entire hybrid pipeline if ES is temporarily down
        return []
