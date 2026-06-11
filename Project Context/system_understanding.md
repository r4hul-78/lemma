# System Understanding: Lemma Plagiarism Analysis & Paraphrasing Platform

This document captures our complete understanding of the Lemma project codebase, architecture, and current execution state as of June 5, 2026.

---

## 1. System Architecture (Current State)

The application is structured as a decoupled client-server architecture. The backend is written in Python (FastAPI) and handles document ingestion, validation, and sentence segmentation.

### Current Directory Structure
```
lemma/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py         # Configures API settings, upload directories, limits
│   │   ├── main.py           # Entrypoint with CORS middleware, exception handlers, and endpoints
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── document.py   # Pydantic schemas (SentenceCoordinate, DocumentUploadResponse)
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── extractor.py  # Service for text extraction from TXT, DOCX, and PDF bytes
│   │       └── segmenter.py  # spaCy segmenter with coordinates mapping and offset trimming
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py       # Shared fixtures (TestClient, mock document helpers)
│   │   ├── test_extractor.py # Unit tests for document extraction
│   │   ├── test_main.py      # Integration tests for FastAPI endpoints
│   │   └── test_segmenter.py # Unit tests for sentence segmentation
│   └── requirements.txt      # Python dependencies
├── Project Context/
│   ├── mission_briefing.md   # Initial mission guidelines
│   └── system_understanding.md # This file
├── requirements.txt          # Root Python dependencies
└── README.md                 # Project README
```

---

## 2. Key Components & Operations

### A. Configuration (`config.py`)
- Sets up Settings class using `pydantic-settings`.
- Enforces an upload folder (`/backend/uploads`) and ensures it is created.
- Constraints: Maximum file size is `100MB`, allowed extensions are `txt`, `docx`, and `pdf`.
- Targets spaCy model `en_core_web_sm` and SQLite database `lemma.db`.

### B. Document Extraction (`extractor.py`)
- **TXT**: Tries UTF-8 decoding; falls back to Latin-1.
- **DOCX**: Utilizes `python-docx` to extract text from normal paragraphs and tables, discarding empty lines.
- **PDF**: Uses `pypdf.PdfReader` to extract text. If encrypted, it tries to decrypt with an empty password. If it fails or is scanned (no text), it raises a specific `ExtractionError`.

### C. Sentence Segmentation (`segmenter.py`)
- Loads `en_core_web_sm` via `spaCy` as a class-level singleton.
- Disables NER (`ner`) and lemmatizer (`lemmatizer`) for speed.
- Tracks `start_char` and `end_char` coordinates.
- Adjusts offsets correctly to omit leading/trailing whitespace in parsed sentences but matches the exact positions in the original text (allowing safe slicing with `text[start_char:end_char]`).

### D. FastAPI Endpoints (`main.py`)
- `/health` and `/api/v1/health`: Basic API health checks.
- `/api/v1/documents/upload`: Accepts a multipart file, runs it through the extractor and segmenter, and returns structured `DocumentUploadResponse` JSON.
- Handlers map `FileSizeExceededError` -> `413 Request Entity Too Large`, `UnsupportedFileTypeError` -> `400 Bad Request`, and `ExtractionError` -> `422 Unprocessable Entity`.

---

## 3. Technology Stack Redirection

Based on the latest user direction, the frontend design stack is shifting:
*   **Original Plan**: React.js + Tailwind CSS.
*   **New Plan**: Basic HTML5 + CSS3 + Vanilla JavaScript (leveraging the same pitch-black `#000000` Stark theme with modern, vibrant styling and soft atmospheric glassmorphism/fog modal overlays). This removes complex framework scaffolding and bundlers, keeping the frontend lightweight and local-first.

---

## 4. Current Work Phase

We are transitioning from **Phase 1 (Ingestion & Backend Core)** to **Phase 2 (Dual-Tier Matcher Engine)**. 
First steps include:
1. Installing local python requirements (e.g., FastAPI, spaCy, pypdf, python-docx, sentence-transformers, celery, redis, scikit-learn).
2. Downloading the spaCy `en_core_web_sm` pipeline.
3. Designing the structure of the HTML5/CSS3/JS UI client.
