# Lemma: Plagiarism Analysis & Academic Text Rewriting Platform

Lemma is a high-performance, local-first plagiarism analysis and academic text rewriting platform. It features a decoupled client-server architecture, local vector-based NLP pipelines, asynchronous worker queues, and professional report automation.

---

## 🚀 Key Features

* **Dual-Tier Plagiarism Matcher**: Combines classical lexical matching (TF-IDF + Cosine Similarity) with deep vector semantic indexing (Sentence-Transformers) to detect both verbatim copy-pastes and complex paraphrasing.
* **Precision Coordinate Mapping**: Utilizes an optimized `spaCy` tokenization pipeline to segment documents into sentences, explicitly preserving absolute character index boundaries (`start_char`, `end_char`) for exact frontend styling.
* **Interactive 3D Visual Shell**: Features a visually stunning, premium dark-mode landing page powered by an interactive **3D Fibonacci Particle Sphere** that rotates, reacts dynamically to mouse cursor dragging/hover, and gracefully bursts and reforms using physics-based LERP mathematics.
* **Local Generative Rewriter**: Integrates with local native `Ollama` pipelines (targeting Llama 3) for academic and technical text rewriting.
* **Decoupled Async Architecture**: Implements `Celery` + `Redis` task queues to run document parsing loops in background workers.
* **HTML-to-PDF Report Automation**: Generates publication-ready PDF reports with color-coded highlighted plagiarism coordinates using the `WeasyPrint` rendering engine.

---

## 🛠️ Technology Stack

* **Frontend**: Basic HTML5, CSS3, and Vanilla JavaScript (Minimally designed high-contrast dark theme with glassmorphic overlays and custom Canvas animations).
* **API Service**: FastAPI (Python) using asynchronous patterns, serving static UI assets directly.
* **NLP & ML Pipelines**: `spaCy` (optimized tokenizer), `scikit-learn` (TF-IDF), `sentence-transformers` (all-MiniLM-L6-v2 vector embeddings).
* **Workers & Cache**: Celery + Redis.
* **Storage**: SQLite (Metadata and embedded vector indexing).
* **Report Generation**: WeasyPrint.

---

## 📂 Repository Directory Structure

```
lemma/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py         # Pydantic Settings
│   │   ├── main.py           # API entry point & exception handlers
│   │   ├── schemas/          # Pydantic validation schemas
│   │   │   ├── __init__.py
│   │   │   └── document.py   # SentenceCoordinate & Upload schemas
│   │   └── services/         # Core business logic
│   │       ├── __init__.py
│   │       ├── extractor.py  # TXT, DOCX, and PDF text extraction
│   │       └── segmenter.py  # Optimized spaCy sentence segmenter
│   └── tests/                # Test suite
│       ├── __init__.py
│       ├── conftest.py       # Shared pytest fixtures
│       ├── test_extractor.py # Document extractor unit tests
│       ├── test_main.py      # FastAPI endpoint integration tests
│       └── test_segmenter.py # Sentence segmenter unit tests
├── frontend/                 # Client UI (served directly by FastAPI)
│   ├── index.html            # Landing page (typewriter title, particle canvas)
│   ├── dashboard.html        # Workspace dashboard (drag & drop ingestion, inspector)
│   ├── style.css             # Main styling, custom blurs, and button layouts
│   ├── app.js                # Dashboard controller, API uploads, highlight rendering
│   └── landing.js            # Landing page animation loop & 3D projection physics
├── Project Context/          # Local briefings & project specifications
│   ├── Demo UI.jpeg          # Reference layout layout
│   └── system_understanding.md # Internal state tracking
├── requirements.txt          # Root Python dependencies
├── run.bat                   # Windows automated environment setup & run script
└── .gitignore                # Git ignore configuration
```

---

## ⚙️ Quick Start (Local Setup)

### Prerequisites

* **Python**: Version `3.10` or higher (successfully tested up to `3.14.3`).
* **Ollama**: Install and pull target models locally for paraphrasing.

### One-Click Setup & Launch (Windows)

Double-click or run the root helper script:

```powershell
.\run.bat
```

This batch script automatically:

1. Creates the Python virtual environment (`venv`) if missing.
2. Upgrades pip and installs all Python dependencies.
3. Downloads the optimized English spaCy model (`en_core_web_sm`).
4. Launches the Uvicorn development server on port `8000`.

### Visiting the Application

Once running:

* Access the **Landing Page** at: 👉 **[http://localhost:8000](http://localhost:8000)**
* From the landing page, click **Launch Workspace** to redirect to the active workspace at: **[http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html)**
* Access the **Interactive API Swagger documentation** at: **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 📡 Core API Documentation (Implemented Endpoints)

### `GET /health`

* **Purpose**: Returns operational status.
* **Response**:

    ```json
    { "status": "ok", "project": "Lemma Plagiarism Analysis Platform" }
    ```

### `POST /api/v1/documents/upload`

* **Purpose**: Uploads `.txt`, `.docx`, or `.pdf` files, extracts raw text, segments text, and maps coordinates.
* **Content-Type**: `multipart/form-data`
* **Success Response (200 OK)**:

    ```json
    {
      "filename": "essay.txt",
      "text": "This is the first sentence. And this is the second.",
      "char_count": 51,
      "sentence_count": 2,
      "sentences": [
        { "text": "This is the first sentence.", "start_char": 0, "end_char": 27 },
        { "text": "And this is the second.", "start_char": 28, "end_char": 51 }
      ]
    }
    ```

* **Exception status codes**:
  * `400 Bad Request`: Unsupported file format.
  * `413 Payload Too Large`: Upload exceeds 100MB constraint.
  * `422 Unprocessable Entity`: Corrupt document or decryption failure.

---

## 🧪 Running the Test Suite

We use `pytest` for unit and integration testing. Run the test suite with:

```bash
python -m pytest backend/tests/
```

---

## 🗺️ Build Roadmap

* [x] **Phase 1**: Core Ingestion, Parsing Service & spaCy Coordinate Segmenter
* [x] **Phase 2**: TF-IDF Matrix & Semantic Embeddings Dual Matching Engine
* [ ] **Phase 3**: Celery Asynchronous Job Queues & Redis Integration
* [x] **Phase 4 (Refactored)**: Stark dark-theme Frontend with Interactive 3D Canvas animation (Completed ahead of matchers to bootstrap UI)
* [ ] **Phase 5**: WeasyPrint PDF Generation & End-to-End Verification
