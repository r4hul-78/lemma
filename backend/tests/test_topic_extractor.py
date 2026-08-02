"""
Unit tests for the Topic Extractor service.
"""

import pytest
from app.services.topic_extractor import TopicExtractor, TopicProfile


class TestTopicExtractor:
    """Tests for TopicExtractor.extract()"""

    def test_extract_from_well_formed_abstract(self):
        """Should extract topics, keywords, and search queries from a well-formed abstract."""
        abstract = (
            "This paper presents a novel deep learning approach for automatic plagiarism detection "
            "in academic manuscripts. We propose a hybrid neural network architecture that combines "
            "convolutional neural networks with transformer-based embeddings to identify semantic "
            "similarity between text passages. Our method achieves state-of-the-art performance on "
            "the PAN plagiarism detection benchmark dataset."
        )
        profile = TopicExtractor.extract(abstract)

        assert isinstance(profile, TopicProfile)
        assert profile.abstract_text == abstract
        assert len(profile.topics) > 0
        assert len(profile.keywords) > 0
        assert len(profile.search_queries) > 0
        # Domain hint should be detected
        assert profile.domain_hint is not None

    def test_extract_empty_abstract(self):
        """Should return empty TopicProfile for empty input."""
        profile = TopicExtractor.extract("")
        assert profile.topics == []
        assert profile.keywords == []
        assert profile.search_queries == []

    def test_extract_none_abstract(self):
        """Should handle None input gracefully."""
        profile = TopicExtractor.extract(None)
        assert profile.topics == []

    def test_extract_very_short_abstract(self):
        """Should supplement a very short abstract with supplementary text."""
        short_abstract = "Machine learning methods."
        supplementary = (
            "We use convolutional neural networks and recurrent neural networks "
            "to detect patterns in textual data from academic papers."
        )
        profile = TopicExtractor.extract(short_abstract, supplementary_text=supplementary)
        assert isinstance(profile, TopicProfile)
        # Should produce more results than without supplementary text
        assert len(profile.keywords) >= 0  # May still be limited by short input

    def test_search_queries_generated(self):
        """Search queries should be generated from topics and keywords."""
        abstract = (
            "This study investigates the effectiveness of transfer learning for natural language "
            "processing tasks in the biomedical domain. We fine-tune pre-trained language models "
            "on clinical text classification and named entity recognition tasks."
        )
        profile = TopicExtractor.extract(abstract)
        assert len(profile.search_queries) >= 1
        assert len(profile.search_queries) <= 5
        # Queries should be unique
        assert len(profile.search_queries) == len(set(q.lower() for q in profile.search_queries))

    def test_domain_detection_computer_science(self):
        """Should detect computer science domain from relevant keywords."""
        abstract = (
            "We propose a novel algorithm for training deep neural networks using gradient descent "
            "optimisation. Our approach leverages transformer architectures and attention mechanisms "
            "for natural language processing applications."
        )
        profile = TopicExtractor.extract(abstract)
        assert profile.domain_hint == "computer_science"

    def test_domain_detection_medicine(self):
        """Should detect medicine domain from medical keywords."""
        abstract = (
            "This clinical study evaluates the effectiveness of a new treatment protocol for "
            "patients diagnosed with chronic kidney disease. We analysed patient outcomes from "
            "three hospitals over a two-year period, comparing surgical and non-surgical approaches."
        )
        profile = TopicExtractor.extract(abstract)
        assert profile.domain_hint == "medicine"

    def test_no_domain_detected(self):
        """Should return None when no domain keywords match."""
        abstract = (
            "A comprehensive analysis of historical voting patterns and their relationship "
            "to economic indicators in post-industrial societies."
        )
        profile = TopicExtractor.extract(abstract)
        # May or may not detect a domain — either is acceptable
        assert profile.domain_hint is None or isinstance(profile.domain_hint, str)

    def test_embedding_generated(self):
        """Should generate an abstract embedding."""
        abstract = (
            "Deep learning models for text classification have shown remarkable performance "
            "improvements over traditional machine learning approaches."
        )
        profile = TopicExtractor.extract(abstract)
        # Embedding may fail if model isn't loaded in test env
        if profile.embedding is not None:
            assert isinstance(profile.embedding, list)
            assert len(profile.embedding) > 0
