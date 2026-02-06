from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import channels, stocks

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup - only start background runner in non-Lambda environment
    if not settings.is_lambda:
        from app.services.background_tasks import start_background_runner
        start_background_runner()
    yield
    # Shutdown - nothing to clean up


app = FastAPI(
    title=settings.app_name,
    description="Track YouTube stock pick recommendations and their performance",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(channels.router, prefix="/api", tags=["channels"])
app.include_router(stocks.router, prefix="/api", tags=["stocks"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
    }
