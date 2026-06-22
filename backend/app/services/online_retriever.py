import logging
import asyncio
import httpx
import xml.etree.ElementTree as ET
from collections import Counter
from backend.app.config import settings
from backend.app.services.segmenter import SentenceSegmenterService
from backend.app.services.database import DatabaseService
from backend.app.services.elasticsearch_client import get_es_client, index_sentence_bulk
from backend.app.services.matcher import SemanticMatcher

logger = logging.getLogger(__name__)

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
    async def fetch_arxiv_candidates(cls, query: str, limit: int = 15) -> list[dict]:
        """Queries the arXiv API for matching academic preprints with retries."""
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f'all:"{query}"',
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
                            
                            candidates.append({
                                "doc_id": f"arxiv_{paper_id}",
                                "title": title,
                                "author": author_str,
                                "source": f"arXiv Preprint ({paper_url})",
                                "text": abstract
                            })
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
            "fields": "title,authors,venue,year,abstract"
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
                            abstract = paper.get("abstract")
                            
                            if not paper_id or not title or not abstract:
                                continue
                                
                            authors = [auth.get("name") for auth in paper.get("authors", []) if auth.get("name")]
                            author_str = ", ".join(authors) if authors else "N/A"
                            
                            venue = paper.get("venue", "Unknown Venue")
                            year = paper.get("year", "N/A")
                            
                            candidates.append({
                                "doc_id": f"semschol_{paper_id}",
                                "title": title,
                                "author": author_str,
                                "source": f"{venue}, {year}",
                                "text": abstract
                            })
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
                
            # Query APIs in sequence or gather them
            arxiv_res = await cls.fetch_arxiv_candidates(query, limit=limit_per_query)
            semschol_res = await cls.fetch_semantic_scholar_candidates(query, limit=limit_per_query)
            
            for cand in arxiv_res + semschol_res:
                cand_id = cand["doc_id"]
                title_lower = cand["title"].lower().strip()
                
                if cand_id not in seen_ids and title_lower not in seen_titles:
                    seen_ids.add(cand_id)
                    seen_titles.add(title_lower)
                    all_candidates.append(cand)
                    
        return all_candidates

    @classmethod
    async def seed_ephemeral_candidates(cls, job_id: str, candidates: list[dict]) -> None:
        """
        Embeds, segments, and writes candidates to PostgreSQL and Elasticsearch using job-isolated IDs.
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

        # 3. Dual-Write to PostgreSQL and Elasticsearch
        try:
            DatabaseService.insert_reference_sentences(flat_sentences)
            index_sentence_bulk(flat_sentences)
            logger.info(f"Successfully cached {len(flat_sentences)} sentences locally for job: {job_id}")
        except Exception as e:
            logger.error(f"Dual-Write caching failed for job {job_id}: {e}")

    @classmethod
    def prune_cache(cls, job_id: str) -> None:
        """
        Deletes all PostgreSQL and Elasticsearch candidate records associated with the specified job_id.
        """
        logger.info(f"Pruning ephemeral cache for job: {job_id}")
        
        # 1. Prune from PostgreSQL
        try:
            with DatabaseService.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Cascade deletes sentences via foreign key on documents
                    cursor.execute("DELETE FROM documents WHERE id LIKE %s;", (f"job_{job_id}_%",))
                conn.commit()
            logger.info(f"Pruned PostgreSQL records for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to prune PostgreSQL cache for job {job_id}: {e}")

        # 2. Prune from Elasticsearch
        try:
            es = get_es_client()
            index_name = "reference_sentences"
            if es.indices.exists(index=index_name):
                query = {
                    "query": {
                        "prefix": {
                            "document_id": f"job_{job_id}_"
                        }
                    }
                }
                res = es.delete_by_query(index=index_name, body=query)
                es.indices.refresh(index=index_name)
                deleted = res.get("deleted", 0)
                logger.info(f"Pruned {deleted} Elasticsearch sentences for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to prune Elasticsearch cache for job {job_id}: {e}")
