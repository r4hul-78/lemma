#!/bin/bash

# 1. Create the target directory inside the container relative to CWD if it doesn't exist
mkdir -p my_custom_model

# 2. Download custom model weights from Model Hub if not already present
if [ ! -f my_custom_model/model.gguf ]; then
    echo "Downloading custom model weights from Model Hub..."
    curl -L -o my_custom_model/model.gguf "https://huggingface.co/r4hul-78/lemma-paraphrase-3b/resolve/main/model.gguf"
fi

# 3. Start Elasticsearch in the background
echo "Starting Elasticsearch..."
/home/user/elasticsearch/bin/elasticsearch &

# 4. Wait for Elasticsearch to wake up
echo "Waiting for Elasticsearch to start..."
for i in {1..30}; do
    if curl -s http://localhost:9200 >/dev/null; then
        echo "Elasticsearch is up and running!"
        break
    fi
    sleep 2
done

# 5. Start the Ollama engine in the background
echo "Starting Ollama engine..."
ollama serve &

# 6. Wait for Ollama to wake up
sleep 5

# 7. Build the Ollama definition from your local Modelfile dynamically at startup
echo "Creating Ollama model instance..."
(cd my_custom_model && ollama create lemma-model -f Modelfile)

# 8. Hand over control to Uvicorn
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
