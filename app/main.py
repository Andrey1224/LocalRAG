"""Main FastAPI application for LocalRAG."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, ingest
from app.core.config import settings
from app.core.logging import get_logger
from app.core.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TracingMiddleware,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting LocalRAG application", version="0.1.0", env=settings.env)
    
    # Startup logic
    try:
        # Initialize services here if needed
        logger.info("Application startup completed")
        yield
    finally:
        # Cleanup logic
        logger.info("Application shutdown completed")


# Create FastAPI application
app = FastAPI(
    title="LocalRAG API",
    description="LLM-платформа с RAG и обратной связью для работы с внутренними документами",
    version="0.1.0",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
    lifespan=lifespan,
)

# Add middleware (order matters - first added is outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(TracingMiddleware)

# Add rate limiting in production
if settings.env == "prod":
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_requests
    )

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(ingest.router, prefix="/api", tags=["Ingest"])

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "name": "LocalRAG API",
        "version": "0.1.0",
        "description": "LLM-платформа с RAG и обратной связью",
        "docs_url": "/docs" if settings.enable_docs else None,
        "health_url": "/healthz",
        "environment": settings.env,
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors."""
    return {
        "error": "Not Found",
        "message": "The requested resource was not found",
        "path": str(request.url),
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors."""
    logger.error("Internal server error", error=str(exc), path=str(request.url))
    
    if settings.debug:
        return {
            "error": "Internal Server Error",
            "message": str(exc),
            "path": str(request.url),
        }
    else:
        return {
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "path": str(request.url),
        }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.api_workers,
        log_level=settings.log_level.lower(),
    )