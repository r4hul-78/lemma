"""
Section Parser Service

Parses document text into structural sections, identifies which sections
should be analyzed for plagiarism, and extracts the abstract using a
dual-strategy approach (regex/heading heuristics → LLM fallback).
"""

import re
import logging
from dataclasses import dataclass, field
from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical section name mapping
# ---------------------------------------------------------------------------
# Maps various heading text patterns to a normalised canonical name.
# Order matters: first match wins.

_HEADING_ALIASES: dict[str, list[str]] = {
    "abstract": [
        "abstract", "summary", "executive summary",
    ],
    "introduction": [
        "introduction", "background", "overview",
    ],
    "literature_review": [
        "literature review", "related work", "related works",
        "previous work", "state of the art", "prior work",
        "review of literature", "theoretical framework",
    ],
    "methods": [
        "methods", "methodology", "method", "materials and methods",
        "experimental setup", "experimental design", "research design",
        "research methodology", "study design", "data collection",
        "experimental method", "experimental methods",
    ],
    "results": [
        "results", "findings", "experimental results",
        "results and analysis", "data analysis",
    ],
    "discussion": [
        "discussion", "analysis", "interpretation",
        "results and discussion", "discussion and results",
        "discussion and analysis",
    ],
    "conclusion": [
        "conclusion", "conclusions", "concluding remarks",
        "summary and conclusion", "summary and conclusions",
        "final remarks", "closing remarks",
    ],
    "references": [
        "references", "bibliography", "works cited",
        "literature cited", "citations", "reference list",
    ],
    "acknowledgements": [
        "acknowledgements", "acknowledgments", "acknowledgement",
        "acknowledgment", "funding",
    ],
    "appendix": [
        "appendix", "appendices", "supplementary material",
        "supplementary materials", "supplementary data",
        "supporting information",
    ],
}

# Invert the mapping for O(1) look-up: alias → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in _HEADING_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias] = canonical


# ---------------------------------------------------------------------------
# Section analysability rules per paper type
# ---------------------------------------------------------------------------
# True  = section is analysable
# False = section is excluded from analysis
# The special key "__default__" is used for sections not listed.

_ANALYSABLE_RULES: dict[str, dict[str, bool]] = {
    "empirical": {
        "abstract": True,
        "introduction": True,
        "literature_review": True,
        "methods": True,
        "results": True,
        "discussion": True,
        "conclusion": True,
        "references": False,
        "acknowledgements": False,
        "appendix": False,
        "__default__": True,
    },
    "review": {
        "abstract": True,
        "introduction": True,
        "literature_review": True,
        "methods": False,
        "results": False,
        "discussion": True,
        "conclusion": True,
        "references": False,
        "acknowledgements": False,
        "appendix": False,
        "__default__": True,
    },
    "case_study": {
        "abstract": True,
        "introduction": True,
        "literature_review": True,
        "methods": True,
        "results": True,
        "discussion": True,
        "conclusion": True,
        "references": False,
        "acknowledgements": False,
        "appendix": False,
        "__default__": True,
    },
    "other": {
        "abstract": True,
        "introduction": True,
        "literature_review": True,
        "methods": True,
        "results": True,
        "discussion": True,
        "conclusion": True,
        "references": False,
        "acknowledgements": False,
        "appendix": False,
        "__default__": True,
    },
}

# Paper-type-specific relevance weights (0.0–1.0).  Higher means more
# likely to contain meaningful plagiarism for that paper type.
_RELEVANCE_WEIGHTS: dict[str, dict[str, float]] = {
    "empirical": {
        "abstract": 0.9,
        "introduction": 0.9,
        "literature_review": 1.0,
        "methods": 0.5,
        "results": 0.6,
        "discussion": 0.8,
        "conclusion": 0.7,
    },
    "review": {
        "abstract": 0.9,
        "introduction": 0.9,
        "literature_review": 1.0,
        "discussion": 0.8,
        "conclusion": 0.7,
    },
    "case_study": {
        "abstract": 0.9,
        "introduction": 0.9,
        "literature_review": 1.0,
        "methods": 0.7,
        "results": 0.7,
        "discussion": 0.8,
        "conclusion": 0.7,
    },
    "other": {
        "__default__": 0.8,
    },
}

# Stricter thresholds for specific sections in empirical papers
_SECTION_THRESHOLD_OVERRIDES: dict[str, dict[str, dict[str, float]]] = {
    "empirical": {
        "methods": {
            "lexical_threshold": settings.EMPIRICAL_METHODS_LEXICAL_THRESHOLD,
            "semantic_threshold": settings.EMPIRICAL_METHODS_SEMANTIC_THRESHOLD,
            "hybrid_threshold": settings.EMPIRICAL_METHODS_HYBRID_THRESHOLD,
        },
        "results": {
            "lexical_threshold": settings.EMPIRICAL_RESULTS_LEXICAL_THRESHOLD,
            "semantic_threshold": settings.EMPIRICAL_RESULTS_SEMANTIC_THRESHOLD,
            "hybrid_threshold": settings.EMPIRICAL_RESULTS_HYBRID_THRESHOLD,
        },
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """Represents one structural section of a parsed document."""
    name: str                                    # Canonical name
    heading_text: str                            # Original heading text
    content: str                                 # Raw text of the section body
    start_char: int                              # Absolute offset in full doc
    end_char: int                                # Absolute offset in full doc
    analyzable: bool = True                      # Should this section be checked?
    paper_type_relevance: float = 0.8            # Weight for this paper type
    threshold_override: dict | None = None       # Per-section threshold adjustments


# ---------------------------------------------------------------------------
# Heading-detection patterns
# ---------------------------------------------------------------------------

# Pattern 1: Numbered headings  ("1. Introduction", "2.1 Methods", etc.)
_RE_NUMBERED_HEADING = re.compile(
    r"^\s*(\d+\.?\d*\.?\d*)\s+(.+)$"
)

# Pattern 2: All-caps headings  ("INTRODUCTION", "RELATED WORK")
_RE_ALLCAPS_HEADING = re.compile(
    r"^([A-Z][A-Z\s\-&]{2,})$"
)

# Pattern 3: Known heading keywords (case-insensitive)
# Built dynamically from _ALIAS_TO_CANONICAL keys
_KNOWN_HEADINGS_LOWER: set[str] = set(_ALIAS_TO_CANONICAL.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SectionParser:
    """Parses document text into structural sections."""

    @classmethod
    def parse(cls, text: str, paper_type: str = "other") -> list[Section]:
        """
        Parse raw document text into a list of ``Section`` objects.

        If no headings are detected the entire document is returned as a
        single analysable "body" section.
        """
        if not text or not text.strip():
            return []

        paper_type = paper_type.lower() if paper_type else "other"
        if paper_type not in _ANALYSABLE_RULES:
            paper_type = "other"

        raw_sections = cls._detect_sections(text)

        if len(raw_sections) < 2:
            # Fallback: treat entire document as one "body" section
            return [
                Section(
                    name="body",
                    heading_text="",
                    content=text,
                    start_char=0,
                    end_char=len(text),
                    analyzable=True,
                    paper_type_relevance=0.8,
                    threshold_override=None,
                )
            ]

        sections: list[Section] = []
        seen_names: dict[str, int] = {}

        for raw in raw_sections:
            canonical = cls._normalise_heading(raw["heading"])
            if not canonical:
                canonical = "body"

            # De-duplicate section names
            if canonical in seen_names:
                seen_names[canonical] += 1
                canonical = f"{canonical}_{seen_names[canonical]}"
            else:
                seen_names[canonical] = 0

            # Determine analysability
            rules = _ANALYSABLE_RULES.get(paper_type, _ANALYSABLE_RULES["other"])
            # Strip dedup suffix for rule look-up
            base_name = canonical.rsplit("_", 1)[0] if re.match(r".*_\d+$", canonical) else canonical
            analyzable = rules.get(base_name, rules.get("__default__", True))

            # Determine relevance weight
            weights = _RELEVANCE_WEIGHTS.get(paper_type, _RELEVANCE_WEIGHTS["other"])
            relevance = weights.get(base_name, weights.get("__default__", 0.8))

            # Determine threshold overrides
            overrides = _SECTION_THRESHOLD_OVERRIDES.get(paper_type, {})
            threshold_override = overrides.get(base_name)

            sections.append(Section(
                name=canonical,
                heading_text=raw["heading"],
                content=raw["content"],
                start_char=raw["start_char"],
                end_char=raw["end_char"],
                analyzable=analyzable,
                paper_type_relevance=relevance,
                threshold_override=threshold_override,
            ))

        # Safety check: if < 3 sections detected from a paper type that
        # should have many, log a warning – the heading detection may have
        # missed headings.
        expected_min = 4 if paper_type in ("empirical", "review") else 3
        if len(sections) < expected_min:
            logger.warning(
                f"Only {len(sections)} sections detected for paper_type='{paper_type}'. "
                "Heading detection may have missed some sections. "
                "Consider reviewing document formatting."
            )

        return sections

    @classmethod
    def extract_abstract(cls, sections: list[Section], fallback_text: str = "") -> str:
        """
        Extract the abstract from parsed sections.

        Returns the abstract content if an "abstract" section is found.
        Returns empty string if no abstract is found (caller should try
        LLM fallback or first-N-sentences fallback).
        """
        for section in sections:
            base_name = section.name.rsplit("_", 1)[0] if re.match(r".*_\d+$", section.name) else section.name
            if base_name == "abstract":
                abstract_text = section.content.strip()
                if abstract_text:
                    return abstract_text

        return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _detect_sections(cls, text: str) -> list[dict]:
        """
        Detect section boundaries in the document text.

        Returns a list of dicts:
        [
            {
                "heading": str,      # original heading text
                "content": str,      # body text under this heading
                "start_char": int,   # absolute start in full document
                "end_char": int,     # absolute end in full document
            },
            ...
        ]
        """
        lines = text.split("\n")
        heading_positions: list[dict] = []  # (line_index, heading_text, char_offset)

        char_offset = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_heading = False

            if stripped and len(stripped) <= settings.SECTION_HEADING_MAX_LENGTH:
                # Test numbered heading
                m = _RE_NUMBERED_HEADING.match(stripped)
                if m:
                    heading_body = m.group(2).strip()
                    if len(heading_body) >= settings.SECTION_HEADING_MIN_LENGTH:
                        is_heading = True
                        stripped = heading_body

                # Test all-caps heading
                if not is_heading:
                    m = _RE_ALLCAPS_HEADING.match(stripped)
                    if m and len(stripped) >= settings.SECTION_HEADING_MIN_LENGTH:
                        is_heading = True

                # Test known heading keywords
                if not is_heading and stripped.lower() in _KNOWN_HEADINGS_LOWER:
                    is_heading = True

                # Test short line followed by blank line (potential heading)
                if (
                    not is_heading
                    and len(stripped) < 60
                    and len(stripped) >= settings.SECTION_HEADING_MIN_LENGTH
                    and i + 1 < len(lines)
                    and not lines[i + 1].strip()
                ):
                    # Only if the line looks like a title (starts with uppercase)
                    if stripped[0].isupper() and not stripped.endswith("."):
                        # Check it's not just a regular sentence
                        word_count = len(stripped.split())
                        if word_count <= 8:
                            is_heading = True

            if is_heading:
                heading_positions.append({
                    "line_index": i,
                    "heading_text": stripped,
                    "char_offset": char_offset,
                })

            char_offset += len(line) + 1  # +1 for \n

        if not heading_positions:
            return []

        # Build sections from heading positions
        sections: list[dict] = []
        total_len = len(text)

        # If there is content before the first heading, capture it as
        # a "preamble" section.
        first_heading_offset = heading_positions[0]["char_offset"]
        if first_heading_offset > 0:
            preamble = text[:first_heading_offset].strip()
            if preamble:
                sections.append({
                    "heading": "",
                    "content": preamble,
                    "start_char": 0,
                    "end_char": first_heading_offset,
                })

        for idx, hp in enumerate(heading_positions):
            heading_line = lines[hp["line_index"]]
            # Content starts after the heading line
            content_start = hp["char_offset"] + len(heading_line) + 1

            if idx + 1 < len(heading_positions):
                content_end = heading_positions[idx + 1]["char_offset"]
            else:
                content_end = total_len

            content = text[content_start:content_end].strip()

            sections.append({
                "heading": hp["heading_text"],
                "content": content,
                "start_char": hp["char_offset"],
                "end_char": content_end,
            })

        return sections

    @classmethod
    def _normalise_heading(cls, heading_text: str) -> str:
        """
        Normalise a heading string to its canonical section name.

        Returns empty string if the heading cannot be mapped.
        """
        if not heading_text:
            return ""

        cleaned = heading_text.strip().lower()
        # Remove leading numbers (e.g., "1." or "2.1")
        cleaned = re.sub(r"^\d+\.?\d*\.?\d*\s*", "", cleaned).strip()
        # Remove trailing colons
        cleaned = cleaned.rstrip(":")

        # Direct look-up
        if cleaned in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[cleaned]

        # Fuzzy: check if any alias is a substring of the heading
        for alias, canonical in _ALIAS_TO_CANONICAL.items():
            if alias in cleaned:
                return canonical

        return ""


def should_parse_sections(text: str) -> bool:
    """
    Determine if raw text input warrants section-level parsing.
    
    Returns True if text is long enough AND contains detectable section headings.
    """
    if len(text) < 1000:
        return False

    heading_patterns = [
        r"^\s*\d+\.?\d*\s+\w+",
        r"^[A-Z][A-Z\s]{3,}$",
        r"^\s*(Abstract|Introduction|Methods|Methodology|Results|Discussion|Conclusion|References)\s*$",
    ]
    for pattern in heading_patterns:
        if re.search(pattern, text, re.MULTILINE | re.IGNORECASE):
            return True

    return False
