"""
FastAPI server for Claude Studio Producer

Provides HTTP API for invoking agents and workflows with hot reload support.
"""

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.routes import agents, workflows, artifacts
from server.routes import memory as memory_routes
from server.routes import runs as runs_routes
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

# Static files mounted after app definition below

# Include routers
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
app.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts"])
app.include_router(memory_routes.router, prefix="/memory", tags=["Memory"])
app.include_router(runs_routes.router, prefix="/runs", tags=["Runs"])


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
            },
            "runs": {
                "list": "GET /runs",
                "detail": "GET /runs/{run_id}",
                "assets": "GET /runs/{run_id}/assets",
                "preview": "GET /runs/{run_id}/preview (HTML)",
                "live": "WS /runs/{run_id}/live"
            },
            "memory": {
                "overview": "GET /memory",
                "preferences": "GET/PUT /memory/preferences",
                "patterns": "GET /memory/patterns",
                "history": "GET /memory/history",
                "analytics": "GET /memory/analytics"
            }
        }
    }


# Error handlers - Note: Don't catch 404 for API routes, let FastAPI/Starlette handle them
# The StaticFiles mount handles its own 404s for /files/ paths


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "path": str(request.url.path)
        }
    )


# Mount static files for serving artifacts (videos, audio, etc.)
# Using /files prefix to avoid any conflict with API routes
artifacts_path = Path(settings.artifact_dir)
print(f"[DEBUG] Artifacts path: {artifacts_path}, exists: {artifacts_path.exists()}")
if artifacts_path.exists():
    print(f"[DEBUG] Mounting static files at /files from {artifacts_path}")
    app.mount("/files", StaticFiles(directory=str(artifacts_path)), name="static_files")
else:
    print(f"[WARN] Artifacts path does not exist, static files not mounted!")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
