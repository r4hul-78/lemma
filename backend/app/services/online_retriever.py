import logging
import asyncio
import io
import httpx
import xml.etree.ElementTree as ET
from collections import Counter
from app.config import settings
from app.services.segmenter import SentenceSegmenterService
from app.services.database import DatabaseService
from app.services.matcher import SemanticMatcher

logger = logging.getLogger(__name__)

# [DEBUG-SECTION] — To remove: delete this import line
from app.debug_logger import log_api_call, log_data_exchange
# [/DEBUG-SECTION]

class OnlineRetrieverService:
    """Manages dynamic query generation, external academic API fetching, and JIT ephemeral caching."""

    @classmethod
    def extract_search_queries(cls, text: str, num_queries: int = 3) -> list[str]:
        """
        Analyzes document text using spaCy to extract high-entropy phrases for searching external APIs,
        distributing candidate selection across different parts of the document.
        """
        if not text or not text.strip():
            return []

        try:
            nlp = SentenceSegmenterService.get_nlp()
            doc = nlp(text)
            
            # Group noun chunks by sentence index
            sentences = list(doc.sents)
            sent_chunks = []
            for i, sent in enumerate(sentences):
                chunks_in_sent = []
                for chunk in sent.noun_chunks:
                    chunk_clean = " ".join([
                        token.text.lower() 
                        for token in chunk 
                        if not token.is_stop and not token.is_punct and token.is_alpha
                    ]).strip()
                    
                    words = chunk_clean.split()
                    if 2 <= len(words) <= 4 and chunk_clean:
                        chunks_in_sent.append(chunk_clean)
                if chunks_in_sent:
                    sent_chunks.append((i, chunks_in_sent))
            
            queries = []
            if sent_chunks:
                num_sents = len(sent_chunks)
                if num_sents <= num_queries:
                    # Pick the longest chunk from each sentence
                    for _, chunks in sent_chunks:
                        chunks.sort(key=len, reverse=True)
                        for c in chunks:
                            if c not in queries:
                                queries.append(c)
                                break
                else:
                    # Distribute chunk selection across the document sentences
                    indices_to_pick = []
                    if num_queries == 1:
                        indices_to_pick = [0]
                    else:
                        for i in range(num_queries):
                            idx = int(i * (num_sents - 1) / (num_queries - 1))
                            if idx not in indices_to_pick:
                                indices_to_pick.append(idx)
                                
                    for idx in indices_to_pick:
                        if idx < len(sent_chunks):
                            chunks = sent_chunks[idx][1]
                            chunks.sort(key=len, reverse=True)
                            for c in chunks:
                                if c not in queries:
                                    queries.append(c)
                                    break

            # Fallback if we don't have enough queries
            if len(queries) < num_queries:
                all_chunks = []
                for _, chunks in sent_chunks:
                    all_chunks.extend(chunks)
                counts = Counter(all_chunks)
                for item, _ in counts.most_common():
                    if len(queries) >= num_queries:
                        break
                    if item not in queries:
                        queries.append(item)

            # Fallback to frequent words if we still don't have enough queries
            if len(queries) < num_queries:
                words = [
                    token.text.lower() 
                    for token in doc 
                    if not token.is_stop and token.is_alpha and len(token.text) > 4
                ]
                word_counts = Counter(words)
                for word, _ in word_counts.most_common(num_queries * 2):
                    if len(queries) >= num_queries:
                        break
                    if word not in queries:
                        queries.append(word)

            # Absolute fallback: first few words of text
            if not queries:
                fallback_words = [w for w in text.split() if w.isalpha()][:5]
                if fallback_words:
                    queries.append(" ".join(fallback_words).lower())

            return queries[:num_queries]
        except Exception as e:
            logger.error(f"Failed to extract search queries from document: {e}")
            return []

    @classmethod
    def extract_search_queries_from_profile(cls, profile) -> list[str]:
        """
        Generates search queries directly from a TopicProfile object,
        prioritizing exact paper title/heading phrases to find exact matches online.
        """
        queries = []
        
        # Include first ~12 words of abstract (contains paper title/topic)
        if profile.abstract_text:
            first_line = profile.abstract_text.strip().split("\n")[0]
            words = [w for w in first_line.split() if len(w) > 2][:12]
            if len(words) >= 3:
                queries.append(" ".join(words))

        if profile.search_queries:
            for q in profile.search_queries:
                if q not in queries:
                    queries.append(q)

        if profile.topics:
            if profile.topics[0] not in queries:
                queries.append(profile.topics[0])
            if len(profile.topics) >= 2:
                q2 = f"{profile.topics[0]} {profile.topics[1]}"
                if q2 not in queries:
                    queries.append(q2)

        if profile.keywords:
            for kw in profile.keywords:
                if kw not in queries and len(queries) < 6:
                    queries.append(kw)

        return queries[:6]

    @classmethod
    async def fetch_arxiv_candidates(cls, query: str, limit: int = 15) -> list[dict]:
        """Queries the arXiv API for matching academic preprints with retries."""
        url = "https://export.arxiv.org/api/query"
        # Sanitize query for arXiv API syntax
        clean_query = query.replace('"', '').replace("'", "")
        params = {
            "search_query": f'all:{clean_query}',
            "max_results": limit
        }
        
        max_retries = 3
        backoff = 1.5
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    response = await client.get(url, params=params)
                    if response.status_code == 200:
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        root = ET.fromstring(response.content)
                        entries = root.findall('atom:entry', ns)
                        
                        candidates = []
                        for entry in entries:
                            title_elem = entry.find('atom:title', ns)
                            summary_elem = entry.find('atom:summary', ns)
                            id_elem = entry.find('atom:id', ns)
                            
                            if title_elem is None or summary_elem is None or id_elem is None:
                                continue
                                
                            title = title_elem.text.strip().replace("\n", " ")
                            abstract = summary_elem.text.strip().replace("\n", " ")
                            paper_url = id_elem.text.strip()
                            paper_id = paper_url.split('/abs/')[-1].split('v')[0]
                            
                            authors = [
                                auth.find('atom:name', ns).text.strip() 
                                for auth in entry.findall('atom:author', ns) 
                                if auth.find('atom:name', ns) is not None
                            ]
                            author_str = ", ".join(authors) if authors else "N/A"

                            # Check for PDF link
                            pdf_url = None
                            for link in entry.findall('atom:link', ns):
                                if link.get('title') == 'pdf' or (link.get('type') == 'application/pdf'):
                                    pdf_url = link.get('href')
                                    break
                            if not pdf_url:
                                # arXiv PDF URL convention
                                pdf_url = paper_url.replace('/abs/', '/pdf/') + '.pdf'
                            
                            candidates.append({
                                "doc_id": f"arxiv_{paper_id}",
                                "title": title,
                                "author": author_str,
                                "source": f"arXiv Preprint ({paper_url})",
                                "text": abstract,
                                "pdf_url": pdf_url,
                            })
                        # [DEBUG-SECTION]
                        log_api_call("arXiv", url, params=params, response_status=200, result_count=len(candidates))
                        # [/DEBUG-SECTION]
                        return candidates
                    elif response.status_code == 429:
                        wait_time = backoff * (2 ** attempt)
                        logger.warning(f"arXiv API returned 429. Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(f"arXiv API returned status code {response.status_code}")
                        return []
            except Exception as e:
                logger.error(f"Failed to fetch candidates from arXiv for query '{query}': {e}")
                return []
        return []

    @classmethod
    async def fetch_semantic_scholar_candidates(cls, query: str, limit: int = 15) -> list[dict]:
        """Queries the Semantic Scholar search API for matching academic papers with retries."""
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,authors,venue,year,abstract,openAccessPdf"
        }
        
        headers = {}
        has_key = False
        if settings.SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY
            has_key = True
            
        max_retries = 3 if has_key else 1
        backoff = 1.5
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    response = await client.get(url, params=params, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        papers = data.get("data", [])
                        
                        candidates = []
                        for paper in papers:
                            paper_id = paper.get("paperId")
                            title = paper.get("title")
                            abstract = paper.get("abstract") or title
                            
                            if not paper_id or not title:
                                continue
                                
                            authors = [auth.get("name") for auth in paper.get("authors", []) if auth.get("name")]
                            author_str = ", ".join(authors) if authors else "N/A"
                            
                            venue = paper.get("venue", "Unknown Venue")
                            year = paper.get("year", "N/A")

                            # Check for open-access PDF
                            pdf_url = None
                            oa_pdf = paper.get("openAccessPdf")
                            if oa_pdf and isinstance(oa_pdf, dict):
                                pdf_url = oa_pdf.get("url")
                            
                            candidates.append({
                                "doc_id": f"semschol_{paper_id}",
                                "title": title,
                                "author": author_str,
                                "source": f"{venue}, {year}",
                                "text": abstract,
                                "pdf_url": pdf_url,
                            })
                        # [DEBUG-SECTION]
                        log_api_call("Semantic Scholar", url, params=params, response_status=200, result_count=len(candidates))
                        # [/DEBUG-SECTION]
                        return candidates
                    elif response.status_code == 429:
                        if not has_key:
                            logger.warning("Semantic Scholar API returned 429 (unauthenticated). Skipping retries to avoid timeout.")
                            return []
                        wait_time = backoff * (2 ** attempt)
                        logger.warning(f"Semantic Scholar API returned 429. Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(f"Semantic Scholar API returned status code {response.status_code}: {response.text}")
                        return []
            except Exception as e:
                logger.error(f"Failed to fetch candidates from Semantic Scholar for query '{query}': {e}")
                return []
        return []

    @classmethod
    async def fetch_crossref_candidates(cls, query: str, limit: int = 15) -> list[dict]:
        """Queries the Crossref API for matching published works with DOI metadata."""
        url = "https://api.crossref.org/works"
        params = {
            "query": query,
            "rows": limit,
            "select": "DOI,title,author,container-title,published-print,abstract",
        }
        headers = {
            "User-Agent": "Lemma/1.0 (mailto:lemma@plagiarism-checker.local)",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("message", {}).get("items", [])

                    candidates = []
                    for item in items:
                        doi = item.get("DOI")
                        titles = item.get("title", [])
                        title = titles[0] if titles else None
                        abstract = item.get("abstract", "")

                        if not doi or not title:
                            continue

                        # Crossref abstracts can contain JATS XML tags – strip them
                        if abstract:
                            import re
                            abstract = re.sub(r"<[^>]+>", "", abstract).strip()

                        if not abstract:
                            abstract = title

                        authors_raw = item.get("author", [])
                        author_parts = []
                        for a in authors_raw:
                            given = a.get("given", "")
                            family = a.get("family", "")
                            if family:
                                author_parts.append(f"{given} {family}".strip())
                        author_str = ", ".join(author_parts) if author_parts else "N/A"

                        container = item.get("container-title", [])
                        venue = container[0] if container else "Unknown Venue"
                        pub_date = item.get("published-print", {}).get("date-parts", [[]])
                        year = pub_date[0][0] if pub_date and pub_date[0] else "N/A"

                        candidates.append({
                            "doc_id": f"crossref_{doi.replace('/', '_')}",
                            "title": title,
                            "author": author_str,
                            "source": f"{venue}, {year} (DOI: {doi})",
                            "text": abstract,
                            "pdf_url": None,
                        })
                    # [DEBUG-SECTION]
                    log_api_call("Crossref", url, params=params, response_status=200, result_count=len(candidates))
                    # [/DEBUG-SECTION]
                    return candidates
                else:
                    logger.warning(f"Crossref API returned status code {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to fetch candidates from Crossref for query '{query}': {e}")
            return []

    @classmethod
    async def fetch_core_candidates(cls, query: str, limit: int = 15) -> list[dict]:
        """Queries the CORE API for matching open-access papers with full-text links."""
        url = f"{settings.CORE_API_URL}/search/works"
        params = {
            "q": query,
            "limit": limit,
        }
        headers = {}
        if settings.CORE_API_KEY:
            headers["Authorization"] = f"Bearer {settings.CORE_API_KEY}"

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])

                    candidates = []
                    for item in results:
                        core_id = item.get("id")
                        title = item.get("title")
                        abstract = item.get("abstract", "")

                        if not core_id or not title or not abstract:
                            continue

                        authors_raw = item.get("authors", [])
                        if isinstance(authors_raw, list):
                            author_parts = []
                            for a in authors_raw:
                                if isinstance(a, dict):
                                    author_parts.append(a.get("name", ""))
                                elif isinstance(a, str):
                                    author_parts.append(a)
                            author_str = ", ".join(p for p in author_parts if p) or "N/A"
                        else:
                            author_str = "N/A"

                        year = item.get("yearPublished", "N/A")
                        download_url = item.get("downloadUrl") or item.get("sourceFulltextUrls", [None])[0] if item.get("sourceFulltextUrls") else None

                        candidates.append({
                            "doc_id": f"core_{core_id}",
                            "title": title,
                            "author": author_str,
                            "source": f"CORE, {year}",
                            "text": abstract,
                            "pdf_url": download_url,
                        })
                    # [DEBUG-SECTION]
                    log_api_call("CORE", url, params=params, response_status=200, result_count=len(candidates))
                    # [/DEBUG-SECTION]
                    return candidates
                elif response.status_code == 429:
                    logger.warning("CORE API returned 429. Rate limited.")
                    return []
                else:
                    logger.warning(f"CORE API returned status code {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"Failed to fetch candidates from CORE for query '{query}': {e}")
            return []

    @staticmethod
    def _validate_pdf_bytes(content: bytes, pdf_url: str) -> bool:
        """
        Validates the integrity of downloaded PDF bytes before passing them
        to the extraction pipeline. Catches corrupted, truncated, or
        non-PDF responses that would silently degrade match accuracy.

        Checks:
        1. Non-zero file size
        2. Reasonable upper bound (< 200 MB)
        3. PDF header magic bytes (%PDF-)
        4. PDF EOF marker (%%EOF)
        """
        if not content or len(content) == 0:
            logger.warning(f"PDF validation failed: empty content from {pdf_url}")
            return False

        # Upper bound sanity check (200 MB)
        if len(content) > 200 * 1024 * 1024:
            logger.warning(f"PDF validation failed: file too large ({len(content)} bytes) from {pdf_url}")
            return False

        # Minimum viable PDF size (~67 bytes for an empty PDF)
        if len(content) < 64:
            logger.warning(f"PDF validation failed: file too small ({len(content)} bytes) from {pdf_url}")
            return False

        # PDF header magic bytes
        if not content[:5] == b"%PDF-":
            logger.warning(f"PDF validation failed: missing PDF header magic bytes from {pdf_url}")
            return False

        # PDF EOF marker — check the last 1024 bytes for %%EOF
        tail = content[-1024:]
        if b"%%EOF" not in tail:
            logger.warning(f"PDF validation failed: missing %%EOF marker from {pdf_url}")
            return False

        return True

    @classmethod
    async def download_fulltext_pdf(cls, pdf_url: str, max_retries: int = 3) -> str | None:
        """
        Downloads and extracts text from an open-access PDF with integrity
        validation and retry-with-backoff on failure.

        Validation is performed immediately after download. On failure,
        the download is retried up to max_retries times with exponential
        backoff. Only validated PDFs reach the text extraction pipeline.

        Returns the extracted full text, or None on failure.
        """
        if not pdf_url:
            return None

        backoff_base = 1.5

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=float(settings.FULLTEXT_DOWNLOAD_TIMEOUT),
                    follow_redirects=True,
                ) as client:
                    response = await client.get(pdf_url)
                    if response.status_code != 200:
                        logger.warning(f"PDF download returned status {response.status_code} for {pdf_url} (attempt {attempt}/{max_retries})")
                        if attempt < max_retries:
                            wait = backoff_base * (2 ** (attempt - 1))
                            await asyncio.sleep(wait)
                            continue
                        return None

                    # Validate PDF integrity before extraction (checks %PDF- magic bytes and %EOF)
                    if not cls._validate_pdf_bytes(response.content, pdf_url):
                        logger.warning(f"PDF integrity check failed for {pdf_url} (attempt {attempt}/{max_retries})")
                        if attempt < max_retries:
                            wait = backoff_base * (2 ** (attempt - 1))
                            await asyncio.sleep(wait)
                            continue
                        logger.error(f"PDF quarantined after {max_retries} failed attempts: {pdf_url}")
                        return None

                    # Extract text using the existing extractor
                    from app.services.extractor import DocumentExtractorService, ExtractionError
                    try:
                        text = DocumentExtractorService._extract_pdf(response.content)
                        if text and len(text.strip()) > 100:
                            return text.strip()
                        else:
                            logger.warning(f"Extracted text too short from PDF: {pdf_url}")
                            return None
                    except ExtractionError as e:
                        logger.warning(f"Failed to extract text from downloaded PDF {pdf_url}: {e}")
                        return None

            except httpx.TimeoutException:
                logger.warning(f"PDF download timed out for {pdf_url} (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    wait = backoff_base * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)
                    continue
                return None
            except Exception as e:
                logger.warning(f"Failed to download PDF from {pdf_url}: {e}")
                return None

        return None

    @classmethod
    async def get_online_candidates(cls, queries: list[str], limit_per_query: int = None) -> list[dict]:
        """Fetches and merges candidates from multiple APIs, deduplicating them."""
        if limit_per_query is None:
            limit_per_query = settings.MAX_ONLINE_CANDIDATES_PER_QUERY
            
        all_candidates = []
        seen_ids = set()
        seen_titles = set()
        
        for idx, query in enumerate(queries):
            if idx > 0:
                await asyncio.sleep(1.0)  # Rate-limit padding between queries
                
            # Query all APIs
            arxiv_res = await cls.fetch_arxiv_candidates(query, limit=limit_per_query)
            semschol_res = await cls.fetch_semantic_scholar_candidates(query, limit=limit_per_query)
            crossref_res = await cls.fetch_crossref_candidates(query, limit=limit_per_query)
            core_res = await cls.fetch_core_candidates(query, limit=limit_per_query)
            
            for cand in arxiv_res + semschol_res + crossref_res + core_res:
                cand_id = cand["doc_id"]
                title_lower = cand["title"].lower().strip()
                
                if cand_id not in seen_ids and title_lower not in seen_titles:
                    seen_ids.add(cand_id)
                    seen_titles.add(title_lower)
                    all_candidates.append(cand)
                    
        return all_candidates

    @classmethod
    async def get_online_candidates_with_relevance(
        cls,
        profile,
        limit_per_query: int = None,
    ) -> list[dict]:
        """
        Fetches candidates using TopicProfile-based queries and re-ranks them
        by cosine similarity against the abstract embedding.

        Filters out candidates below MIN_CANDIDATE_RELEVANCE.
        """
        queries = cls.extract_search_queries_from_profile(profile)
        if not queries:
            logger.warning("No search queries generated from TopicProfile. Falling back to empty candidate set.")
            return []

        candidates = await cls.get_online_candidates(queries, limit_per_query)

        if not candidates:
            return []

        # Re-rank by abstract embedding similarity if enabled and embedding available
        if settings.ABSTRACT_EMBEDDING_RERANK and profile.embedding:
            try:
                import numpy as np
                profile_emb = np.array(profile.embedding)

                model = SemanticMatcher.get_model()
                candidate_texts = [c["text"] for c in candidates]
                candidate_embeddings = model.encode(candidate_texts, show_progress_bar=False)

                for i, cand in enumerate(candidates):
                    cand_emb = candidate_embeddings[i]
                    # Cosine similarity
                    dot = np.dot(profile_emb, cand_emb)
                    norm = np.linalg.norm(profile_emb) * np.linalg.norm(cand_emb)
                    similarity = float(dot / norm) if norm > 0 else 0.0
                    cand["relevance_score"] = similarity

                # Filter by relevance threshold
                candidates = [
                    c for c in candidates
                    if c.get("relevance_score", 0.0) >= settings.MIN_CANDIDATE_RELEVANCE
                ]

                # Sort by relevance descending
                candidates.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)

                logger.info(f"After relevance filtering: {len(candidates)} candidates remain (threshold={settings.MIN_CANDIDATE_RELEVANCE})")
                # [DEBUG-SECTION]
                log_data_exchange("EmbeddingReranker", "CandidatePool",
                    "relevance-scored candidates", record_count=len(candidates),
                    sample={"top_score": round(candidates[0].get("relevance_score", 0), 4) if candidates else 0,
                            "threshold": settings.MIN_CANDIDATE_RELEVANCE})
                # [/DEBUG-SECTION]
            except Exception as e:
                logger.error(f"Failed to re-rank candidates by embedding similarity: {e}")

        # Download full-text PDFs for top candidates if enabled
        if settings.ENABLE_FULLTEXT_DOWNLOAD:
            download_count = 0
            for cand in candidates:
                if download_count >= settings.MAX_FULLTEXT_DOWNLOADS_PER_JOB:
                    break
                pdf_url = cand.get("pdf_url")
                if pdf_url:
                    fulltext = await cls.download_fulltext_pdf(pdf_url)
                    if fulltext:
                        cand["text"] = fulltext
                        download_count += 1
                        logger.info(f"Downloaded full text for: {cand['title'][:60]}...")

        return candidates

    @classmethod
    async def seed_ephemeral_candidates(cls, job_id: str, candidates: list[dict]) -> None:
        """
        Embeds, segments, and writes candidates to PostgreSQL using job-isolated IDs.
        The tsvector column handles lexical indexing automatically.
        """
        if not candidates:
            return

        logger.info(f"Seeding {len(candidates)} ephemeral candidates for job: {job_id}")
        
        # 1. Segment candidates into sentences
        flat_sentences = []
        for cand in candidates:
            doc_id = f"job_{job_id}_{cand['doc_id']}"
            
            # Write document metadata to PostgreSQL
            try:
                DatabaseService.insert_reference_document(
                    doc_id=doc_id,
                    title=cand["title"],
                    author=cand["author"],
                    source=cand["source"]
                )
            except Exception as e:
                logger.error(f"Failed to write ephemeral document {doc_id} metadata: {e}")
                continue

            sentences = SentenceSegmenterService.segment(cand["text"])
            for idx, s in enumerate(sentences):
                flat_sentences.append({
                    "document_id": doc_id,
                    "sentence_index": idx,
                    "text": s["text"]
                })

        if not flat_sentences:
            return

        # 2. Generate vector embeddings using SemanticMatcher
        try:
            model = SemanticMatcher.get_model()
            corpus = [s["text"] for s in flat_sentences]
            embeddings = model.encode(corpus, show_progress_bar=False)
            
            for s, emb in zip(flat_sentences, embeddings):
                s["embedding"] = emb.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embeddings for ephemeral sentences: {e}")
            return

        # 3. Write to PostgreSQL (tsvector column auto-populates for lexical search)
        try:
            DatabaseService.insert_reference_sentences(flat_sentences)
            logger.info(f"Successfully cached {len(flat_sentences)} sentences in PostgreSQL for job: {job_id}")
        except Exception as e:
            logger.error(f"PostgreSQL caching failed for job {job_id}: {e}")

    @classmethod
    def prune_cache(cls, job_id: str) -> None:
        """
        Deletes all PostgreSQL candidate records associated with the specified job_id.
        CASCADE foreign key automatically removes associated sentences.
        """
        logger.info(f"Pruning ephemeral cache for job: {job_id}")
        
        try:
            with DatabaseService.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Cascade deletes sentences via foreign key on documents
                    cursor.execute("DELETE FROM documents WHERE id LIKE %s;", (f"job_{job_id}_%",))
                conn.commit()
            logger.info(f"Pruned PostgreSQL records for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to prune PostgreSQL cache for job {job_id}: {e}")

