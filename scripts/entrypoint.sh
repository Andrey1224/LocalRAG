#!/bin/bash
set -e

echo "Starting LocalRAG application..."

# Wait for dependencies to be ready
echo "Waiting for dependencies..."

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
while ! curl -s postgres:5432 > /dev/null; do
  sleep 2
done
echo "PostgreSQL is ready!"

# Wait for Qdrant
echo "Waiting for Qdrant..."
while ! curl -s http://qdrant:6333/health > /dev/null; do
  sleep 2
done
echo "Qdrant is ready!"

# Wait for Elasticsearch
echo "Waiting for Elasticsearch..."
while ! curl -s http://elasticsearch:9200/_cluster/health > /dev/null; do
  sleep 2
done
echo "Elasticsearch is ready!"

# Wait for Ollama
echo "Waiting for Ollama..."
while ! curl -s http://ollama:11434/api/tags > /dev/null; do
  sleep 2
done
echo "Ollama is ready!"

# Run database migrations if in production
if [ "$ENV" = "prod" ]; then
    echo "Running database migrations..."
    # alembic upgrade head
fi

# Pull required models on first run
echo "Checking LLM models..."
if [ "${LLM_MODEL:-llama3.1:8b}" != "" ]; then
    echo "Ensuring model ${LLM_MODEL:-llama3.1:8b} is available..."
    curl -X POST http://ollama:11434/api/pull -d "{\"name\": \"${LLM_MODEL:-llama3.1:8b}\"}" || echo "Model pull failed, continuing..."
fi

echo "Starting application..."
exec "$@"