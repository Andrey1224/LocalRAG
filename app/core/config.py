"""Configuration management for LocalRAG application."""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and config files."""
    
    # Environment
    env: str = Field(default="dev", env="ENV")
    debug: bool = Field(default=True, env="DEBUG")
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_workers: int = Field(default=1, env="API_WORKERS")
    
    # Security
    secret_key: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    api_key_header: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"], 
        env="CORS_ORIGINS"
    )
    
    # Database
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: str = Field(default="localrag", env="POSTGRES_DB")
    postgres_user: str = Field(default="localrag", env="POSTGRES_USER")
    postgres_password: str = Field(default="localrag_password", env="POSTGRES_PASSWORD")
    
    # Redis
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    
    # Vector Database
    qdrant_host: str = Field(default="localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")
    qdrant_collection_name: str = Field(default="documents", env="QDRANT_COLLECTION_NAME")
    
    # Search
    elasticsearch_host: str = Field(default="localhost", env="ELASTICSEARCH_HOST")
    elasticsearch_port: int = Field(default=9200, env="ELASTICSEARCH_PORT")
    elasticsearch_index: str = Field(default="documents", env="ELASTICSEARCH_INDEX")
    
    # LLM Configuration
    llm_model: str = Field(default="llama3.1:8b", env="LLM_MODEL")
    ollama_host: str = Field(default="localhost", env="OLLAMA_HOST")
    ollama_port: int = Field(default=11434, env="OLLAMA_PORT")
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3", env="RERANKER_MODEL")
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", env="EMBEDDING_MODEL")
    
    # Generation Limits
    max_tokens: int = Field(default=400, env="MAX_TOKENS")
    context_window: int = Field(default=2500, env="CONTEXT_WINDOW")
    chunk_size: int = Field(default=1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, env="CHUNK_OVERLAP")
    
    # File Processing
    max_file_size_mb: int = Field(default=50, env="MAX_FILE_SIZE_MB")
    max_chunk_size_tokens: int = Field(default=1000, env="MAX_CHUNK_SIZE_TOKENS")
    chunk_overlap_tokens: int = Field(default=100, env="CHUNK_OVERLAP_TOKENS")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")
    log_file_max_size: int = Field(default=10485760, env="LOG_FILE_MAX_SIZE")  # 10MB
    log_file_backup_count: int = Field(default=7, env="LOG_FILE_BACKUP_COUNT")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=60, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="RATE_LIMIT_PERIOD")
    
    # Documentation
    enable_docs: bool = Field(default=True, env="ENABLE_DOCS")
    
    @property
    def database_url(self) -> str:
        """Get PostgreSQL database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def qdrant_url(self) -> str:
        """Get Qdrant URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    @property
    def elasticsearch_url(self) -> str:
        """Get Elasticsearch URL."""
        return f"http://{self.elasticsearch_host}:{self.elasticsearch_port}"
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "allow"
    }


class AppConfig:
    """Application configuration loaded from YAML config file."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    @property
    def models(self) -> dict:
        """Get models configuration."""
        return self._config.get("models", {})
    
    @property
    def chunking(self) -> dict:
        """Get chunking configuration."""
        return self._config.get("chunking", {})
    
    @property
    def search(self) -> dict:
        """Get search configuration."""
        return self._config.get("search", {})
    
    @property
    def generation(self) -> dict:
        """Get generation configuration."""
        return self._config.get("generation", {})
    
    @property
    def evaluation(self) -> dict:
        """Get evaluation configuration."""
        return self._config.get("evaluation", {})
    
    @property
    def feedback(self) -> dict:
        """Get feedback configuration."""
        return self._config.get("feedback", {})
    
    @property
    def ingest(self) -> dict:
        """Get ingest configuration."""
        return self._config.get("ingest", {})
    
    @property
    def logging(self) -> dict:
        """Get logging configuration."""
        return self._config.get("logging", {})
    
    @property
    def security(self) -> dict:
        """Get security configuration."""
        return self._config.get("security", {})


# Global settings instance
settings = Settings()
app_config = AppConfig()