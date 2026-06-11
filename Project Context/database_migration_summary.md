# Conversation Summary: Local Vector Database Migration (FAISS + SQLite)

This document provides a summary of the migration of Project Lemma's plagiarism reference corpus storage from an in-memory JSON cache to a dedicated local-first vector database setup.

---

## 1. Objectives
- **Relational Metadata**: Maintain document metadata (author, title, source) and text segments in a structured relational database rather than an in-memory JSON.
- **Scalable Vector Search**: Transition from an in-memory search loop to **FAISS (Facebook AI Similarity Search)** using `all-MiniLM-L6-v2` embeddings for fast, sub-millisecond semantic lookups.
- **Robust Local-First Architecture**: Keep all databases and indices local to avoid external dependency issues on Windows.

---

## 2. Decoupled Architecture

The new architecture decouples vector representation from relational metadata:

1.  **FAISS Vector Index (`lemma_vectors.index`)**: Stores high-dimensional sentence embeddings. Queries return a numerical index matching the position of the closest vector.
2.  **SQLite Database (`lemma.db`)**: Houses `documents` and `sentences` tables. A `faiss_id` field bridges the FAISS search result back to the corresponding sentence text and document citation details.

```
                      +-------------------+
                      |   Query Sentence  |
                      +---------+---------+
                                |
                    Encode to 384-d Embedding
                                |
                   faiss.normalize_L2(vector)
                                |
                                v
               +---------------------------------+
               |  FAISS Index Search (IndexFlat) |
               |     (lemma_vectors.index)       |
               +----------------+----------------+
                                |
                       Returns: faiss_id
                                |
                                v
               +---------------------------------+
               |    SQLite Query (lemma.db)      |
               | SELECT text, doc_title, source  |
               +----------------+----------------+
                                |
                                v
               +---------------------------------+
               |      Exact Citation Match       |
               +----------------+----------------+
```

---

## 3. Implemented Components

### A. Configuration & Setup
- **[config.py](file:///d:/Learning/Along%20Her/lemma/backend/app/config.py)**: Added settings configurations for `SQLITE_DB_PATH` and `FAISS_INDEX_PATH`.
- **[requirements.txt](file:///d:/Learning/Along%20Her/lemma/requirements.txt)** & **[backend/requirements.txt](file:///d:/Learning/Along%20Her/lemma/backend/requirements.txt)**: Appended `faiss-cpu>=1.8.0`.

### B. Relational Service
- **[database.py](file:///d:/Learning/Along%20Her/lemma/backend/app/services/database.py)**: Manages SQLite table initialization, bulk insertions, and metadata queries. Contains `documents` and `sentences` schemas with foreign key mappings.

### C. Matching Coordinator
- **[matcher.py](file:///d:/Learning/Along%20Her/lemma/backend/app/services/matcher.py)**:
  - Updates `seed_database()` to segment reference corpus texts, bulk-insert records into SQLite, encode sentence vectors, build an exact Cosine Similarity index (`faiss.IndexFlatIP` using normalized vectors), and write it to disk.
  - Modifies `SemanticMatcher` to load the index from file, query FAISS for the nearest `faiss_id` index, and lookup metadata details from SQLite.

### D. Testing & Quality Assurance
- **[conftest.py](file:///d:/Learning/Along%20Her/lemma/backend/tests/conftest.py)**: Redirects settings configurations to `test_lemma.db` and `test_lemma_vectors.index` and runs automated pre-test and post-test cleanup fixtures.
- **[test_matcher.py](file:///d:/Learning/Along%20Her/lemma/backend/tests/test_matcher.py)**: Implements database setup, seeding, reloading, and similarity matching tests.
- **[pytest.ini](file:///d:/Learning/Along%20Her/lemma/pytest.ini)**: Hushed the third-party `StarletteDeprecationWarning` regarding `httpx` inside `starlette.testclient` to ensure clean terminal output.

---

## 4. Verification
All 21 backend unit and integration tests successfully pass on the host machine:
```powershell
python -m pytest backend/tests/
```
The test suite runs in ~10 seconds with zero warnings, validating full SQLite/FAISS integration.
