"""Rate limiting middleware for LAB 05 (Redis)."""

import re
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.infrastructure.cache_keys import payment_rate_limit_key
from app.infrastructure.redis_client import get_redis


_PAY_PATH_RE = re.compile(
    r"^/api/orders/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/pay$"
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting для endpoint оплаты.

    Ограничивает POST-запросы к:
    - /api/orders/{uuid}/pay
    - /api/payments/retry-demo
    """

    def __init__(self, app, limit_per_window: int = 5, window_seconds: int = 10):
        super().__init__(app)
        self.limit_per_window = limit_per_window
        self.window_seconds = window_seconds

    def _should_limit(self, request: Request) -> bool:
        if request.method.upper() != "POST":
            return False
        path = request.url.path
        if path == "/api/payments/retry-demo":
            return True
        return bool(_PAY_PATH_RE.match(path))

    def _subject(self, request: Request) -> str:
        xfwd = request.headers.get("x-forwarded-for")
        if xfwd:
            return xfwd.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _rate_headers(self, remaining: int, reset_ts: int) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit_per_window),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(reset_ts),
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._should_limit(request):
            return await call_next(request)

        try:
            redis = get_redis()
        except Exception:
            return await call_next(request)

        subject = self._subject(request)
        key = payment_rate_limit_key(subject)

        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, self.window_seconds)
            ttl_ms = await redis.pttl(key)
            ttl_sec = self.window_seconds
            if ttl_ms and ttl_ms > 0:
                ttl_sec = max(1, int(ttl_ms / 1000))
            reset_ts = int(time.time()) + ttl_sec
        except Exception:
            return await call_next(request)

        remaining = self.limit_per_window - count
        hdrs = self._rate_headers(remaining, reset_ts)

        if count > self.limit_per_window:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests"},
                headers=hdrs,
            )

        response = await call_next(request)
        for name, value in hdrs.items():
            response.headers[name] = value
        return response
