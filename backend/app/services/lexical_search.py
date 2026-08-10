"""
Lexical Search Service — Postgres tsvector + pg_trgm

Replaces the Elasticsearch BM25 search backend with PostgreSQL full-text search
(tsvector/GIN) and trigram similarity (pg_trgm). Provides the exact same interface
as the former elasticsearch_client.py so all consumers are drop-in compatible.
"""

import logging
import psycopg2
import psycopg2.extras
from app.services.database import DatabaseService

logger = logging.getLogger(__name__)


def initialize_lexical_index() -> None:
    """
    No-op — the tsvector column, GIN indexes, and pg_trgm extension are
    created by DatabaseService.initialize_db(). This function exists solely
    to preserve interface compatibility with the former initialize_es().
    """
    logger.info("Lexical index initialization: handled by DatabaseService.initialize_db() (tsvector + pg_trgm).")


def index_sentence_bulk(sentences: list[dict]) -> None:
    """
    No-op — sentences are already written to the PostgreSQL `sentences` table
    by DatabaseService.insert_reference_sentences(), and the tsvector column
    is auto-generated. This eliminates the former dual-write to Elasticsearch.

    The function signature is preserved for interface compatibility.
    """
    logger.debug(f"index_sentence_bulk called with {len(sentences)} sentences (no-op — data already in Postgres).")


def search_sentences_bm25(query_text: str, k: int = 20, job_id: str = None) -> list[dict]:
    """
    Full-text search against the `sentences` table using PostgreSQL
    tsvector ranking (ts_rank) as a BM25-equivalent signal, with pg_trgm
    similarity as a secondary fuzzy matching boost.

    Returns the top K matches with document references and combined scores,
    in the same format as the former Elasticsearch implementation:
    [{"document_id", "sentence_index", "text", "score"}, ...]
    """
    if not query_text or not query_text.strip():
        return []

    try:
        with DatabaseService.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Build the tsquery from the input text.
                # plainto_tsquery handles natural language input without requiring
                # the caller to construct boolean query syntax.
                #
                # Scoring combines two signals:
                #   1. ts_rank — full-text relevance (analogous to BM25)
                #   2. similarity — trigram character-level fuzzy match (pg_trgm)
                #
                # The combined score uses a 70/30 weighting to prioritize
                # full-text relevance while still rewarding fuzzy overlap.

                if job_id:
                    query = """
                        SELECT
                            s.document_id,
                            s.sentence_index,
                            s.text,
                            (
                                COALESCE(ts_rank(s.text_tsv, websearch_to_tsquery('english', %(query)s)), 0) * 0.6
                                + similarity(s.text, %(query)s) * 0.4
                            ) AS score
                        FROM sentences s
                        WHERE
                            (
                                s.text_tsv @@ websearch_to_tsquery('english', %(query)s)
                                OR similarity(s.text, %(query)s) > 0.15
                            )
                            AND (
                                s.document_id LIKE 'ref_%%'
                                OR s.document_id LIKE 'job_' || %(job_id)s || '_%%'
                            )
                        ORDER BY score DESC
                        LIMIT %(k)s;
                    """
                    cursor.execute(query, {"query": query_text, "job_id": job_id, "k": k})
                else:
                    query = """
                        SELECT
                            s.document_id,
                            s.sentence_index,
                            s.text,
                            (
                                COALESCE(ts_rank(s.text_tsv, websearch_to_tsquery('english', %(query)s)), 0) * 0.6
                                + similarity(s.text, %(query)s) * 0.4
                            ) AS score
                        FROM sentences s
                        WHERE
                            (
                                s.text_tsv @@ websearch_to_tsquery('english', %(query)s)
                                OR similarity(s.text, %(query)s) > 0.15
                            )
                        ORDER BY score DESC
                        LIMIT %(k)s;
                    """
                    cursor.execute(query, {"query": query_text, "k": k})

                rows = cursor.fetchall()

                results = []
                for r in rows:
                    results.append({
                        "document_id": r["document_id"],
                        "sentence_index": r["sentence_index"],
                        "text": r["text"],
                        "score": float(r["score"]) if r["score"] is not None else 0.0,
                    })

                # If full-text search returned no results (e.g. all query words are
                # stop-words or the tsquery is empty), fall back to trigram similarity
                # only. This prevents returning zero results for legitimate queries
                # that happen to consist entirely of common English words.
                if not results:
                    results = _fallback_trigram_search(cursor, query_text, k, job_id)

                return results

    except Exception as e:
        logger.error(f"Postgres lexical search failed: {e}")
        # Return empty list to avoid breaking the hybrid pipeline
        return []


def _fallback_trigram_search(cursor, query_text: str, k: int, job_id: str = None) -> list[dict]:
    """
    Pure trigram similarity search — used as a fallback when the tsvector
    full-text query returns no results (e.g. when all query terms are
    stop-words that get stripped by to_tsquery).
    """
    try:
        if job_id:
            query = """
                SELECT
                    s.document_id,
                    s.sentence_index,
                    s.text,
                    similarity(s.text, %(query)s) AS score
                FROM sentences s
                WHERE
                    similarity(s.text, %(query)s) > 0.1
                    AND (
                        s.document_id LIKE 'ref_%%'
                        OR s.document_id LIKE 'job_' || %(job_id)s || '_%%'
                    )
                ORDER BY score DESC
                LIMIT %(k)s;
            """
            cursor.execute(query, {"query": query_text, "job_id": job_id, "k": k})
        else:
            query = """
                SELECT
                    s.document_id,
                    s.sentence_index,
                    s.text,
                    similarity(s.text, %(query)s) AS score
                FROM sentences s
                WHERE
                    similarity(s.text, %(query)s) > 0.1
                ORDER BY score DESC
                LIMIT %(k)s;
            """
            cursor.execute(query, {"query": query_text, "k": k})

        rows = cursor.fetchall()
        return [
            {
                "document_id": r["document_id"],
                "sentence_index": r["sentence_index"],
                "text": r["text"],
                "score": float(r["score"]) if r["score"] is not None else 0.0,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Trigram fallback search failed: {e}")
        return []
