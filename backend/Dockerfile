FROM python:3.11-slim

# Install system dependencies for WeasyPrint and Ollama
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

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Set up user 1000 (Hugging Face requirements)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Download and extract Elasticsearch 8.11.1
RUN curl -L -o elasticsearch.tar.gz https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.11.1-linux-x86_64.tar.gz && \
    tar -xzf elasticsearch.tar.gz && \
    rm elasticsearch.tar.gz && \
    mv elasticsearch-8.11.1 /home/user/elasticsearch

# Configure Elasticsearch for single-node container deployment
RUN echo "discovery.type: single-node" >> /home/user/elasticsearch/config/elasticsearch.yml && \
    echo "xpack.security.enabled: false" >> /home/user/elasticsearch/config/elasticsearch.yml && \
    echo "-Xms512m" > /home/user/elasticsearch/config/jvm.options.d/heap.options && \
    echo "-Xmx512m" >> /home/user/elasticsearch/config/jvm.options.d/heap.options && \
    chown -R user:user /home/user/elasticsearch

# Copy requirements and install
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Copy remaining code with correct ownership
COPY --chown=user:user . .

# Ensure start.sh is executable
RUN chmod +x start.sh

# Expose Hugging Face Space port
EXPOSE 7860

# Ensure user:user owns their entire home directory to avoid write permission errors
RUN chown -R user:user /home/user

# Switch to non-root user
USER user

CMD ["./start.sh"]
