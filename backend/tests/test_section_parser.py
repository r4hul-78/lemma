"""
Unit tests for the Section Parser service.
"""

import pytest
from app.services.section_parser import SectionParser, Section, should_parse_sections


class TestSectionParser:
    """Tests for SectionParser.parse()"""

    def test_parse_standard_paper(self):
        """Should detect standard section headings and split content correctly."""
        text = """Abstract
This paper presents a novel approach to plagiarism detection.

Introduction
Plagiarism is a serious issue in academia. This paper proposes a solution.

Methods
We used a dual-tier matching system combining BM25 and pgvector.

Results
Our system achieved 95% accuracy on the test dataset.

Discussion
The results demonstrate the effectiveness of our approach.

Conclusion
We have presented a plagiarism detection system that works well.

References
[1] Smith et al., 2023. Plagiarism Detection Systems.
[2] Jones et al., 2022. Semantic Similarity Methods."""

        sections = SectionParser.parse(text, paper_type="empirical")

        # Should find multiple sections
        assert len(sections) >= 6

        # Verify section names are canonical
        section_names = [s.name for s in sections]
        assert "abstract" in section_names
        assert "introduction" in section_names
        assert "methods" in section_names
        assert "references" in section_names

        # References should NOT be analyzable
        ref_section = next(s for s in sections if s.name == "references")
        assert ref_section.analyzable is False

        # Introduction should be analyzable
        intro_section = next(s for s in sections if s.name == "introduction")
        assert intro_section.analyzable is True

    def test_parse_no_headings(self):
        """Should return a single 'body' section when no headings are detected."""
        text = "This is just a plain paragraph of text with no headings at all. It contains several sentences about various topics. There is no structure to parse."
        sections = SectionParser.parse(text, paper_type="other")

        assert len(sections) == 1
        assert sections[0].name == "body"
        assert sections[0].analyzable is True
        assert sections[0].content == text

    def test_parse_empty_text(self):
        """Should return empty list for empty text."""
        assert SectionParser.parse("", paper_type="other") == []
        assert SectionParser.parse("   ", paper_type="other") == []
        assert SectionParser.parse(None, paper_type="other") == []

    def test_parse_numbered_headings(self):
        """Should detect numbered headings like '1. Introduction'."""
        text = """1. Introduction
This is the introduction section.

2. Methods
This describes the methodology used.

3. Results
Here are the results of our study.

4. References
[1] A reference entry."""

        sections = SectionParser.parse(text, paper_type="empirical")
        section_names = [s.name for s in sections]
        assert "introduction" in section_names
        assert "methods" in section_names
        assert "results" in section_names
        assert "references" in section_names

    def test_parse_allcaps_headings(self):
        """Should detect all-caps headings like 'INTRODUCTION'."""
        text = """ABSTRACT
A short abstract of the paper.

INTRODUCTION
The introduction to the paper.

RELATED WORK
Previous research in this area.

REFERENCES
[1] A citation."""

        sections = SectionParser.parse(text, paper_type="review")
        section_names = [s.name for s in sections]
        assert "abstract" in section_names
        assert "introduction" in section_names
        assert "literature_review" in section_names
        assert "references" in section_names

    def test_review_paper_skips_methods_results(self):
        """For review papers, methods and results sections should not be analyzable."""
        text = """Abstract
Review abstract text here.

Introduction
Introduction to the review.

Methods
Some methodology description.

Results
Some results description.

Discussion
Discussion of the review findings.

References
[1] Reference."""

        sections = SectionParser.parse(text, paper_type="review")

        methods = next((s for s in sections if s.name == "methods"), None)
        results = next((s for s in sections if s.name == "results"), None)
        discussion = next((s for s in sections if s.name == "discussion"), None)

        if methods:
            assert methods.analyzable is False
        if results:
            assert results.analyzable is False
        if discussion:
            assert discussion.analyzable is True

    def test_empirical_methods_has_threshold_overrides(self):
        """Empirical papers should have stricter thresholds for methods section."""
        text = """Abstract
Study abstract.

Introduction
Study introduction.

Methods
Study methodology described here.

Results
Study results presented.

References
[1] Reference."""

        sections = SectionParser.parse(text, paper_type="empirical")
        methods = next((s for s in sections if s.name == "methods"), None)

        assert methods is not None
        assert methods.threshold_override is not None
        assert methods.threshold_override["lexical_threshold"] > 0.70  # Stricter than default

    def test_references_always_excluded(self):
        """References should be excluded for all paper types."""
        for paper_type in ["empirical", "review", "case_study", "other"]:
            text = """Introduction
Some intro text.

References
[1] Some reference."""

            sections = SectionParser.parse(text, paper_type=paper_type)
            ref = next((s for s in sections if s.name == "references"), None)
            if ref:
                assert ref.analyzable is False, f"References should not be analyzable for {paper_type}"

    def test_acknowledgements_excluded(self):
        """Acknowledgements should be excluded."""
        text = """Introduction
Some content.

Acknowledgements
We thank our funding agency.

References
[1] Ref."""

        sections = SectionParser.parse(text, paper_type="empirical")
        ack = next((s for s in sections if s.name == "acknowledgements"), None)
        if ack:
            assert ack.analyzable is False

    def test_duplicate_section_names(self):
        """Should deduplicate section names with index suffix."""
        text = """Discussion
First discussion section.

Discussion
Second discussion section."""

        sections = SectionParser.parse(text, paper_type="other")
        names = [s.name for s in sections]
        # Should have deduplication
        assert len(set(names)) == len(names)

    def test_invalid_paper_type_defaults_to_other(self):
        """Invalid paper_type should fall back to 'other'."""
        text = """Introduction
Some text.

Conclusion
Some conclusion."""

        sections = SectionParser.parse(text, paper_type="nonexistent_type")
        assert len(sections) >= 1  # Should still parse successfully


class TestExtractAbstract:
    """Tests for SectionParser.extract_abstract()"""

    def test_extract_abstract_found(self):
        """Should return abstract content when section is present."""
        sections = [
            Section(name="abstract", heading_text="Abstract", content="This is the abstract.",
                    start_char=0, end_char=50),
            Section(name="introduction", heading_text="Introduction", content="Intro text.",
                    start_char=50, end_char=100),
        ]
        result = SectionParser.extract_abstract(sections)
        assert result == "This is the abstract."

    def test_extract_abstract_not_found(self):
        """Should return empty string when no abstract section exists."""
        sections = [
            Section(name="introduction", heading_text="Introduction", content="Intro text.",
                    start_char=0, end_char=50),
        ]
        result = SectionParser.extract_abstract(sections)
        assert result == ""

    def test_extract_abstract_empty_content(self):
        """Should return empty string when abstract section has empty content."""
        sections = [
            Section(name="abstract", heading_text="Abstract", content="   ",
                    start_char=0, end_char=10),
        ]
        result = SectionParser.extract_abstract(sections)
        assert result == ""


class TestShouldParseSections:
    """Tests for should_parse_sections()"""

    def test_short_text_returns_false(self):
        """Text shorter than 1000 chars should not be parsed for sections."""
        text = "Short text without any headings."
        assert should_parse_sections(text) is False

    def test_long_text_with_headings_returns_true(self):
        """Long text with detectable headings should trigger section parsing."""
        text = "x " * 600 + "\nIntroduction\n" + "y " * 100
        assert should_parse_sections(text) is True

    def test_long_text_without_headings_returns_false(self):
        """Long text without any heading patterns should not trigger section parsing."""
        text = ("This is a long paragraph without any section headings. " * 50)
        assert should_parse_sections(text) is False
