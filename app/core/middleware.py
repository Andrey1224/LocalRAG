"""Middleware for LocalRAG application."""

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import RequestLogger, generate_trace_id, set_trace_id


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware to add trace ID to all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract trace ID
        trace_id = request.headers.get("X-Trace-ID", generate_trace_id())
        set_trace_id(trace_id)

        # Add trace ID to request state
        request.state.trace_id = trace_id

        # Process request
        response = await call_next(request)

        # Add trace ID to response headers
        response.headers["X-Trace-ID"] = trace_id

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests."""

    def __init__(self, app, skip_paths: list = None):
        super().__init__(app)
        self.logger = RequestLogger()
        self.skip_paths = skip_paths or ["/healthz", "/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for certain paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        # Record start time
        start_time = time.time()

        # Get request details
        method = request.method
        url = request.url
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # Extract session and user info if available
        session_id = request.headers.get("X-Session-ID")
        user_id = request.headers.get("X-User-ID")

        try:
            # Process request
            response = await call_next(request)

            # Calculate timing
            latency_ms = (time.time() - start_time) * 1000

            # Log successful request
            self.logger.log_request(
                method=method,
                url=url,
                status_code=response.status_code,
                latency_ms=latency_ms,
                user_id=user_id,
                session_id=session_id,
                client_ip=client_ip,
                user_agent=user_agent,
            )

            return response

        except Exception as e:
            # Calculate timing for failed requests
            latency_ms = (time.time() - start_time) * 1000

            # Log failed request
            self.logger.log_request(
                method=method,
                url=url,
                status_code=500,
                latency_ms=latency_ms,
                user_id=user_id,
                session_id=session_id,
                client_ip=client_ip,
                user_agent=user_agent,
                error=str(e),
            )

            # Re-raise the exception
            raise


class CORSMiddleware:
    """Custom CORS middleware configuration."""

    @staticmethod
    def add_cors_headers(response: Response, origin: str = None) -> None:
        """Add CORS headers to response."""
        from app.core.config import settings

        if origin and origin in settings.cors_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers[
            "Access-Control-Allow-Headers"
        ] = "Content-Type, Authorization, X-API-Key, X-Trace-ID, X-Session-ID, X-User-ID"
        response.headers["Access-Control-Expose-Headers"] = "X-Trace-ID"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware."""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts = {}
        self.window_start = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get client identifier (IP address)
        client_ip = request.client.host if request.client else "unknown"

        # Check rate limit
        current_time = time.time()
        window_size = 60  # 1 minute

        # Initialize tracking for new clients
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = 0
            self.window_start[client_ip] = current_time

        # Reset window if needed
        if current_time - self.window_start[client_ip] > window_size:
            self.request_counts[client_ip] = 0
            self.window_start[client_ip] = current_time

        # Check if rate limit exceeded
        if self.request_counts[client_ip] >= self.requests_per_minute:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=429, detail="Rate limit exceeded. Please try again later."
            )

        # Increment request count
        self.request_counts[client_ip] += 1

        # Process request
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Add CSP header for non-API endpoints
        if not request.url.path.startswith("/api"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self';"
            )

        return response
