import os
import logging
from backend.app.tasks.celery_app import celery_app
from backend.app.services.extractor import DocumentExtractorService
from backend.app.services.segmenter import SentenceSegmenterService
from backend.app.services.matcher import DualTierMatcher

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="backend.app.tasks.analysis.analyze_document_task")
def analyze_document_task(self, file_path: str, original_filename: str) -> dict:
    """
    Background Celery task to parse a document and perform plagiarism analysis.
    """
    logger.info(f"Starting analysis task for file: {original_filename} (temp path: {file_path})")
    try:
        # Read the file from disk
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Temporary file not found at: {file_path}")
            
        with open(file_path, "rb") as f:
            content = f.read()
        
        # Run extractor
        text = DocumentExtractorService.extract_text(original_filename, content)
        
        # Segment sentences
        sentences_data = SentenceSegmenterService.segment(text)
        
        # Format sentences
        sentences = [
            {
                "text": s["text"],
                "start_char": s["start_char"],
                "end_char": s["end_char"]
            }
            for s in sentences_data
        ]
        
        # Run dual-tier plagiarism matcher
        matcher = DualTierMatcher()
        analysis_report = matcher.analyze_document(sentences_data)
        
        # Return complete results in the same structure as DocumentUploadResponse
        result = {
            "filename": original_filename,
            "text": text,
            "char_count": len(text),
            "sentence_count": len(sentences),
            "sentences": sentences,
            "analysis": analysis_report
        }
        
        # Clean up the temporary uploaded file from disk
        try:
            os.remove(file_path)
            logger.info(f"Successfully deleted temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {file_path}: {e}")
            
        return result
        
    except Exception as e:
        logger.error(f"Error in analyze_document_task: {str(e)}", exc_info=True)
        # Attempt cleanup of the file if task failed
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temp file after task failure: {file_path}")
            except Exception:
                pass
        raise e
