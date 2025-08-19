# LocalRAG

LLM-платформа с RAG и обратной связью для работы с внутренними документами.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Development Setup

1. **Clone and setup**:
```bash
git clone <repository>
cd LocalRAG
cp .env.example .env
```

2. **Start services**:
```bash
docker-compose up -d
```

3. **Check health**:
```bash
curl http://localhost:8000/healthz
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | FastAPI backend |
| UI | 8501 | Streamlit frontend |
| Qdrant | 6333 | Vector database |
| Elasticsearch | 9200 | BM25 search |
| Ollama | 11434 | LLM server |

### API Endpoints

- `GET /` - Root information
- `GET /healthz` - Basic health check
- `GET /health/detailed` - Detailed health check
- `GET /docs` - OpenAPI documentation

### Development

#### Quick Start with Poetry (recommended):

```bash
# Install dependencies
poetry install

# Setup pre-commit hooks (recommended)
poetry run pre-commit install
poetry run pre-commit install --hook-type pre-push

# Start development server
poetry run uvicorn app.main:app --reload

# Run tests
poetry run pytest

# Code formatting and linting
poetry run black app/
poetry run ruff check app/ --fix
poetry run mypy app/
```

#### Alternative Setup (without Poetry):

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Setup pre-commit hooks
pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push

# Start development server
uvicorn app.main:app --reload

# Run tests
pytest

# Code formatting and linting
black app/
ruff check app/ --fix
mypy app/
```

#### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

- **Automatic formatting** (Black, Ruff)
- **Type checking** (MyPy)
- **Security scanning** (Bandit)
- **Dependency analysis** (Deptry)
- **Standard checks** (YAML, JSON, trailing whitespace, etc.)

**Usage:**
```bash
# Hooks run automatically on commit
git commit -m "your message"

# Run hooks manually on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files

# Skip hooks for emergency commits
git commit --no-verify -m "hotfix: critical issue"
```

**Troubleshooting:**
- If hooks fail, fix the issues and commit again
- Use `--no-verify` only for emergency hotfixes
- Run `pre-commit run --all-files` to check all files at once

### Project Structure

```
├── app/                 # FastAPI application
│   ├── api/            # API routes
│   ├── core/           # Core functionality
│   ├── models/         # Pydantic models
│   ├── services/       # Business logic
│   └── utils/          # Utilities
├── ui/                 # Streamlit UI
├── data/               # Data storage
├── logs/               # Log files
├── scripts/            # Shell scripts
├── tests/              # Test files
└── docs/               # Documentation
```

### Configuration

- Environment variables: `.env`
- Application config: `config.yaml`
- Docker services: `docker-compose.yml`

### Next Steps

See `DEVELOPMENT_PLAN.md` for roadmap and current progress.
