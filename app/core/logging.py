"""Logging configuration for LocalRAG application."""

import logging
import logging.handlers
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.stdlib import LoggerFactory

from app.core.config import settings

# Context variable for trace ID
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Get current trace ID."""
    return trace_id_var.get()


def set_trace_id(trace_id: str) -> None:
    """Set trace ID in context."""
    trace_id_var.set(trace_id)


def generate_trace_id() -> str:
    """Generate new trace ID."""
    return str(uuid.uuid4())


def add_trace_id(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add trace ID to log record."""
    event_dict["trace_id"] = get_trace_id()
    return event_dict


def configure_logging() -> None:
    """Configure structured logging for the application."""

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        add_trace_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler for development
    if settings.env == "dev":
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        if settings.log_format == "json":
            formatter = logging.Formatter("%(message)s")
        else:
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler for production and development
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"{settings.env}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=settings.log_file_max_size,
        backupCount=settings.log_file_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    file_formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class RequestLogger:
    """Logger for HTTP requests with timing and trace ID."""

    def __init__(self):
        self.logger = get_logger("request")

    def log_request(
        self,
        method: str,
        url: str,
        status_code: int,
        latency_ms: float,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        error: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log HTTP request details."""
        log_data = {
            "method": method,
            "url": str(url),
            "status_code": status_code,
            "latency_ms": latency_ms,
            "user_id": user_id,
            "session_id": session_id,
            **kwargs,
        }

        if error:
            log_data["error"] = error
            self.logger.error("Request failed", **log_data)
        else:
            self.logger.info("Request completed", **log_data)


class ServiceLogger:
    """Logger for service operations with detailed timing."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = get_logger(f"service.{service_name}")

    def log_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log service operation details."""
        log_data = {
            "service": self.service_name,
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
            **kwargs,
        }

        if error:
            log_data["error"] = error
            self.logger.error("Operation failed", **log_data)
        else:
            self.logger.info("Operation completed", **log_data)


# Initialize logging on module import
configure_logging()
