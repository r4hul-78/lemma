import os
import logging
import asyncio
import threading
from app.config import settings
from app.tasks.celery_app import celery_app
from app.services.extractor import DocumentExtractorService
from app.services.segmenter import SentenceSegmenterService
from app.services.matcher import DualTierMatcher
from app.services.section_parser import SectionParser, should_parse_sections

# [DEBUG-SECTION] — To remove: delete this import line
from app.debug_logger import log_pipeline_step, log_data_exchange, log_section_result
# [/DEBUG-SECTION]

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


def _get_first_n_sentences(text: str, n: int = 5) -> str:
    """Extract the first N sentences from text as a pseudo-abstract fallback."""
    sentences = SentenceSegmenterService.segment(text)
    first_n = sentences[:n]
    return " ".join(s["text"] for s in first_n)


def _extract_abstract_with_fallbacks(sections, text: str) -> str:
    """
    Extract abstract using the three-tier fallback chain:
    1. Regex/heading-based extraction from parsed sections
    2. LLM-based extraction via Ollama
    3. First N sentences as pseudo-abstract
    """
    # Tier 1: Regex/heading-based
    abstract = SectionParser.extract_abstract(sections, fallback_text=text)
    if abstract:
        logger.info("Abstract extracted via heading-based heuristics.")
        return abstract

    # Tier 2: LLM-based via Ollama
    try:
        from app.services.llm import LLMService
        excerpt = text[:2000]
        abstract = run_async_in_thread(LLMService.extract_abstract(excerpt))
        if abstract:
            logger.info("Abstract extracted via LLM fallback.")
            return abstract
    except Exception as e:
        logger.warning(f"LLM abstract extraction failed: {e}")

    # Tier 3: First N sentences
    abstract = _get_first_n_sentences(text, n=settings.ABSTRACT_FALLBACK_SENTENCES)
    if abstract:
        logger.info(f"Using first {settings.ABSTRACT_FALLBACK_SENTENCES} sentences as pseudo-abstract.")
    return abstract


@celery_app.task(bind=True, name="app.tasks.analysis.analyze_document_task")
def analyze_document_task(self, file_path: str, original_filename: str, paper_type: str = "other", match_type: str = "hybrid") -> dict:
    """
    Background Celery task to parse a document, extract topics from abstract,
    fetch web references, and perform section-aware plagiarism analysis.
    """
    logger.info(f"Starting analysis task for file: {original_filename} (temp path: {file_path}, paper_type: {paper_type}, match_type: {match_type})")
    job_id = self.request.id or "dummy_job"
    
    try:
        # 1. Read the file from disk
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Temporary file not found at: {file_path}")
            
        with open(file_path, "rb") as f:
            content = f.read()
        
        # 2. Extract raw text
        text = DocumentExtractorService.extract_text(original_filename, content)
        # [DEBUG-SECTION]
        log_pipeline_step("Text Extraction", filename=original_filename, char_count=len(text), text_preview=text[:200])
        # [/DEBUG-SECTION]
        
        # 3. Parse sections (if enabled and text is long enough)
        use_sections = settings.SECTION_PARSER_ENABLED and should_parse_sections(text)
        if use_sections:
            sections = SectionParser.parse(text, paper_type=paper_type)
            logger.info(f"Parsed {len(sections)} sections (paper_type={paper_type})")
        else:
            sections = SectionParser.parse(text, paper_type=paper_type)
            if len(sections) < 2:
                use_sections = False
                logger.info("No sections detected; using full-document analysis.")
        # [DEBUG-SECTION]
        log_pipeline_step("Section Parsing",
            paper_type=paper_type,
            use_sections=use_sections,
            sections_found=len(sections),
            section_names=[{"name": s.name, "analyzable": s.analyzable, "chars": len(s.content), "threshold_override": bool(s.threshold_override)} for s in sections],
        )
        # [/DEBUG-SECTION]

        # 4. Extract abstract (with fallback chain)
        abstract = _extract_abstract_with_fallbacks(sections, text)
        # [DEBUG-SECTION]
        log_pipeline_step("Abstract Extraction", abstract_length=len(abstract), abstract_preview=abstract[:200])
        # [/DEBUG-SECTION]

        # 5. Build topic profile from abstract
        topic_profile = None
        try:
            from app.services.topic_extractor import TopicExtractor
            # For short abstracts, supplement with intro text
            supplementary = ""
            if use_sections:
                for s in sections:
                    if s.name == "introduction":
                        intro_sentences = SentenceSegmenterService.segment(s.content)
                        supplementary = " ".join(sent["text"] for sent in intro_sentences[:3])
                        break
            topic_profile = TopicExtractor.extract(abstract, supplementary_text=supplementary)
            logger.info(f"Topic profile: topics={topic_profile.topics}, domain={topic_profile.domain_hint}")
            # [DEBUG-SECTION]
            log_pipeline_step("Topic Extraction",
                topics=topic_profile.topics,
                keywords=topic_profile.keywords,
                domain_hint=topic_profile.domain_hint,
                search_queries=topic_profile.search_queries,
                embedding_dims=len(topic_profile.embedding) if topic_profile.embedding else 0,
            )
            # [/DEBUG-SECTION]
        except Exception as e:
            logger.error(f"Topic extraction failed: {e}")
        
        # 6. Online retrieval using topic profile (or fallback to full-text)
        if settings.ENABLE_ONLINE_RETRIEVAL:
            try:
                from app.services.online_retriever import OnlineRetrieverService
                
                if topic_profile and topic_profile.search_queries:
                    logger.info(f"Using abstract-driven queries: {topic_profile.search_queries}")
                    candidates = run_async_in_thread(
                        OnlineRetrieverService.get_online_candidates_with_relevance(topic_profile)
                    )
                else:
                    # Fallback to legacy full-text query extraction
                    logger.info("Falling back to full-text query extraction.")
                    queries = OnlineRetrieverService.extract_search_queries(text)
                    logger.info(f"Generated search queries: {queries}")
                    candidates = run_async_in_thread(
                        OnlineRetrieverService.get_online_candidates(queries)
                    )
                
                # [DEBUG-SECTION]
                log_pipeline_step("Online Retrieval Complete",
                    total_candidates=len(candidates),
                    candidate_sources=[c.get("source", "unknown")[:40] for c in candidates[:10]],
                    candidates_with_fulltext=sum(1 for c in candidates if len(c.get("text", "")) > 500),
                    candidates_with_pdf_url=sum(1 for c in candidates if c.get("pdf_url")),
                )
                # [/DEBUG-SECTION]

                run_async_in_thread(
                    OnlineRetrieverService.seed_ephemeral_candidates(job_id, candidates)
                )
                # [DEBUG-SECTION]
                log_data_exchange("OnlineRetriever", "PostgreSQL",
                    "ephemeral candidate sentences", record_count=len(candidates),
                    sample={"first_title": candidates[0]["title"] if candidates else "(none)"})
                # [/DEBUG-SECTION]
            except Exception as e:
                logger.error(f"Failed to fetch/cache online candidate papers: {e}")

        # 7. Run analysis : section-aware or full-document
        matcher = DualTierMatcher()
        
        if use_sections and len(sections) >= 2:
            analysis_report = _analyze_by_sections(matcher, sections, job_id, paper_type, topic_profile, match_type=match_type)
        else:
            # Full-document analysis (legacy path)
            sentences_data = SentenceSegmenterService.segment(text)
            analysis_report = matcher.analyze_document(sentences_data, job_id=job_id, match_type=match_type)
            # Wrap in enhanced format
            analysis_report = _wrap_legacy_report(analysis_report, paper_type, topic_profile, text)

        # 8. Build response
        sentences_data = SentenceSegmenterService.segment(text)
        sentences = [
            {
                "text": s["text"],
                "start_char": s["start_char"],
                "end_char": s["end_char"],
            }
            for s in sentences_data
        ]
        
        result = {
            "filename": original_filename,
            "text": text,
            "char_count": len(text),
            "sentence_count": len(sentences),
            "sentences": sentences,
            "analysis": analysis_report,
        }
        # [DEBUG-SECTION]
        log_pipeline_step("Final Report",
            plagiarism_score=analysis_report.get("plagiarism_score", 0),
            total_sentences=analysis_report.get("total_sentences", 0),
            plagiarized_count=analysis_report.get("plagiarized_sentences_count", 0),
            sections_analyzed=analysis_report.get("sections_analyzed", 0),
            sections_skipped=analysis_report.get("sections_skipped", 0),
            skipped_names=analysis_report.get("skipped_section_names", []),
        )
        # [/DEBUG-SECTION]
        return result
        
    except Exception as e:
        logger.error(f"Error in analyze_document_task: {str(e)}", exc_info=True)
        raise e
        
    finally:
        # Clean up the temporary uploaded file from disk
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Successfully deleted temp file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {file_path}: {e}")
                
        # Prune ephemeral database candidate records
        if settings.ENABLE_ONLINE_RETRIEVAL:
            try:
                from app.services.online_retriever import OnlineRetrieverService
                OnlineRetrieverService.prune_cache(job_id)
            except Exception as e:
                logger.error(f"Failed to prune cache for job {job_id}: {e}")


def _analyze_by_sections(matcher, sections, job_id, paper_type, topic_profile, match_type: str = "hybrid"):
    """
    Analyze each analyzable section independently, applying per-section
    threshold overrides, then aggregate results.
    """
    section_results = []
    total_sentences = 0
    total_plagiarized = 0
    total_lexical = 0
    total_semantic = 0
    total_hybrid = 0
    all_matches = []
    sections_analyzed = 0
    sections_skipped = 0
    skipped_names = []

    for section in sections:
        if not section.analyzable:
            sections_skipped += 1
            skipped_names.append(section.name)
            section_results.append({
                "section_name": section.name,
                "section_heading": section.heading_text,
                "analyzable": False,
                "sentence_count": 0,
                "plagiarized_count": 0,
                "plagiarism_score": 0.0,
                "matches": [],
            })
            continue

        # Segment section content
        sentences = SentenceSegmenterService.segment(section.content)
        if not sentences:
            section_results.append({
                "section_name": section.name,
                "section_heading": section.heading_text,
                "analyzable": True,
                "sentence_count": 0,
                "plagiarized_count": 0,
                "plagiarism_score": 0.0,
                "matches": [],
            })
            continue

        # Re-map char offsets to absolute document positions
        for s in sentences:
            s["start_char"] += section.start_char
            s["end_char"] += section.start_char

        # Apply section-specific threshold overrides
        thresholds = section.threshold_override or {}
        section_report = matcher.analyze_document(
            sentences,
            lexical_threshold=thresholds.get("lexical_threshold"),
            semantic_threshold=thresholds.get("semantic_threshold"),
            job_id=job_id,
            match_type=match_type
        )

        section_sentence_count = section_report.get("total_sentences", 0)
        section_plagiarized = section_report.get("plagiarized_sentences_count", 0)
        section_score = section_report.get("plagiarism_score", 0.0)

        total_sentences += section_sentence_count
        total_plagiarized += section_plagiarized
        total_lexical += section_report.get("lexical_matches_count", 0)
        total_semantic += section_report.get("semantic_matches_count", 0)
        total_hybrid += section_report.get("hybrid_matches_count", 0)
        all_matches.extend(section_report.get("matches", []))
        sections_analyzed += 1

        section_results.append({
            "section_name": section.name,
            "section_heading": section.heading_text,
            "analyzable": True,
            "sentence_count": section_sentence_count,
            "plagiarized_count": section_plagiarized,
            "plagiarism_score": section_score,
            "matches": section_report.get("matches", []),
        })
        # [DEBUG-SECTION]
        log_section_result(section.name, analyzable=True,
            sentence_count=section_sentence_count, plagiarized_count=section_plagiarized, score=section_score)
        # [/DEBUG-SECTION]

    overall_score = (total_plagiarized / total_sentences) if total_sentences > 0 else 0.0

    # Build topic info
    topic_info = {"topics": [], "keywords": [], "domain_hint": None}
    if topic_profile:
        topic_info = {
            "topics": topic_profile.topics,
            "keywords": topic_profile.keywords,
            "domain_hint": topic_profile.domain_hint,
        }

    return {
        "plagiarism_score": overall_score,
        "total_sentences": total_sentences,
        "plagiarized_sentences_count": total_plagiarized,
        "lexical_matches_count": total_lexical,
        "semantic_matches_count": total_semantic,
        "hybrid_matches_count": total_hybrid,
        "matches": all_matches,
        "paper_type": paper_type,
        "topics": topic_info,
        "sections": section_results,
        "sections_analyzed": sections_analyzed,
        "sections_skipped": sections_skipped,
        "skipped_section_names": skipped_names,
    }


def _wrap_legacy_report(report, paper_type, topic_profile, text):
    """
    Wrap a legacy flat analysis report in the enhanced format for
    backward compatibility when section parsing is not used.
    """
    topic_info = {"topics": [], "keywords": [], "domain_hint": None}
    if topic_profile:
        topic_info = {
            "topics": topic_profile.topics,
            "keywords": topic_profile.keywords,
            "domain_hint": topic_profile.domain_hint,
        }

    body_section = {
        "section_name": "body",
        "section_heading": "",
        "analyzable": True,
        "sentence_count": report.get("total_sentences", 0),
        "plagiarized_count": report.get("plagiarized_sentences_count", 0),
        "plagiarism_score": report.get("plagiarism_score", 0.0),
        "matches": report.get("matches", []),
    }

    report["paper_type"] = paper_type
    report["topics"] = topic_info
    report["sections"] = [body_section]
    report["sections_analyzed"] = 1
    report["sections_skipped"] = 0
    report["skipped_section_names"] = []

    return report

