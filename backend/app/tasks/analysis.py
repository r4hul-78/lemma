import os
import logging
import asyncio
import threading
from backend.app.config import settings
from backend.app.tasks.celery_app import celery_app
from backend.app.services.extractor import DocumentExtractorService
from backend.app.services.segmenter import SentenceSegmenterService
from backend.app.services.matcher import DualTierMatcher

logger = logging.getLogger(__name__)

def run_async_in_thread(coro):
    """Runs a coroutine inside a separate thread to prevent event loop blockages in Celery Eager mode."""
    res = None
    err = None
    
    def target():
        nonlocal res, err
        try:
            res = asyncio.run(coro)
        except Exception as e:
            err = e
            
    t = threading.Thread(target=target)
    t.start()
    t.join()
    
    if err:
        raise err
    return res

@celery_app.task(bind=True, name="backend.app.tasks.analysis.analyze_document_task")
def analyze_document_task(self, file_path: str, original_filename: str) -> dict:
    """
    Background Celery task to parse a document, fetch web references, and perform plagiarism analysis.
    """
    logger.info(f"Starting analysis task for file: {original_filename} (temp path: {file_path})")
    job_id = self.request.id or "dummy_job"
    
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
        
        # 1. Ephemeral online candidate retrieval & caching
        if settings.ENABLE_ONLINE_RETRIEVAL:
            try:
                from backend.app.services.online_retriever import OnlineRetrieverService
                logger.info(f"Triggering online retrieval query generation for job: {job_id}")
                queries = OnlineRetrieverService.extract_search_queries(text)
                
                logger.info(f"Generated search queries: {queries}")
                candidates = run_async_in_thread(OnlineRetrieverService.get_online_candidates(queries))
                
                run_async_in_thread(OnlineRetrieverService.seed_ephemeral_candidates(job_id, candidates))
            except Exception as e:
                logger.error(f"Failed to fetch/cache online candidate papers: {e}")

        # 2. Run dual-tier plagiarism matcher
        matcher = DualTierMatcher()
        analysis_report = matcher.analyze_document(sentences_data, job_id=job_id)
        
        # Return complete results in the same structure as DocumentUploadResponse
        result = {
            "filename": original_filename,
            "text": text,
            "char_count": len(text),
            "sentence_count": len(sentences),
            "sentences": sentences,
            "analysis": analysis_report
        }
        return result
        
    except Exception as e:
        logger.error(f"Error in analyze_document_task: {str(e)}", exc_info=True)
        raise e
        
    finally:
        # 3. Clean up the temporary uploaded file from disk
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Successfully deleted temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {file_path}: {e}")
                
        # 4. Prune ephemeral database & Elasticsearch candidate records
        if settings.ENABLE_ONLINE_RETRIEVAL:
            try:
                from backend.app.services.online_retriever import OnlineRetrieverService
                OnlineRetrieverService.prune_cache(job_id)
            except Exception as e:
                logger.error(f"Failed to prune cache for job {job_id}: {e}")
