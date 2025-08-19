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
# Install dependencies and setup development environment
poetry install

# Setup pre-commit hooks (run once after cloning)
poetry run pre-commit install
poetry run pre-commit install --hook-type pre-push

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

# Code formatting and linting (manual runs)
poetry run black app/
poetry run ruff check app/
poetry run ruff check app/ --fix

# Type checking
poetry run mypy app/

# Pre-commit hooks (automatic on commit, manual commands below)
poetry run pre-commit run --all-files  # Run all hooks manually
poetry run pre-commit run black        # Run specific hook
poetry run pre-commit autoupdate       # Update hook versions
```

### Alternative Development (without Poetry)
```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Setup pre-commit hooks
pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest --cov=app --cov-report=term-missing

# Code quality checks
black app/
ruff check app/ --fix
mypy app/
pre-commit run --all-files
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
- **app/utils/**: Utility functions and helpers

### Project File Structure
```
LocalRAG/
├── app/                      # Main application code
│   ├── api/                  # FastAPI route handlers
│   ├── core/                 # Core functionality (config, logging, middleware)
│   ├── models/               # Pydantic models
│   ├── services/             # Business logic services
│   └── utils/                # Utility functions
├── tests/                    # Test files
│   ├── unit/                 # Unit tests (run in pre-commit)
│   └── integration/          # Integration tests
├── data/                     # Data storage directories
│   ├── raw/                  # Original documents
│   ├── normalized/           # Processed documents
│   └── chunks/               # Document chunks
├── logs/                     # Application logs
├── ui/                       # Streamlit UI components
├── scripts/                  # Shell scripts and utilities
├── docs/                     # Documentation
├── .github/workflows/        # GitHub Actions CI/CD
├── config.yaml               # Application configuration
├── pyproject.toml           # Python project configuration
├── docker-compose.yml       # Docker services orchestration
├── .pre-commit-config.yaml  # Pre-commit hooks configuration
├── simple_localrag.py       # Standalone implementation for testing
├── test_ui.py               # Streamlit testing interface
└── test_api.py              # API testing scripts
```

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

## Code Quality and Development Workflow

### Pre-commit Hooks
The project uses automated pre-commit hooks to ensure code quality:

**Enabled Checks:**
- **Black**: Automatic code formatting (line length: 100)
- **Ruff**: Fast linting + import sorting (replaces flake8 + isort)
- **MyPy**: Type checking with strict settings
- **Bandit**: Security vulnerability scanning
- **Pytest**: Fast unit tests (tests/unit/ directory)
- **Standard checks**: YAML/JSON validation, trailing whitespace, large files
- **Custom checks**: Prevent TODO/print() in production code, .env validation

**Usage Patterns:**
```bash
# Hooks run automatically on every commit
git commit -m "feat: add new feature"

# Run manually on all files
pre-commit run --all-files

# Skip hooks for emergency commits (use sparingly)
git commit --no-verify -m "hotfix: critical fix"

# Update hook versions
pre-commit autoupdate
```

**Troubleshooting:**
- If hooks fail, fix the issues and commit again
- Pre-commit automatically formats files - review changes before re-committing
- Use `--no-verify` only for emergency hotfixes
- All team members should run `pre-commit install` after cloning

### Testing Strategy
- **Unit tests**: Fast tests in `tests/unit/` (run in pre-commit)
- **Integration tests**: Full system tests in `tests/`
- **Manual testing**: Use `test_ui.py` Streamlit interface
- **API testing**: Automated scripts in `test_api.py`
- **Simple validation**: Use `simple_localrag.py` for quick debugging

### Code Conventions
- **Python version**: 3.11+ (specified in pyproject.toml)
- **Line length**: 100 characters (Black + Ruff configured)
- **Import organization**: Automatic via Ruff
- **Type hints**: Required for all functions (MyPy enforced)
- **Security**: No hardcoded secrets, use environment variables
- **Logging**: Structured JSON logging with trace IDs

### Development Best Practices
- **Always run pre-commit hooks** before pushing
- **Test locally first** using simple_localrag.py
- **Use meaningful commit messages** following conventional commits
- **Update dependencies carefully** and test thoroughly
- **Document configuration changes** in this file

### CI/CD Integration
The project includes GitHub Actions workflows for automated quality checks:

**Pre-commit CI** (`.github/workflows/pre-commit.yml`):
- Runs all pre-commit hooks on every push/PR
- Tests both Poetry and pip-only setups
- Uploads security reports from Bandit
- Caches dependencies for faster runs

**Workflow triggers:**
- Push to `main` or `develop` branches
- Pull requests targeting `main` or `develop`
- Manual workflow dispatch

**Local vs CI behavior:**
- Same checks run locally and in CI
- CI failures indicate code quality issues
- Fix issues locally and push again

## Important Implementation Notes

### Key Files and Their Purpose
- **`simple_localrag.py`**: Fully functional standalone RAG implementation without external dependencies - use for quick testing and debugging
- **`test_ui.py`**: Comprehensive Streamlit testing interface with multiple modes (Health, Ingest, Ask, Document Management, Feedback, Full Test)
- **`test_api.py`**: Automated API testing scripts for validation
- **`config.yaml`**: Central configuration for models, chunking, search, and evaluation parameters
- **`pyproject.toml`**: Python project dependencies, tools configuration (Black, Ruff, MyPy, Pytest)
- **`.pre-commit-config.yaml`**: Code quality automation configuration
- **`docker-compose.yml`**: Full system orchestration with all required services

### Development Workflow Guidelines
- **Always test against the simple implementation first** when debugging complex issues
- **Use the Streamlit UI** (`test_ui.py`) for comprehensive testing - prefer this over manual API calls
- **Run pre-commit hooks** before every commit to ensure code quality
- **Update this CLAUDE.md file** when making architectural or configuration changes
- **Test locally first** before pushing to ensure CI passes
- **Use meaningful commit messages** following conventional commit format
- **Document new features** in both README.md and this file

### Production Deployment Notes
- All commits should be in English without decorative elements per project conventions
- When making configuration changes, always restart services to ensure updates take effect
- Environment variables should be used for secrets and environment-specific settings
- Health checks are comprehensive - use `/health/detailed` for debugging service issues
- Document management includes both API endpoints and UI components for complete lifecycle management
- **CRITICAL**: Always run linting and type checking commands before committing to avoid CI failures

### Security and Best Practices
- Never commit secrets or API keys - use environment variables
- All API endpoints have proper error handling and logging
- Rate limiting is enabled in production environments
- Structured logging with trace IDs for debugging and monitoring
- Type hints are required for all functions (enforced by MyPy)
- Security scanning is automated via Bandit in pre-commit hooks
