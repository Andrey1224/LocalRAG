# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LocalRAG is a modular LLM platform with Retrieval-Augmented Generation (RAG) for working with internal documents. It provides document ingestion, hybrid search (BM25 + vector), LLM generation with citations, feedback collection, and automated evaluation - all deployable locally or in cloud environments.

## Development Commands

### Quick Start
```bash
# Full system startup with Docker
docker-compose up -d

# Check all services health
curl http://localhost:8000/healthz

# Stop all services
docker-compose down
```

### Development with Poetry
```bash
# Install dependencies
poetry install

# Run main API server (development)
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run simplified testing server
python simple_localrag.py

# Run Streamlit UI
streamlit run test_ui.py --server.port 8501

# Run specific test file
poetry run pytest tests/test_specific.py -v

# Run all tests with coverage
poetry run pytest --cov=app --cov-report=term-missing

# Code formatting and linting
poetry run black app/
poetry run ruff check app/
poetry run ruff check app/ --fix

# Type checking
poetry run mypy app/
```

### Docker Development
```bash
# Build and run API only
docker build -t localrag .
docker run -p 8000:8000 localrag

# Build Streamlit UI
docker build -f Dockerfile.streamlit -t localrag-ui .
```

### Testing and API Interaction
```bash
# Test document ingestion
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["test_document.md"]}'

# Ask questions
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What security policies are described?"}'

# List documents
curl "http://localhost:8000/documents"

# Delete document
curl -X DELETE "http://localhost:8000/documents/{doc_id}"
```

## Architecture

### Core Application Structure
- **app/main.py**: FastAPI application entry point with middleware stack
- **app/core/**: Configuration management, logging, middleware, and security
- **app/api/**: REST API endpoints organized by functionality (health, ingest, ask, feedback, evaluation)
- **app/services/**: Business logic for document processing, search, LLM integration, embeddings
- **app/models/**: Pydantic data models for API requests/responses

### Service Architecture
The system runs as microservices orchestrated by Docker Compose:

- **FastAPI API** (port 8000): Main application server
- **Streamlit UI** (port 8501): User interface for testing
- **Qdrant** (port 6333): Vector database for embeddings
- **Elasticsearch** (port 9200): BM25 search engine
- **PostgreSQL** (port 5432): Relational data storage
- **Ollama** (port 11434): Local LLM server
- **Redis** (port 6379): Caching layer

### Configuration System
- Environment variables via `.env` file
- Pydantic Settings in `app/core/config.py` with validation
- YAML configuration in `config.yaml` for model parameters
- All settings have sensible defaults for development

### RAG Pipeline Flow
1. **Document Ingestion**: Parse → Chunk → Embed → Index (Qdrant + Elasticsearch)
2. **Question Processing**: Query → Hybrid Search (BM25 + Vector) → Rerank → LLM Generation
3. **Response**: Answer + Citations + Debug Info + Feedback Collection

### Testing Infrastructure
- **simple_localrag.py**: Simplified working implementation for testing and demonstrations
- **test_ui.py**: Streamlit interface with multiple testing modes (Health, Ingest, Ask, Document Management, Feedback, Full Test)
- **test_api.py**: Automated API testing scripts
- Unit tests in **tests/** directory with pytest

### Middleware Stack (Applied in Order)
1. SecurityHeadersMiddleware: Security headers
2. CORSMiddleware: Cross-origin request handling
3. LoggingMiddleware: Request/response logging with trace IDs
4. TracingMiddleware: Distributed tracing support
5. RateLimitMiddleware: Rate limiting (production only)

### Key Design Patterns
- **Dependency Injection**: Services injected via FastAPI dependencies
- **Configuration as Code**: All settings externalized and validated
- **Structured Logging**: JSON format with trace IDs for observability
- **Health Checks**: Comprehensive health monitoring for all services
- **Error Handling**: Consistent error responses with proper HTTP status codes

### Environment-Specific Behavior
- **Development** (`ENV=dev`): Debug mode, auto-reload, detailed error messages, no rate limiting
- **Production** (`ENV=prod`): Rate limiting enabled, error details hidden, optimized for performance

### Document Management
The system provides full CRUD operations for documents:
- List all documents with metadata (`GET /documents`)
- Delete documents with automatic chunk cleanup (`DELETE /documents/{doc_id}`)
- Idempotent ingestion prevents duplicates via content hashing

### LLM Integration
- Primary: Ollama for local LLM inference (llama3.1:8b, llama3.2:1b)
- Fallback: Intelligent text extraction when LLM is unavailable
- Embeddings: BGE models (BAAI/bge-small-en-v1.5)
- Reranking: BGE reranker (BAAI/bge-reranker-v2-m3)

## Important Implementation Notes

- The simplified `simple_localrag.py` is a fully functional standalone implementation that demonstrates real RAG capabilities without external dependencies
- Always test against the simple implementation first when debugging complex issues
- The Streamlit UI (`test_ui.py`) provides comprehensive testing interfaces - prefer this over manual API calls
- Document management includes both API endpoints and UI components for complete document lifecycle management
- All commits should be in English without decorative elements per project conventions
- When making changes, always restart services to ensure configuration updates take effect