"""
Paper Broker — FastAPI application entry point.
"""
import asyncio
import signal

import asyncpg
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .portfolio import PaperPortfolio
from .publisher import create_redis
from .routes.health import router as health_router
from .routes.orders import router as orders_router
from .routes.portfolio import router as portfolio_router
from .routes.positions import router as positions_router
from .routes.warmup import router as warmup_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Okane Paper Broker",
        description="Simulated order execution for Kalshi paper trading",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Instrumentator().instrument(app).expose(app)

    app.include_router(health_router)
    app.include_router(orders_router)
    app.include_router(positions_router)
    app.include_router(portfolio_router)
    app.include_router(warmup_router)

    @app.on_event("startup")
    async def startup():
        log.info("paper_broker_starting")
        pool = await asyncpg.create_pool(
            settings.postgres_dsn, min_size=5, max_size=20
        )
        redis = await create_redis(settings.redis_url)
        portfolio = PaperPortfolio(pool=pool, redis=redis)
        await portfolio.ensure_initialized()

        app.state.pool = pool
        app.state.redis = redis
        app.state.portfolio = portfolio
        log.info("paper_broker_ready", port=settings.port)

    @app.on_event("shutdown")
    async def shutdown():
        await app.state.pool.close()
        await app.state.redis.aclose()
        log.info("paper_broker_stopped")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )
