"""
FastAPI server for Claude Studio Producer

Provides HTTP API for invoking agents and workflows with hot reload support.
"""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.routes import agents, workflows, artifacts
from server.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown logic"""
    # Startup
    print("=" * 50)
    print("Claude Studio Producer - FastAPI Server")
    print("=" * 50)
    print(f"Environment: {settings.env}")
    print(f"Debug: {settings.debug}")
    print(f"Provider Mode: {settings.provider_mode}")
    print(f"Artifact Dir: {settings.artifact_dir}")
    print("=" * 50)

    # Ensure artifact directory exists
    Path(settings.artifact_dir).mkdir(parents=True, exist_ok=True)

    # Initialize providers based on mode
    if settings.provider_mode == "live":
        print("[INFO] Running in LIVE mode - using real API providers")
        print("[WARN] Ensure API keys are set in .env file")
    else:
        print("[INFO] Running in MOCK mode - using mock providers")

    yield

    # Shutdown
    print("\nShutting down Claude Studio Producer server...")


# Create FastAPI app
app = FastAPI(
    title="Claude Studio Producer",
    description="Multi-agent video production API with Strands orchestration",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
app.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts"])


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "claude-studio-producer",
        "version": "0.1.0",
        "mode": settings.provider_mode,
        "debug": settings.debug,
        "env": settings.env
    }


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Claude Studio Producer",
        "version": "0.1.0",
        "description": "Multi-agent video production API",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "endpoints": {
            "agents": {
                "list": "GET /agents",
                "run": "POST /agents/{name}/run",
                "schema": "GET /agents/{name}/schema"
            },
            "workflows": {
                "list": "GET /workflows",
                "run": "POST /workflows/{name}/run",
                "status": "GET /workflows/status/{run_id}"
            },
            "artifacts": {
                "list": "GET /artifacts",
                "category": "GET /artifacts/{category}",
                "runs": "GET /artifacts/runs/{run_id}"
            }
        }
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "detail": str(exc.detail) if hasattr(exc, "detail") else "Resource not found",
        "path": str(request.url.path)
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {
        "error": "Internal Server Error",
        "detail": str(exc),
        "path": str(request.url.path)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
