# Dockerfile for Lemma - Research Paper Summarizer

FROM python:3.11-slim

# Install system dependencies for WeasyPrint (PDF rendering) and Ollama
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    zstd \
    libcairo2 \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    libffi-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama LLM runtime
RUN curl -fsSL https://ollama.com/install.sh | sh

# Create non-root user 1000 (required for Hugging Face Spaces security)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    OLLAMA_KEEP_ALIVE=0 \
    PYTHONPATH=/home/user/app/backend

WORKDIR $HOME/app

# Copy requirements and install Python dependencies
COPY --chown=user:user backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy English NLP model
RUN python -m spacy download en_core_web_sm

# Copy full application code (backend + frontend)
COPY --chown=user:user . .

# Ensure startup script is executable
RUN chmod +x start.sh backend/start.sh

# Expose default port (7860 for Hugging Face Spaces & local Docker)
EXPOSE 7860

# Ensure user permissions across home directory
RUN chown -R user:user /home/user

# Switch to non-root user
USER user

CMD ["./start.sh"]
