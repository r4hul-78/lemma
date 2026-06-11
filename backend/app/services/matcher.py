import json
import difflib
from pathlib import Path
import numpy as np
import faiss
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer, util

from backend.app.config import settings
from backend.app.services.segmenter import SentenceSegmenterService
from backend.app.services.database import DatabaseService

def seed_database():
    """Seeds SQLite and FAISS index from the mock JSON references file if empty."""
    if not Path(settings.MOCK_DATABASE_PATH).exists():
        return
        
    with open(settings.MOCK_DATABASE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    # 1. Initialize SQLite Database schemas
    DatabaseService.initialize_db()
    
    # 2. Extract and segment sentences
    flat_sentences = []
    faiss_id_counter = 0
    
    for doc in data:
        # Save document metadata to SQLite
        DatabaseService.insert_reference_document(
            doc_id=doc["id"],
            title=doc["title"],
            author=doc["author"],
            source=doc["source"]
        )
        
        # Segment document text into sentences using the spaCy segmenter
        sentences = SentenceSegmenterService.segment(doc["text"])
        for s in sentences:
            flat_sentences.append({
                "faiss_id": faiss_id_counter,
                "document_id": doc["id"],
                "text": s["text"]
            })
            faiss_id_counter += 1
            
    if not flat_sentences:
        return
        
    # Save sentence records to SQLite
    DatabaseService.insert_reference_sentences(flat_sentences)
    
    # 3. Create FAISS Vector Index
    model = SemanticMatcher.get_model()
    corpus = [s["text"] for s in flat_sentences]
    
    # Encode sentences to embeddings
    embeddings = model.encode(corpus, show_progress_bar=False)
    embeddings = np.array(embeddings).astype("float32")
    
    # Normalize vectors for Cosine Similarity (Inner Product)
    faiss.normalize_L2(embeddings)
    
    # Build FAISS index
    dimension = 384  # model output dimension (all-MiniLM-L6-v2)
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    
    # Write FAISS index to disk
    faiss.write_index(index, str(settings.FAISS_INDEX_PATH))


def load_references() -> list[dict]:
    """
    Loads all references from the SQLite database.
    Seeds the database if it is empty.
    """
    DatabaseService.initialize_db()
    
    # Check if we have records
    count = DatabaseService.get_sentence_count()
    if count == 0:
        seed_database()
        
    # Query all sentences and documents
    with DatabaseService.get_connection() as conn:
        cursor = conn.execute("""
            SELECT s.text AS sentence_text, s.faiss_id, s.document_id, d.title, d.author, d.source
            FROM sentences s
            JOIN documents d ON s.document_id = d.id
            ORDER BY s.faiss_id ASC;
        """)
        rows = cursor.fetchall()
        
    flat_sentences = []
    for r in rows:
        flat_sentences.append({
            "text": r["sentence_text"],
            "faiss_id": r["faiss_id"],
            "doc_id": r["document_id"],
            "doc_title": r["title"],
            "doc_author": r["author"],
            "doc_source": r["source"]
        })
    return flat_sentences


class LexicalMatcher:
    """Detects verbatim or near-verbatim copy-paste text using TF-IDF and Cosine Similarity."""
    def __init__(self, references: list[dict]):
        self.references = references
        self.corpus = [ref["text"] for ref in references]
        self.vectorizer = TfidfVectorizer(stop_words='english')
        
        # Fit vectorizer and cache reference TF-IDF vectors
        if self.corpus:
            self.ref_vectors = self.vectorizer.fit_transform(self.corpus)
        else:
            self.ref_vectors = None

    def find_match(self, query_text: str, threshold: float = None) -> dict | None:
        """
        Compares query_text against reference sentences using TF-IDF.
        Returns the best match details if above threshold, else None.
        """
        if not self.references or self.ref_vectors is None or not query_text.strip():
            return None
            
        if threshold is None:
            threshold = settings.LEXICAL_THRESHOLD
            
        # Transform query text to TF-IDF vector
        query_vector = self.vectorizer.transform([query_text])
        
        # Compute cosine similarity between query and all reference vectors
        similarities = cosine_similarity(query_vector, self.ref_vectors)[0]
        
        # Find best match index and score
        best_idx = similarities.argmax()
        best_score = float(similarities[best_idx])
        
        if best_score >= threshold:
            best_ref = self.references[best_idx]
            return {
                "score": best_score,
                "text": best_ref["text"],
                "doc_id": best_ref["doc_id"],
                "doc_title": best_ref["doc_title"],
                "doc_author": best_ref["doc_author"],
                "doc_source": best_ref["doc_source"]
            }
        return None


class SemanticMatcher:
    """Detects paraphrased or structurally modified sentences using SentenceTransformers and local FAISS index."""
    _model = None

    @classmethod
    def get_model(cls):
        """Loads and returns the SentenceTransformer model as a singleton."""
        if cls._model is None:
            cls._model = SentenceTransformer(settings.SENTENCE_TRANSFORMERS_MODEL)
        return cls._model

    def __init__(self, references: list[dict] = None):
        """Loads the pre-computed FAISS index from disk, seeding database first if empty."""
        DatabaseService.initialize_db()
        if DatabaseService.get_sentence_count() == 0:
            seed_database()
            
        if Path(settings.FAISS_INDEX_PATH).exists():
            self.index = faiss.read_index(str(settings.FAISS_INDEX_PATH))
        else:
            self.index = None

    def find_match(self, query_text: str, threshold: float = None) -> dict | None:
        """
        Compares query_text against reference sentences using local FAISS index and sentence embeddings.
        Returns the best match details from SQLite if above threshold, else None.
        """
        if self.index is None or not query_text.strip():
            return None
            
        if threshold is None:
            threshold = settings.SEMANTIC_THRESHOLD
            
        model = self.get_model()
        # Encode query sentence
        query_embedding = model.encode(query_text, show_progress_bar=False)
        query_vector = np.array([query_embedding]).astype("float32")
        
        # Normalize vector for Cosine Similarity (Inner Product)
        faiss.normalize_L2(query_vector)
        
        # Query FAISS index for the closest match (k=1)
        scores, indices = self.index.search(query_vector, k=1)
        
        best_score = float(scores[0][0])
        best_faiss_id = int(indices[0][0])
        
        if best_faiss_id != -1 and best_score >= threshold:
            # Fetch metadata from SQLite database
            match_ref = DatabaseService.get_sentence_by_faiss_id(best_faiss_id)
            if match_ref:
                return {
                    "score": best_score,
                    "text": match_ref["text"],
                    "doc_id": match_ref["doc_id"],
                    "doc_title": match_ref["doc_title"],
                    "doc_author": match_ref["doc_author"],
                    "doc_source": match_ref["doc_source"]
                }
        return None


def get_matching_slices(query: str, ref: str, min_length: int = 6) -> list[dict]:
    """
    Extracts matching character slices between query and reference sentences.
    Merges overlapping/adjacent matches and filters out noise (short character matches).
    Returns list of matching character slice dictionaries relative to the query string.
    """
    matcher = difflib.SequenceMatcher(None, query.lower(), ref.lower())
    matching_blocks = matcher.get_matching_blocks()
    
    slices = []
    for block in matching_blocks:
        start_q, start_r, size = block
        if size >= min_length:
            matched_text = query[start_q : start_q + size]
            # Clean up whitespace and adjust offsets
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
        
    # Sort slices and merge overlapping or near-adjacent ones (separated by <= 2 chars of spacing/punctuation)
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
    """Coordinates the lexical and semantic matching stages to generate a comprehensive plagiarism profile."""
    def __init__(self, references: list[dict] = None):
        if references is None:
            references = load_references()
            
        self.lexical_matcher = LexicalMatcher(references)
        self.semantic_matcher = SemanticMatcher(references)

    def analyze_sentence(self, query_sentence: str, lexical_threshold: float = None, semantic_threshold: float = None) -> dict | None:
        """Runs lexical analysis followed by semantic analysis on a query sentence."""
        # 1. Run TF-IDF lexical match
        lexical_match = self.lexical_matcher.find_match(query_sentence, lexical_threshold)
        if lexical_match:
            lexical_match["match_type"] = "lexical"
            return lexical_match
            
        # 2. Run sentence embeddings semantic match
        semantic_match = self.semantic_matcher.find_match(query_sentence, semantic_threshold)
        if semantic_match:
            semantic_match["match_type"] = "semantic"
            return semantic_match
            
        return None

    def analyze_document(
        self, 
        sentences: list[dict], 
        lexical_threshold: float = None, 
        semantic_threshold: float = None
    ) -> dict:
        """
        Performs full document plagiarism analysis across segmented sentence coordinate structures.
        """
        matched_sentences = []
        lexical_count = 0
        semantic_count = 0
        
        for s in sentences:
            q_text = s["text"]
            match = self.analyze_sentence(q_text, lexical_threshold, semantic_threshold)
            
            if match:
                if match["match_type"] == "lexical":
                    lexical_count += 1
                elif match["match_type"] == "semantic":
                    semantic_count += 1
                
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
            "matches": matched_sentences
        }
