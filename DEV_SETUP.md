# Lemma — Development Setup Guide

## Overview

Lemma supports two local development profiles:

| Profile | Services Required | Use Case |
|---------|------------------|----------|
| **Dev** (`--dev`) | Postgres + pgvector only | Pipeline logic testing, UI work, fast iteration |
| **Full Stack** | Postgres + pgvector + Ollama | End-to-end accuracy testing, LLM features |

---

## Quick Start

### Dev Mode (Recommended for Daily Development)

```bash
# 1. Start the minimal Postgres container
docker compose up -d

# 2. Run the application in dev mode
run.bat --dev
```

In dev mode:
- **Online retrieval is disabled** — no external API calls to arXiv, Semantic Scholar, etc.
- **Celery runs in eager mode** — tasks execute synchronously, no Redis needed
- **Ollama is not required** — LLM features (text rewriting, abstract extraction) will gracefully degrade
- **Debug middleware is enabled** — detailed request/response logging

### Full Stack Mode

```bash
# 1. Start the full Docker stack
docker compose up -d

# 2. Start Ollama separately
ollama serve

# 3. Create the Lemma model (first time only)
ollama create lemma-model -f Modelfile

# 4. Run the application
run.bat
```

---

## Environment Configuration

### Dev Environment (`.env.dev`)

Located at `backend/.env.dev`. Automatically copied to `backend/.env` when using `run.bat --dev`.

Key settings:
- `LEMMA_DATABASE_URL` — Points to local Docker Postgres
- `LEMMA_ENABLE_ONLINE_RETRIEVAL=false` — Skips external API fetching
- `LEMMA_CELERY_ALWAYS_EAGER=true` — No Redis dependency
- `LEMMA_OLLAMA_KEEP_ALIVE=5m` — Keeps model loaded during active dev sessions

### Production Environment (`.env.example`)

Located at `backend/.env.example`. Copy to `backend/.env` and fill in Supabase credentials.

Key settings:
- `LEMMA_DATABASE_URL` — Supabase Postgres connection string
- `LEMMA_ENABLE_ONLINE_RETRIEVAL=true` — Enables full academic paper fetching
- `LEMMA_OLLAMA_KEEP_ALIVE=0` — Unloads model immediately after each request

---

## Architecture (Post-Migration)

```
Frontend (HTML/CSS/JS) ─── HTTPS ───> FastAPI (stateless)
                                          │
                              ┌───────────┼───────────┐
                              │           │           │
                        Lexical Search  Semantic    Ollama
                        (Postgres       Search     (on-demand)
                         tsvector +    (pgvector)
                         pg_trgm)         │
                              │           │
                              └─────┬─────┘
                                    │
                            Supabase Postgres
                           (production) or
                           Local Docker Postgres
                           (development)
```

### What Changed
- **Elasticsearch removed** — Replaced by Postgres `tsvector` + `pg_trgm` (full-text + fuzzy search)
- **Dual-write eliminated** — Single write to Postgres covers both semantic and lexical indexing
- **Ollama load-on-demand** — Model unloads after idle (`KEEP_ALIVE=0` in production)
- **PDF validation** — Downloaded papers are integrity-checked before entering the pipeline

### What Stayed the Same
- Lexical match engine logic (n-gram overlap via `difflib.SequenceMatcher`)
- Semantic match engine logic (embedding similarity via pgvector)
- RRF (Reciprocal Rank Fusion) blending pipeline
- PDF ingestion + report generation
- Academic API fetchers (arXiv, Semantic Scholar, Crossref, CORE)

---

## Running Tests

```bash
# Ensure Postgres is running
docker compose up -d

# Run the test suite
cd d:\Learning\Self\lemma
set PYTHONPATH=backend
python -m pytest backend/tests/ -v
```

> **Note:** Tests use the `test_lemma` database (configured in `conftest.py`). Make sure the Postgres container is running before executing tests.
