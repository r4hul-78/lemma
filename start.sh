#!/bin/bash

# 1. Create target directory inside container if it doesn't exist
mkdir -p backend/my_custom_model

# 2. Download custom model weights from Hugging Face Hub if not present
if [ ! -f backend/my_custom_model/model.gguf ]; then
    echo "Downloading custom model weights from Hugging Face Model Hub..."
    curl -L -o backend/my_custom_model/model.gguf "https://huggingface.co/r4hul-78/lemma-paraphrase-3b/resolve/main/model.gguf" || echo "Warning: Model download failed or skipped."
fi

# 3. Configure Ollama load-on-demand mode (unloads model after use to free RAM)
export OLLAMA_KEEP_ALIVE=${OLLAMA_KEEP_ALIVE:-0}
echo "Ollama KEEP_ALIVE set to: $OLLAMA_KEEP_ALIVE"

# 4. Start Ollama service in background
echo "Starting Ollama engine..."
ollama serve &

# 5. Wait for Ollama to initialize
echo "Waiting for Ollama engine to wake up..."
for i in {1..15}; do
    if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "Ollama engine is ready!"
        break
    fi
    sleep 1
done

# 6. Create Ollama model instance from Modelfile
echo "Creating Ollama model instance..."
if [ -f backend/my_custom_model/model.gguf ] && [ -f backend/my_custom_model/Modelfile ]; then
    (cd backend/my_custom_model && ollama create lemma-model -f Modelfile) || echo "Warning: Failed to create model from backend/my_custom_model."
elif [ -f Modelfile ]; then
    ollama create lemma-model -f Modelfile || echo "Warning: Failed to create model from root Modelfile."
else
    echo "Notice: Custom model weights not present. Application will operate with online retrieval and database features."
fi

# 7. Start FastAPI application server with Uvicorn
echo "Starting FastAPI application on port 7860..."
export PYTHONPATH=backend
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
