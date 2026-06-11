from pydantic import BaseModel, Field

class SentenceCoordinate(BaseModel):
    text: str = Field(..., description="The raw text of the segmented sentence.")
    start_char: int = Field(..., description="The 0-based start character offset in the document.")
    end_char: int = Field(..., description="The 0-based end character offset in the document.")

class MatchHighlight(BaseModel):
    start_char: int = Field(..., description="The 0-based start offset of the highlight in the document.")
    end_char: int = Field(..., description="The 0-based end offset of the highlight in the document.")
    text: str = Field(..., description="The text matching fragment.")

class MatchedSentenceInfo(BaseModel):
    text: str = Field(..., description="The matching reference sentence text.")
    doc_id: str = Field(..., description="Reference document ID.")
    doc_title: str = Field(..., description="Reference document title.")
    doc_author: str = Field(..., description="Reference document author.")
    doc_source: str = Field(..., description="Reference document source.")

class PlagiarismMatch(BaseModel):
    query_sentence: SentenceCoordinate = Field(..., description="The query sentence coordinates.")
    matched_sentence: MatchedSentenceInfo = Field(..., description="The matched reference sentence details.")
    match_type: str = Field(..., description="Type of match: 'lexical' or 'semantic'.")
    score: float = Field(..., description="Cosine similarity score.")
    highlights: list[MatchHighlight] = Field(..., description="Exact coordinate highlights within the sentence.")

class PlagiarismAnalysisReport(BaseModel):
    plagiarism_score: float = Field(..., description="Overall plagiarism ratio (0.0 to 1.0).")
    total_sentences: int = Field(..., description="Total sentences in the query document.")
    plagiarized_sentences_count: int = Field(..., description="Total matched sentences.")
    lexical_matches_count: int = Field(..., description="Count of lexical matches.")
    semantic_matches_count: int = Field(..., description="Count of semantic matches.")
    matches: list[PlagiarismMatch] = Field(..., description="Sentence-by-sentence match details.")

class DocumentUploadResponse(BaseModel):
    filename: str = Field(..., description="The name of the uploaded file.")
    text: str = Field(..., description="The full extracted text of the document.")
    char_count: int = Field(..., description="Total characters in the document.")
    sentence_count: int = Field(..., description="Total segmented sentences in the document.")
    sentences: list[SentenceCoordinate] = Field(..., description="List of sentence coordinate objects.")
    analysis: PlagiarismAnalysisReport | None = Field(None, description="Detailed plagiarism analysis report.")
