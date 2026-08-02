from enum import Enum
from pydantic import BaseModel, Field

class PaperType(str, Enum):
    """Supported paper types for section-aware analysis."""
    EMPIRICAL = "empirical"
    REVIEW = "review"
    CASE_STUDY = "case_study"
    OTHER = "other"

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
    match_type: str = Field(..., description="Type of match: 'lexical', 'semantic', or 'hybrid'.")
    score: float = Field(..., description="Cosine similarity score.")
    highlights: list[MatchHighlight] = Field(..., description="Exact coordinate highlights within the sentence.")

class PlagiarismAnalysisReport(BaseModel):
    plagiarism_score: float = Field(..., description="Overall plagiarism ratio (0.0 to 1.0).")
    total_sentences: int = Field(..., description="Total sentences in the query document.")
    plagiarized_sentences_count: int = Field(..., description="Total matched sentences.")
    lexical_matches_count: int = Field(..., description="Count of lexical matches.")
    semantic_matches_count: int = Field(..., description="Count of semantic matches.")
    hybrid_matches_count: int = Field(0, description="Count of hybrid matches.")
    matches: list[PlagiarismMatch] = Field(..., description="Sentence-by-sentence match details.")


class TopicInfo(BaseModel):
    """Topic profile information derived from the paper's abstract."""
    topics: list[str] = Field(default_factory=list, description="Ranked main topics extracted from abstract.")
    keywords: list[str] = Field(default_factory=list, description="Extracted keywords from abstract.")
    domain_hint: str | None = Field(None, description="Detected academic domain hint.")

class SectionAnalysisResult(BaseModel):
    """Plagiarism analysis results for a single document section."""
    section_name: str = Field(..., description="Canonical section name.")
    section_heading: str = Field("", description="Original heading text as found in the document.")
    analyzable: bool = Field(..., description="Whether this section was analyzed.")
    sentence_count: int = Field(0, description="Total sentences in this section.")
    plagiarized_count: int = Field(0, description="Plagiarized sentences in this section.")
    plagiarism_score: float = Field(0.0, description="Section-level plagiarism ratio.")
    matches: list[PlagiarismMatch] = Field(default_factory=list, description="Matches within this section.")

class EnhancedPlagiarismAnalysisReport(PlagiarismAnalysisReport):
    """Extended plagiarism report with section-level detail and topic information."""
    paper_type: PaperType = Field(PaperType.OTHER, description="The paper type used for analysis.")
    topics: TopicInfo = Field(default_factory=TopicInfo, description="Topic profile from abstract.")
    sections: list[SectionAnalysisResult] = Field(default_factory=list, description="Per-section analysis results.")
    sections_analyzed: int = Field(0, description="Number of sections that were analyzed.")
    sections_skipped: int = Field(0, description="Number of sections that were skipped.")
    skipped_section_names: list[str] = Field(default_factory=list, description="Names of skipped sections.")


class DocumentUploadResponse(BaseModel):
    filename: str = Field(..., description="The name of the uploaded file.")
    text: str = Field(..., description="The full extracted text of the document.")
    char_count: int = Field(..., description="Total characters in the document.")
    sentence_count: int = Field(..., description="Total segmented sentences in the document.")
    sentences: list[SentenceCoordinate] = Field(..., description="List of sentence coordinate objects.")
    analysis: PlagiarismAnalysisReport | None = Field(None, description="Detailed plagiarism analysis report.")

class RawTextAnalysisRequest(BaseModel):
    """Request body for the raw text analysis endpoint."""
    text: str = Field(..., min_length=50, max_length=500_000, description="Raw text to analyze.")
    paper_type: PaperType = Field(PaperType.OTHER, description="Type of paper for section-aware analysis.")
    match_type: str = Field("hybrid", description="Matching type to perform: 'lexical', 'semantic', or 'hybrid'.")

