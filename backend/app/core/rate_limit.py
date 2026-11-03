import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_settings


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Single-process safety limiter; production multi-worker limits belong at the gateway/Redis."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        if (
            path.endswith("/health")
            or path.endswith("/health/ready")
            or path.endswith("/openapi.json")
        ):
            return await call_next(request)
        settings = get_settings()
        client = request.client.host if request.client else "unknown"
        # Path strings can contain attacker-controlled IDs. Keying by endpoint path
        # lets one client grow the map without bound by requesting unique paths.
        limit = settings.rate_limit_per_minute
        if "/auth/" in path:
            scope = "auth"
            limit = settings.auth_rate_limit_per_minute
        elif "/voice/" in path or "/ocr-captures" in path:
            scope = "expensive"
            limit = settings.expensive_rate_limit_per_minute
        else:
            scope = "api"
        key = f"{client}:{scope}"
        now = time.monotonic()
        async with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "60"},
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests. Try again shortly.",
                        }
                    },
                )
            bucket.append(now)
            if len(self._requests) > 10_000:
                expired = [
                    k
                    for k, values in self._requests.items()
                    if not values or values[-1] <= now - 60
                ]
                for expired_key in expired:
                    self._requests.pop(expired_key, None)
                while len(self._requests) > 10_000:
                    self._requests.pop(next(iter(self._requests)))
        return await call_next(request)
