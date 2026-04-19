"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.payment_routes import router as payment_router
from app.api.cache_demo_routes import router as cache_demo_router
from app.middleware.idempotency_middleware import IdempotencyMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware

app = FastAPI(
    title="Marketplace API",
    description="DDD-based marketplace API for lab work",
    version="1.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LAB 04: middleware идемпотентности (логика дорабатывается студентами).
app.add_middleware(IdempotencyMiddleware)
# LAB 05: middleware rate limiting через Redis (логика дорабатывается студентами).
app.add_middleware(RateLimitMiddleware)

# Include routes
app.include_router(router, prefix="/api")
app.include_router(payment_router)  # Payment routes для тестирования конкурентности
app.include_router(cache_demo_router)  # LAB 05 cache consistency demo


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
