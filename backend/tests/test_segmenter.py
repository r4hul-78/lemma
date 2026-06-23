import pytest
from app.services.segmenter import SentenceSegmenterService

def test_segmenter_empty():
    assert SentenceSegmenterService.segment("") == []
    assert SentenceSegmenterService.segment("   ") == []

def test_segmenter_basic(sample_text):
    sentences = SentenceSegmenterService.segment(sample_text)
    
    assert len(sentences) == 4
    
    # Verify coordinates exactly match the sliced string
    for sent in sentences:
        start = sent["start_char"]
        end = sent["end_char"]
        text = sent["text"]
        
        # Slice original text
        sliced_text = sample_text[start:end]
        assert sliced_text == text, f"Mismatch: sliced '{sliced_text}' != expected '{text}'"

def test_segmenter_spacing_and_newlines():
    text = "  Hello world!   \n\n  This is another test.   "
    sentences = SentenceSegmenterService.segment(text)
    
    assert len(sentences) == 2
    
    assert sentences[0]["text"] == "Hello world!"
    assert sentences[1]["text"] == "This is another test."
    
    # Check offsets slice the text properly
    for sent in sentences:
        start = sent["start_char"]
        end = sent["end_char"]
        text_val = sent["text"]
        
        sliced = text[start:end]
        assert sliced == text_val, f"Mismatch: sliced '{sliced}' != expected '{text_val}'"
