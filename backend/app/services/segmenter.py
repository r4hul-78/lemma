import spacy
from app.config import settings

class SentenceSegmenterService:
    _nlp = None

    @classmethod
    def get_nlp(cls):
        """Loads and returns the spaCy NLP model as a singleton, optimizing components."""
        if cls._nlp is None:
            # Disable unnecessary components to improve performance
            disable_components = ["ner", "lemmatizer"]
            try:
                cls._nlp = spacy.load(settings.SPACY_MODEL, disable=disable_components)
            except OSError:
                # If model is not found, raise a friendly error
                raise RuntimeError(
                    f"spaCy model '{settings.SPACY_MODEL}' not found. "
                    f"Please run 'python -m spacy download {settings.SPACY_MODEL}' to install it."
                )
        return cls._nlp

    @classmethod
    def segment(cls, text: str) -> list[dict]:
        """
        Segments the text into sentences and returns a list of dictionaries with 
        absolute start and end character offsets.
        
        Output format:
        [
            {
                "text": "Sentence text.",
                "start_char": 0,
                "end_char": 14
            },
            ...
        ]
        """
        if not text or not text.strip():
            return []

        nlp = cls.get_nlp()
        doc = nlp(text)

        sentences = []
        for sent in doc.sents:
            # We strip trailing/leading whitespace from the text but keep original coordinates
            # Wait, if we strip whitespace, does start_char/end_char map to the stripped text?
            # It's better to preserve the coordinates matching the exact text or map them correctly.
            # Let's keep the raw sentence span coordinates and text as is, or strip but adjust offsets.
            # Actually, standard is to preserve exact start/end char in the original text, and include the actual matching substring.
            # Let's check: if we keep the raw sentence text, it may contain trailing newlines/spaces.
            # So let's save the exact text and exact start_char/end_char.
            sent_text = sent.text
            start = sent.start_char
            end = sent.end_char
            
            # To be even cleaner, we can trim whitespace and adjust start/end character offsets accordingly.
            # Let's adjust for leading whitespace
            leading_spaces = len(sent_text) - len(sent_text.lstrip())
            # Let's adjust for trailing whitespace
            trailing_spaces = len(sent_text) - len(sent_text.rstrip())
            
            final_start = start + leading_spaces
            final_end = end - trailing_spaces
            final_text = sent_text.strip()
            
            if final_text:
                sentences.append({
                    "text": final_text,
                    "start_char": final_start,
                    "end_char": final_end
                })
                
        return sentences
