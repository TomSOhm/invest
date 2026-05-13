"""
Invest Solo -- FastAPI Application Entry Point

Run from project root:
    python -m uvicorn backend.app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.app.api.company import router as company_router
from backend.app.api.market import router as market_router
from backend.app.api.portfolio import router as portfolio_router
from backend.app.api.screener import router as screener_router
from backend.app.api.watchlist import router as watchlist_router
from backend.app.config import settings

# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Invest Solo API v0.4.0 starting up (M10 three-horizon schema)")
    logger.info(f"Project: {settings.project_name} v{settings.project_version}")
    logger.info(f"Data source: {settings.primary_source}")
    logger.info(f"PEA enabled: {settings.pea_enabled} ({len(settings.pea_eligible_countries)} countries)")
    yield
    logger.info("Invest Solo API shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Invest Solo API",
    description="Quantitative fundamental analysis API for PEA and Global investment strategies.",
    version="0.4.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Middleware
# Explicit method list + localhost regex for dev (any port). For production
# deploys, narrow allow_origins to the real frontend hostname and drop the
# regex.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# ---------------------------------------------------------------------------
# Router Registration (all under /api)
# ---------------------------------------------------------------------------
app.include_router(market_router, prefix="/api/market")
app.include_router(portfolio_router, prefix="/api/portfolio")
app.include_router(watchlist_router, prefix="/api/watchlist")
app.include_router(screener_router, prefix="/api/screener")
app.include_router(company_router, prefix="/api/company")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    """Redirect root to API docs."""
    return {
        "message": "Invest Solo API",
        "version": "0.4.0",
        "docs": "/api/docs",
    }
