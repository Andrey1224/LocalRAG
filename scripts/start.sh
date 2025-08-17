#!/bin/bash

# Development startup script for LocalRAG

set -e

echo "🚀 Starting LocalRAG in development mode..."

# Check if .env exists, if not copy from .env.example
if [ ! -f .env ]; then
    echo "📋 Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please review and update .env file with your configuration"
fi

# Check if poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry is not installed. Please install poetry first:"
    echo "curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies with poetry..."
poetry install

# Start services with docker-compose
echo "🐳 Starting Docker services..."
docker-compose up -d postgres qdrant elasticsearch ollama redis

# Wait a bit for services to start
echo "⏳ Waiting for services to be ready..."
sleep 10

# Start the FastAPI app in development mode
echo "🔧 Starting FastAPI application in development mode..."
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &

# Start Streamlit UI
echo "🎨 Starting Streamlit UI..."
poetry run streamlit run ui/main.py --server.port 8501 &

echo "✅ LocalRAG is starting up!"
echo "📊 API will be available at: http://localhost:8000"
echo "🖥️  UI will be available at: http://localhost:8501"
echo "📚 API docs at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for interrupt
wait