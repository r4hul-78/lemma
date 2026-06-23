from app.services.matcher import (
    load_references,
    LexicalMatcher,
    SemanticMatcher,
    get_matching_slices,
    DualTierMatcher
)
from app.services.database import DatabaseService
from app.config import settings

def test_database_and_elasticsearch_initialization():
    # Trigger loading references, which seeds database and ES if empty
    references = load_references()
    assert len(references) > 0
    
    # Verify records in database
    assert DatabaseService.get_sentence_count() == len(references)
    
    # Retrieve sentence by faiss_id (which is s.id primary key in Postgres) and verify it matches references
    for i in range(min(5, len(references))):
        ref_item = references[i]
        db_item = DatabaseService.get_sentence_by_faiss_id(ref_item["faiss_id"])
        assert db_item is not None
        assert db_item["text"] == ref_item["text"]
        assert db_item["doc_id"] == ref_item["doc_id"]
        assert db_item["doc_title"] == ref_item["doc_title"]
        assert db_item["doc_author"] == ref_item["doc_author"]
        assert db_item["doc_source"] == ref_item["doc_source"]


def test_load_references():
    references = load_references()
    assert len(references) > 0
    # Every reference item must have required fields
    for ref in references:
        assert "text" in ref
        assert "doc_id" in ref
        assert "doc_title" in ref
        assert "doc_author" in ref
        assert "doc_source" in ref
        assert len(ref["text"].strip()) > 0

def test_lexical_matcher_exact_copy():
    references = load_references()
    matcher = LexicalMatcher(references)
    
    # Take an exact sentence from the reference database
    ref_sentence = references[0]["text"]
    
    # Exact copy should match with high similarity
    match = matcher.find_match(ref_sentence, threshold=0.7)
    assert match is not None
    assert match["text"] == ref_sentence
    assert match["score"] > 0.95
    assert match["doc_id"] == references[0]["doc_id"]
    
    # Completely unrelated sentence should not match
    no_match = matcher.find_match("We like eating pizza on Friday nights while watching movies.", threshold=0.7)
    assert no_match is None

def test_semantic_matcher_paraphrase():
    references = load_references()
    lex_matcher = LexicalMatcher(references)
    sem_matcher = SemanticMatcher(references)
    
    # Original from database: "Climate change represents one of the defining challenges of our generation, requiring immediate and decisive systemic shifts."
    # Heavily paraphrased version:
    paraphrased = "Global warming is one of the key challenges of our time, requiring immediate and strong systemic changes."
    
    # Check that it doesn't match lexically (threshold 0.7)
    lex_match = lex_matcher.find_match(paraphrased, threshold=0.7)
    assert lex_match is None
    
    # Check that it matches semantically
    sem_match = sem_matcher.find_match(paraphrased, threshold=0.55)
    assert sem_match is not None
    assert sem_match["doc_id"] == "ref_climate_change"
    assert sem_match["score"] >= 0.55

def test_get_matching_slices():
    query = "Transitioning from fossil fuels to clean solar power is key."
    ref = "Transitioning from fossil fuels to renewable energy sources is key."
    
    slices = get_matching_slices(query, ref, min_length=6)
    
    # We expect two matches:
    # 1. "Transitioning from fossil fuels to"
    # 2. "is key." (which strips to "is key")
    assert len(slices) == 2
    
    # Sort just in case
    slices.sort(key=lambda x: x["start"])
    
    assert slices[0]["text"] == "Transitioning from fossil fuels to"
    assert slices[0]["start"] == 0
    assert slices[0]["end"] == 34
    
    assert slices[1]["text"] == "is key."
    assert slices[1]["start"] == 53
    assert slices[1]["end"] == 60

def test_dual_tier_matcher_integration():
    # Setup query sentences with absolute offsets
    # Sentence 1: Exact copy from ref_history_internet
    # Sentence 2: Original/clean sentence
    # Sentence 3: Paraphrased from ref_dna_genetics
    text1 = "The World Wide Web was invented by Sir Tim Berners-Lee in 1989 while working at CERN as a distributed information sharing system."
    text2 = "In this paper, we present a novel approach to local file indexing."
    text3 = "Genomic edit methods have progressed very fast, powered by finding and creating the CRISPR-Cas9 mechanism."
    
    full_text = f"{text1} {text2} {text3}"
    
    sentences = [
        {"text": text1, "start_char": 0, "end_char": len(text1)},
        {"text": text2, "start_char": len(text1) + 1, "end_char": len(text1) + 1 + len(text2)},
        {"text": text3, "start_char": len(text1) + 1 + len(text2) + 1, "end_char": len(full_text)}
    ]
    
    matcher = DualTierMatcher()
    report = matcher.analyze_document(sentences, lexical_threshold=0.7, semantic_threshold=0.55)
    
    assert report["total_sentences"] == 3
    # Both text1 (lexical/hybrid) and text3 (semantic) should match
    assert report["plagiarized_sentences_count"] == 2
    assert abs(report["plagiarism_score"] - 0.666) < 0.01
    
    matches = report["matches"]
    assert len(matches) == 2
    
    # Verify match detail structure
    m1 = matches[0]
    # In hybrid RRF, exact copies appear in both ES and pgvector top K, so it could be "hybrid" or "lexical" depending on rank
    assert m1["match_type"] in ("lexical", "hybrid")
    assert m1["matched_sentence"]["doc_id"] == "ref_history_internet"
    assert len(m1["highlights"]) > 0
    for hl in m1["highlights"]:
        assert hl["start_char"] >= 0
        assert hl["end_char"] <= len(text1)
        
    m2 = matches[1]
    assert m2["match_type"] in ("semantic", "hybrid")
    assert m2["matched_sentence"]["doc_id"] == "ref_dna_genetics"
    assert len(m2["highlights"]) > 0
    for hl in m2["highlights"]:
        assert hl["start_char"] >= sentences[2]["start_char"]
        assert hl["end_char"] <= sentences[2]["end_char"]
