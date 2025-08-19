"""Health check endpoints."""

import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.models.base import HealthCheckResponse

router = APIRouter()
logger = get_logger(__name__)


async def check_postgres() -> str:
    """Check PostgreSQL connection."""
    try:
        from sqlalchemy import create_engine

        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        logger.error("PostgreSQL health check failed", error=str(e))
        return f"unhealthy: {str(e)}"


async def check_qdrant() -> str:
    """Check Qdrant connection."""
    try:
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=5)
        # Try to get collections list
        collections = client.get_collections()
        return "healthy"
    except Exception as e:
        logger.error("Qdrant health check failed", error=str(e))
        return f"unhealthy: {str(e)}"


async def check_elasticsearch() -> str:
    """Check Elasticsearch connection."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.elasticsearch_url}/_cluster/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                status = health.get("status", "unknown")
                return f"healthy ({status})"
            else:
                return f"unhealthy: HTTP {response.status_code}"
    except Exception as e:
        logger.error("Elasticsearch health check failed", error=str(e))
        return f"unhealthy: {str(e)}"


async def check_ollama() -> str:
    """Check Ollama connection."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                tags = response.json()
                models = tags.get("models", [])
                return f"healthy ({len(models)} models)"
            else:
                return f"unhealthy: HTTP {response.status_code}"
    except Exception as e:
        logger.error("Ollama health check failed", error=str(e))
        return f"unhealthy: {str(e)}"


@router.get("/healthz", response_model=HealthCheckResponse)
async def health_check():
    """
    Basic health check endpoint.
    Returns 200 if the service is running.
    """
    return HealthCheckResponse(status="healthy", timestamp=datetime.utcnow(), version="0.1.0")


@router.get("/health/detailed", response_model=HealthCheckResponse)
async def detailed_health_check():
    """
    Detailed health check that verifies all external dependencies.
    """
    logger.info("Running detailed health check")

    # Run all checks concurrently
    tasks = {
        "postgres": check_postgres(),
        "qdrant": check_qdrant(),
        "elasticsearch": check_elasticsearch(),
        "ollama": check_ollama(),
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Map results back to service names
    services = {}
    for i, (service_name, _) in enumerate(tasks.items()):
        result = results[i]
        if isinstance(result, Exception):
            services[service_name] = f"error: {str(result)}"
        else:
            services[service_name] = result

    # Determine overall status
    overall_status = "healthy"
    for service_status in services.values():
        if not service_status.startswith("healthy"):
            overall_status = "degraded"
            break

    # Log results
    unhealthy_services = [
        name for name, status in services.items() if not status.startswith("healthy")
    ]

    if unhealthy_services:
        logger.warning(
            "Some services are unhealthy", unhealthy_services=unhealthy_services, services=services
        )
    else:
        logger.info("All services are healthy", services=services)

    return HealthCheckResponse(
        status=overall_status, timestamp=datetime.utcnow(), version="0.1.0", services=services
    )


@router.get("/ready")
async def readiness_check():
    """
    Readiness check for Kubernetes.
    Returns 200 if the service is ready to accept traffic.
    """
    # Check critical dependencies
    critical_services = ["postgres", "qdrant"]

    try:
        postgres_status = await check_postgres()
        qdrant_status = await check_qdrant()

        if not postgres_status.startswith("healthy"):
            raise HTTPException(status_code=503, detail=f"PostgreSQL not ready: {postgres_status}")

        if not qdrant_status.startswith("healthy"):
            raise HTTPException(status_code=503, detail=f"Qdrant not ready: {qdrant_status}")

        return {"status": "ready", "timestamp": datetime.utcnow()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")
