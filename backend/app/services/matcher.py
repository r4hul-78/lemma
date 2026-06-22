import json
import difflib
import logging
import psycopg2
import psycopg2.extras
from pathlib import Path
from sentence_transformers import SentenceTransformer

from backend.app.config import settings
from backend.app.services.segmenter import SentenceSegmenterService
from backend.app.services.database import DatabaseService
from backend.app.services.elasticsearch_client import (
    initialize_es,
    index_sentence_bulk,
    search_sentences_bm25
)

logger = logging.getLogger(__name__)

def search_sentences_semantic(query_vector: list[float], k: int = 20, job_id: str = None) -> list[dict]:
    """
    Performs cosine similarity neighbor search against pgvector.
    Returns the top K matches with document details and cosine similarity scores.
    """
    vector_str = f"[{','.join(map(str, query_vector))}]"
    
    with DatabaseService.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if job_id:
                query = """
                    SELECT s.text, s.document_id, s.sentence_index, d.title, d.author, d.source, (s.embedding <=> %s) AS distance
                    FROM sentences s
                    JOIN documents d ON s.document_id = d.id
                    WHERE s.document_id LIKE 'ref_%%' OR s.document_id LIKE 'job_' || %s || '_%%'
                    ORDER BY distance ASC
                    LIMIT %s;
                """
                cursor.execute(query, (vector_str, job_id, k))
            else:
                query = """
                    SELECT s.text, s.document_id, s.sentence_index, d.title, d.author, d.source, (s.embedding <=> %s) AS distance
                    FROM sentences s
                    JOIN documents d ON s.document_id = d.id
                    ORDER BY distance ASC
                    LIMIT %s;
                """
                cursor.execute(query, (vector_str, k))
                
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                distance = float(r["distance"]) if r["distance"] is not None else 1.0
                results.append({
                    "document_id": r["document_id"],
                    "sentence_index": r["sentence_index"],
                    "text": r["text"],
                    "title": r["title"],
                    "author": r["author"],
                    "source": r["source"],
                    "score": 1.0 - distance  # Cosine Similarity
                })
            return results


def seed_database():
    """Seeds PostgreSQL and Elasticsearch from the mock JSON references file if empty."""
    DatabaseService.initialize_db()
    
    # Check if database is already seeded
    try:
        count = DatabaseService.get_sentence_count()
        if count > 0:
            logger.info("Database already seeded.")
            return
    except Exception as e:
        logger.error(f"Failed to check sentence count during seed check: {e}")
        
    if not Path(settings.MOCK_DATABASE_PATH).exists():
        logger.warning(f"Mock references file not found at: {settings.MOCK_DATABASE_PATH}")
        return
        
    with open(settings.MOCK_DATABASE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # Initialize Elasticsearch index
    initialize_es()
    
    flat_sentences = []
    
    for doc in data:
        # Save document metadata to PostgreSQL
        DatabaseService.insert_reference_document(
            doc_id=doc["id"],
            title=doc["title"],
            author=doc["author"],
            source=doc["source"]
        )
        
        # Segment document text into sentences using spaCy segmenter
        sentences = SentenceSegmenterService.segment(doc["text"])
        for idx, s in enumerate(sentences):
            flat_sentences.append({
                "document_id": doc["id"],
                "sentence_index": idx,
                "text": s["text"]
            })
            
    if not flat_sentences:
        return
        
    # Generate vector embeddings
    model = SemanticMatcher.get_model()
    corpus = [s["text"] for s in flat_sentences]
    embeddings = model.encode(corpus, show_progress_bar=False)
    
    for s, emb in zip(flat_sentences, embeddings):
        s["embedding"] = emb.tolist()
        
    # Dual-Write Pattern:
    # 1. Write to PostgreSQL (relational metadata + vectors)
    DatabaseService.insert_reference_sentences(flat_sentences)
    
    # 2. Write to Elasticsearch (document_id, sentence_index, text)
    index_sentence_bulk(flat_sentences)
    logger.info("Database and Elasticsearch seeded successfully.")


def load_references() -> list[dict]:
    """
    Loads all references from the PostgreSQL database.
    Seeds the database if it is empty.
    """
    DatabaseService.initialize_db()
    
    try:
        count = DatabaseService.get_sentence_count()
        if count == 0:
            seed_database()
    except Exception:
        seed_database()
        
    # Query all sentences and documents
    with DatabaseService.get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT s.text AS sentence_text, s.id AS sentence_id, s.sentence_index, s.document_id, d.title, d.author, d.source
                FROM sentences s
                JOIN documents d ON s.document_id = d.id
                ORDER BY s.id ASC;
            """)
            rows = cursor.fetchall()
            
    flat_sentences = []
    for r in rows:
        flat_sentences.append({
            "text": r["sentence_text"],
            "faiss_id": r["sentence_id"],  # kept for compatibility with legacy test_matcher
            "doc_id": r["document_id"],
            "doc_title": r["title"],
            "doc_author": r["author"],
            "doc_source": r["source"]
        })
    return flat_sentences


class LexicalMatcher:
    """Detects verbatim or near-verbatim copy-paste text using Elasticsearch BM25."""
    def __init__(self, references: list[dict] = None):
        self.references = references

    def find_match(self, query_text: str, threshold: float = None, job_id: str = None) -> dict | None:
        """Compares query_text against reference sentences using Elasticsearch BM25."""
        if threshold is None:
            threshold = settings.LEXICAL_THRESHOLD
            
        results = search_sentences_bm25(query_text, k=1, job_id=job_id)
        if not results:
            return None
            
        best = results[0]
        # Calculate lexical similarity using word-level sequence matcher ratio to avoid matching paraphrases
        q_words = query_text.lower().split()
        r_words = best["text"].lower().split()
        similarity = difflib.SequenceMatcher(None, q_words, r_words).ratio()
        
        if similarity >= threshold:
            with DatabaseService.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT title, author, source FROM documents WHERE id = %s;", (best["document_id"],))
                    doc = cursor.fetchone()
                    
            doc_title = doc["title"] if doc else "Unknown"
            doc_author = doc["author"] if doc else "N/A"
            doc_source = doc["source"] if doc else "N/A"
            
            return {
                "score": similarity,
                "text": best["text"],
                "doc_id": best["document_id"],
                "doc_title": doc_title,
                "doc_author": doc_author,
                "doc_source": doc_source
            }
        return None


class SemanticMatcher:
    """Detects paraphrased or structurally modified sentences using pgvector."""
    _model = None

    @classmethod
    def get_model(cls):
        """Loads and returns the SentenceTransformer model as a singleton."""
        if cls._model is None:
            cls._model = SentenceTransformer(settings.SENTENCE_TRANSFORMERS_MODEL)
        return cls._model

    def __init__(self, references: list[dict] = None):
        self.references = references

    def find_match(self, query_text: str, threshold: float = None, job_id: str = None) -> dict | None:
        """Compares query_text against reference sentences using pgvector cosine similarity."""
        if threshold is None:
            threshold = settings.SEMANTIC_THRESHOLD
            
        model = self.get_model()
        query_embedding = model.encode(query_text, show_progress_bar=False).tolist()
        
        results = search_sentences_semantic(query_embedding, k=1, job_id=job_id)
        if not results:
            return None
            
        best = results[0]
        score = best["score"]
        
        if score >= threshold:
            return {
                "score": score,
                "text": best["text"],
                "doc_id": best["document_id"],
                "doc_title": best["title"],
                "doc_author": best["author"],
                "doc_source": best["source"]
            }
        return None


def get_matching_slices(query: str, ref: str, min_length: int = 6) -> list[dict]:
    """
    Extracts matching character slices between query and reference sentences.
    Merges overlapping/adjacent matches and filters out noise.
    """
    matcher = difflib.SequenceMatcher(None, query.lower(), ref.lower())
    matching_blocks = matcher.get_matching_blocks()
    
    slices = []
    for block in matching_blocks:
        start_q, start_r, size = block
        if size >= min_length:
            matched_text = query[start_q : start_q + size]
            stripped_text = matched_text.strip()
            if stripped_text:
                leading_spaces = len(matched_text) - len(matched_text.lstrip())
                trailing_spaces = len(matched_text) - len(matched_text.rstrip())
                
                final_start = start_q + leading_spaces
                final_end = start_q + size - trailing_spaces
                
                if (final_end - final_start) >= min_length:
                    slices.append({
                        "start": final_start,
                        "end": final_end,
                        "text": query[final_start:final_end]
                    })
    
    if not slices:
        return []
        
    slices.sort(key=lambda x: x["start"])
    merged = [slices[0]]
    for current in slices[1:]:
        prev = merged[-1]
        if current["start"] <= prev["end"] + 2:
            prev["end"] = max(prev["end"], current["end"])
            prev["text"] = query[prev["start"]:prev["end"]]
        else:
            merged.append(current)
            
    return merged


class DualTierMatcher:
    """Coordinates the lexical and semantic matching stages to generate a comprehensive plagiarism profile using RRF."""
    def __init__(self, references: list[dict] = None):
        # Automatically seed database on initialization if empty
        seed_database()
        self.lexical_matcher = LexicalMatcher(references)
        self.semantic_matcher = SemanticMatcher(references)

    def analyze_sentence(self, query_sentence: str, lexical_threshold: float = None, semantic_threshold: float = None, job_id: str = None) -> dict | None:
        """Runs hybrid plagiarism analysis using RRF across Elasticsearch and pgvector."""
        if lexical_threshold is None:
            lexical_threshold = settings.LEXICAL_THRESHOLD
        if semantic_threshold is None:
            semantic_threshold = settings.SEMANTIC_THRESHOLD
            
        # 1. Retrieve candidates from Elasticsearch (Query A)
        es_results = search_sentences_bm25(query_sentence, k=20, job_id=job_id)
        
        # 2. Retrieve candidates from pgvector (Query B)
        model = SemanticMatcher.get_model()
        query_embedding = model.encode(query_sentence, show_progress_bar=False).tolist()
        semantic_results = search_sentences_semantic(query_embedding, k=20, job_id=job_id)
        
        if not es_results and not semantic_results:
            return None
            
        # 3. Apply Reciprocal Rank Fusion (RRF)
        k = 60
        candidates = {}
        
        for rank_idx, res in enumerate(es_results):
            key = (res["document_id"], res["sentence_index"])
            rank = rank_idx + 1
            candidates[key] = {
                "document_id": res["document_id"],
                "sentence_index": res["sentence_index"],
                "text": res["text"],
                "es_rank": rank,
                "es_score": res["score"],
                "semantic_rank": None,
                "semantic_score": None,
                "rrf_score": 1.0 / (k + rank)
            }
            
        for rank_idx, res in enumerate(semantic_results):
            key = (res["document_id"], res["sentence_index"])
            rank = rank_idx + 1
            if key in candidates:
                candidates[key]["semantic_rank"] = rank
                candidates[key]["semantic_score"] = res["score"]
                candidates[key]["rrf_score"] += 1.0 / (k + rank)
                candidates[key]["text"] = res["text"]
                candidates[key]["title"] = res["title"]
                candidates[key]["author"] = res["author"]
                candidates[key]["source"] = res["source"]
            else:
                candidates[key] = {
                    "document_id": res["document_id"],
                    "sentence_index": res["sentence_index"],
                    "text": res["text"],
                    "es_rank": None,
                    "es_score": None,
                    "semantic_rank": rank,
                    "semantic_score": res["score"],
                    "title": res["title"],
                    "author": res["author"],
                    "source": res["source"],
                    "rrf_score": 1.0 / (k + rank)
                }
                
        # Resolve document metadata for candidates found only in ES
        missing_doc_ids = [
            key[0] for key, cand in candidates.items()
            if "title" not in cand
        ]
        if missing_doc_ids:
            with DatabaseService.get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute("SELECT id, title, author, source FROM documents WHERE id IN %s;", (tuple(missing_doc_ids),))
                    docs = cursor.fetchall()
                    doc_meta_map = {d["id"]: d for d in docs}
            for key, cand in candidates.items():
                if "title" not in cand:
                    doc_id = key[0]
                    meta = doc_meta_map.get(doc_id, {})
                    cand["title"] = meta.get("title", "Unknown Reference")
                    cand["author"] = meta.get("author", "N/A")
                    cand["source"] = meta.get("source", "N/A")
                    
        # Sort by RRF score descending
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )
        
        if not sorted_candidates:
            return None
            
        best = sorted_candidates[0]
        
        # Calculate normalized RRF score
        rrf_max = 2.0 / (k + 1)
        normalized_rrf = best["rrf_score"] / rrf_max
        
        # Calculate word-level similarity for validation
        q_words = query_sentence.lower().split()
        r_words = best["text"].lower().split()
        lexical_sim = difflib.SequenceMatcher(None, q_words, r_words).ratio()
        
        # Classify Match Type:
        # If present in both, it's hybrid
        # If only in ES, it's lexical
        # If only in pgvector, it's semantic
        if best["es_rank"] is not None and best["semantic_rank"] is not None:
            match_type = "hybrid"
        elif best["es_rank"] is not None:
            match_type = "lexical"
        else:
            match_type = "semantic"
            
        # Validate match against thresholds to prevent false positives and correctly handle single-source matches
        is_valid = False
        if match_type == "hybrid":
            if normalized_rrf >= settings.HYBRID_THRESHOLD:
                if (best["semantic_score"] is not None and best["semantic_score"] >= semantic_threshold) or (lexical_sim >= lexical_threshold):
                    is_valid = True
        elif match_type == "lexical":
            if lexical_sim >= lexical_threshold:
                is_valid = True
        elif match_type == "semantic":
            if best["semantic_score"] is not None and best["semantic_score"] >= semantic_threshold:
                is_valid = True
                
        if not is_valid:
            return None
            
        # Compute display score
        if best["semantic_score"] is not None:
            display_score = best["semantic_score"]
        else:
            display_score = lexical_sim
            
        display_score = max(0.0, min(1.0, display_score))
        
        return {
            "score": display_score,
            "text": best["text"],
            "doc_id": best["document_id"],
            "doc_title": best["title"],
            "doc_author": best["author"],
            "doc_source": best["source"],
            "match_type": match_type,
            "normalized_rrf": normalized_rrf
        }

    def analyze_document(
        self, 
        sentences: list[dict], 
        lexical_threshold: float = None, 
        semantic_threshold: float = None,
        job_id: str = None
    ) -> dict:
        """
        Performs full document plagiarism analysis across segmented sentence coordinate structures.
        """
        matched_sentences = []
        lexical_count = 0
        semantic_count = 0
        hybrid_count = 0
        
        for s in sentences:
            q_text = s["text"]
            match = self.analyze_sentence(q_text, lexical_threshold, semantic_threshold, job_id=job_id)
            
            if match:
                if match["match_type"] == "lexical":
                    lexical_count += 1
                elif match["match_type"] == "semantic":
                    semantic_count += 1
                elif match["match_type"] == "hybrid":
                    hybrid_count += 1
                
                # Extract word slices relative to the sentence text
                slices = get_matching_slices(q_text, match["text"])
                
                # Re-map slices to absolute character indices in the original document
                abs_highlights = []
                for sl in slices:
                    abs_highlights.append({
                        "start_char": s["start_char"] + sl["start"],
                        "end_char": s["start_char"] + sl["end"],
                        "text": sl["text"]
                    })
                
                matched_sentences.append({
                    "query_sentence": {
                        "text": q_text,
                        "start_char": s["start_char"],
                        "end_char": s["end_char"]
                    },
                    "matched_sentence": {
                        "text": match["text"],
                        "doc_id": match["doc_id"],
                        "doc_title": match["doc_title"],
                        "doc_author": match["doc_author"],
                        "doc_source": match["doc_source"]
                    },
                    "match_type": match["match_type"],
                    "score": match["score"],
                    "highlights": abs_highlights
                })
        
        total_sentences = len(sentences)
        plagiarized_count = len(matched_sentences)
        plagiarism_score = (plagiarized_count / total_sentences) if total_sentences > 0 else 0.0
        
        return {
            "plagiarism_score": plagiarism_score,
            "total_sentences": total_sentences,
            "plagiarized_sentences_count": plagiarized_count,
            "lexical_matches_count": lexical_count,
            "semantic_matches_count": semantic_count,
            "hybrid_matches_count": hybrid_count,
            "matches": matched_sentences
        }
