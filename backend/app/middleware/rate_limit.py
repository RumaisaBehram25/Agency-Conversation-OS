"""
Attora — Rate Limiting Middleware

Redis-backed sliding window rate limiter.
Limits requests per IP address (configurable per-minute limit).
"""

import time
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed rate limiting middleware using a sliding window counter.

    Rate limits are applied per client IP address. The window is 60 seconds.
    Exempt paths (health checks) bypass rate limiting.
    """

    EXEMPT_PATHS = {"/api/health/ping", "/api/health"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Try to get Redis — if unavailable, allow the request through
        try:
            from app.redis import get_redis_pool
            redis_client = get_redis_pool()
        except RuntimeError:
            # Redis not initialized — skip rate limiting
            return await call_next(request)

        # Determine client identifier (IP address)
        client_ip = request.client.host if request.client else "unknown"
        rate_key = f"ratelimit:{client_ip}"

        limit = settings.rate_limit_per_minute
        request_count: int | None = None

        try:
            current_time = time.time()
            window_start = current_time - 60  # 60-second sliding window

            # Use Redis pipeline for atomic operations
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(rate_key, 0, window_start)
            pipe.zcard(rate_key)
            pipe.zadd(rate_key, {str(current_time): current_time})
            pipe.expire(rate_key, 120)

            results = await pipe.execute()
            request_count = results[1]  # zcard result
        except Exception as e:
            # Redis failed — fail open and skip limit enforcement for this request.
            logger.warning(f"Rate limiter error (allowing request): {e}")

        if request_count is not None and request_count >= limit:
            retry_after = 60  # seconds
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        if request_count is not None:
            remaining = max(0, limit - request_count - 1)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
