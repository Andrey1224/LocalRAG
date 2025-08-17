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

Using Poetry (recommended):

```bash
# Install dependencies
poetry install

# Start development server
poetry run uvicorn app.main:app --reload

# Run tests
poetry run pytest

# Code formatting
poetry run black app/
poetry run ruff app/
```

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