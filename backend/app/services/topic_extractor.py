"""
Topic Extractor Service

Extracts topics, keywords, and search queries from the abstract of an
uploaded paper using the spaCy NLP pipeline and SentenceTransformer
embeddings.  Produces a ``TopicProfile`` used to drive downstream
retrieval of related academic papers.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from app.config import settings
from app.services.segmenter import SentenceSegmenterService

logger = logging.getLogger(__name__)


@dataclass
class TopicProfile:
    """Encapsulates the topic analysis results derived from an abstract."""
    abstract_text: str
    topics: list[str] = field(default_factory=list)       # Ranked 3–5 main topics
    keywords: list[str] = field(default_factory=list)      # 5–10 extracted keywords
    domain_hint: str | None = None                         # e.g. "computer_science"
    search_queries: list[str] = field(default_factory=list)  # Ready-to-use queries
    embedding: list[float] | None = None                   # Abstract-level embedding


# ---------------------------------------------------------------------------
# Domain hint mapping – maps common entity / noun-chunk terms to broad
# academic domains.  Used as a weak signal, not authoritative.
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "computer_science": [
        "algorithm", "neural", "network", "machine learning", "deep learning",
        "software", "database", "computing", "artificial intelligence",
        "natural language", "transformer", "convolutional",
    ],
    "medicine": [
        "patient", "clinical", "disease", "treatment", "diagnosis",
        "surgery", "hospital", "medical", "therapeutic", "pathology",
    ],
    "biology": [
        "gene", "protein", "cell", "organism", "species", "evolution",
        "genomic", "molecular", "biological", "ecology",
    ],
    "physics": [
        "quantum", "particle", "photon", "relativity", "cosmology",
        "electromagnetic", "thermodynamic",
    ],
    "social_science": [
        "survey", "interview", "qualitative", "quantitative",
        "socioeconomic", "demographics", "policy", "governance",
    ],
    "engineering": [
        "structural", "mechanical", "thermal", "fluid", "circuit",
        "fabrication", "manufacturing",
    ],
}


class TopicExtractor:
    """Extracts a TopicProfile from a paper's abstract text."""

    @classmethod
    def extract(cls, abstract_text: str, supplementary_text: str = "") -> TopicProfile:
        """
        Build a ``TopicProfile`` from the given abstract text.

        Parameters
        ----------
        abstract_text : str
            The primary text to analyse (the paper's abstract).
        supplementary_text : str, optional
            Additional text (e.g. first paragraph of introduction) to
            supplement a very short abstract.
        """
        profile = TopicProfile(abstract_text=abstract_text)

        if not abstract_text or not abstract_text.strip():
            logger.warning("Empty abstract text provided to TopicExtractor.")
            return profile

        # Supplement short abstracts
        text_to_analyse = abstract_text.strip()
        sentences = text_to_analyse.split(".")
        if len(sentences) < 3 and supplementary_text:
            text_to_analyse = f"{text_to_analyse} {supplementary_text.strip()}"
            logger.info("Abstract is very short; supplementing with additional text.")

        try:
            nlp = SentenceSegmenterService.get_nlp()
            doc = nlp(text_to_analyse)
        except Exception as e:
            logger.error(f"spaCy processing failed during topic extraction: {e}")
            return profile

        # ----- Step 1: Extract noun chunks ---------------------------------
        noun_chunks = cls._extract_noun_chunks(doc)

        # ----- Step 2: Extract named entities ------------------------------
        entities = cls._extract_entities(doc)

        # ----- Step 3: Build ranked keyword list ---------------------------
        all_candidates = noun_chunks + entities
        profile.keywords = cls._rank_keywords(all_candidates, max_keywords=settings.TOPIC_EXTRACTION_MAX_KEYWORDS)

        # ----- Step 4: Select top topics -----------------------------------
        profile.topics = profile.keywords[:settings.TOPIC_EXTRACTION_MAX_TOPICS]

        # ----- Step 5: Detect domain hint ----------------------------------
        profile.domain_hint = cls._detect_domain(text_to_analyse)

        # ----- Step 6: Generate search queries -----------------------------
        profile.search_queries = cls._generate_search_queries(profile)

        # ----- Step 7: Generate abstract embedding -------------------------
        try:
            from app.services.matcher import SemanticMatcher
            model = SemanticMatcher.get_model()
            embedding = model.encode(abstract_text, show_progress_bar=False)
            profile.embedding = embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate abstract embedding: {e}")

        return profile

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _extract_noun_chunks(cls, doc) -> list[str]:
        """Extract and filter noun chunks from spaCy doc."""
        chunks: list[str] = []
        for chunk in doc.noun_chunks:
            # Filter: keep tokens that are not stop words, not punctuation, alphabetic
            filtered_tokens = [
                token.text.lower()
                for token in chunk
                if not token.is_stop and not token.is_punct and token.is_alpha
            ]
            phrase = " ".join(filtered_tokens).strip()
            # Keep multi-word phrases (2–5 words) for specificity
            word_count = len(phrase.split())
            if 2 <= word_count <= 5 and phrase:
                chunks.append(phrase)

        return chunks

    @classmethod
    def _extract_entities(cls, doc) -> list[str]:
        """Extract named entities relevant to academic context."""
        relevant_labels = {"ORG", "PRODUCT", "EVENT", "WORK_OF_ART", "LAW", "GPE"}
        entities: list[str] = []
        for ent in doc.ents:
            if ent.label_ in relevant_labels:
                cleaned = ent.text.strip().lower()
                if len(cleaned) > 3 and cleaned not in entities:
                    entities.append(cleaned)
        return entities

    @classmethod
    def _rank_keywords(cls, candidates: list[str], max_keywords: int = 10) -> list[str]:
        """
        Rank keyword candidates by specificity.

        Specificity score = word_count * frequency_in_candidates / total_candidates
        Longer, more frequent phrases are ranked higher.
        """
        if not candidates:
            return []

        counts = Counter(candidates)
        total = len(candidates) if candidates else 1

        scored: list[tuple[str, float]] = []
        seen = set()
        for phrase, freq in counts.most_common():
            if phrase in seen:
                continue
            seen.add(phrase)
            word_count = len(phrase.split())
            # Specificity: longer phrases with higher frequency score better
            specificity = (word_count * freq) / total
            scored.append((phrase, specificity))

        # Sort by specificity descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return [phrase for phrase, _ in scored[:max_keywords]]

    @classmethod
    def _detect_domain(cls, text: str) -> str | None:
        """Detect the broad academic domain from text content."""
        text_lower = text.lower()
        domain_scores: dict[str, int] = {}

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                domain_scores[domain] = score

        if domain_scores:
            return max(domain_scores, key=domain_scores.get)
        return None

    @classmethod
    def _generate_search_queries(cls, profile: TopicProfile) -> list[str]:
        """
        Generate 3–5 search queries from the topic profile for use with
        academic APIs (arXiv, Semantic Scholar, Crossref, CORE).
        """
        queries: list[str] = []

        topics = profile.topics
        keywords = profile.keywords

        # Query 1: Top topic phrase (standalone)
        if topics:
            queries.append(topics[0])

        # Query 2: Top 2 topics joined
        if len(topics) >= 2:
            queries.append(f"{topics[0]} {topics[1]}")

        # Query 3: First topic + most specific keyword not already used
        if topics and len(keywords) > len(topics):
            extra_kw = keywords[len(topics)]
            queries.append(f"{topics[0]} {extra_kw}")

        # Query 4: Domain-specific query if domain is detected
        if profile.domain_hint and topics:
            queries.append(f"{profile.domain_hint.replace('_', ' ')} {topics[0]}")

        # Query 5: Second and third topics combined
        if len(topics) >= 3:
            queries.append(f"{topics[1]} {topics[2]}")

        # De-duplicate while preserving order
        seen = set()
        unique_queries: list[str] = []
        for q in queries:
            q_lower = q.lower().strip()
            if q_lower and q_lower not in seen:
                seen.add(q_lower)
                unique_queries.append(q)

        return unique_queries[:5]
