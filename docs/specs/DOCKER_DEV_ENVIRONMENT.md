---
layout: default
title: Docker Development Environment Specification
---
# Docker Development Environment Specification

## Overview

This document outlines a Docker-based development environment that enables rapid iteration on agents and workflows. Inspired by the AgentCore pattern, it provides:

1. **Hot Reload**: Mount repo into container, changes apply instantly
2. **Offline Development**: Test with mocks, switch to real APIs when ready
3. **Artifact Persistence**: Reuse outputs from previous runs
4. **Credential Mounting**: AWS/API keys available without baking into image
5. **Local API Server**: Invoke agents/workflows via HTTP endpoints

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                             │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   VS Code    │    │   Claude     │    │   Browser    │      │
│  │   + Claude   │    │   Desktop    │    │   (UI)       │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         └───────────────────┼───────────────────┘               │
│                             │                                    │
│                             ▼                                    │
│                    http://localhost:8000                         │
│                             │                                    │
├─────────────────────────────┼────────────────────────────────────┤
│                             │                                    │
│                    DOCKER CONTAINER                              │
│  ┌──────────────────────────┼──────────────────────────────┐    │
│  │                          ▼                              │    │
│  │  ┌─────────────────────────────────────────────────┐   │    │
│  │  │              FastAPI Server (:8000)             │   │    │
│  │  │                                                 │   │    │
│  │  │  POST /agents/{name}/run                        │   │    │
│  │  │  POST /workflows/{name}/run                     │   │    │
│  │  │  GET  /artifacts/{id}                           │   │    │
│  │  │  GET  /health                                   │   │    │
│  │  └─────────────────────────────────────────────────┘   │    │
│  │                          │                              │    │
│  │         ┌────────────────┼────────────────┐            │    │
│  │         ▼                ▼                ▼            │    │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────────┐     │    │
│  │  │  Agents  │    │ Workflows│    │   Providers  │     │    │
│  │  └──────────┘    └──────────┘    └──────────────┘     │    │
│  │                                                        │    │
│  │  MOUNTED VOLUMES:                                      │    │
│  │  ├── /app              ← ~/GitHub/claude-studio-producer   │
│  │  ├── /artifacts        ← ./artifacts (persistent)     │    │
│  │  ├── /root/.aws        ← ~/.aws (credentials)         │    │
│  │  └── /.env             ← ./.env (API keys)            │    │
│  │                                                        │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
claude-studio-producer/
├── docker/
│   ├── Dockerfile              # Development image
│   ├── Dockerfile.prod         # Production image
│   ├── docker-compose.yml      # Local development
│   ├── docker-compose.prod.yml # Production deployment
│   └── entrypoint.sh           # Container startup
│
├── server/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── agents.py           # /agents/* endpoints
│   │   ├── workflows.py        # /workflows/* endpoints
│   │   └── artifacts.py        # /artifacts/* endpoints
│   └── models/
│       ├── __init__.py
│       └── requests.py         # Pydantic request/response models
│
├── artifacts/                  # Persistent output storage (mounted)
│   ├── videos/
│   ├── audio/
│   ├── scripts/
│   └── runs/                   # Full run outputs by ID
│
├── agents/
├── workflows/
├── core/
├── tests/
└── ...
```

## Docker Configuration

### Dockerfile (Development)

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install development dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Install the package in editable mode
# This will be overridden by volume mount, but ensures deps are right
COPY . .
RUN pip install -e .

# Create artifacts directory
RUN mkdir -p /artifacts

# Expose API port
EXPOSE 8000

# Default command - can be overridden
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### docker-compose.yml (Development)

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  studio:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    volumes:
      # Mount repo for hot reload
      - ..:/app
      
      # Persist artifacts between runs
      - ../artifacts:/artifacts
      
      # Mount AWS credentials (optional)
      - ~/.aws:/root/.aws:ro
      
      # Mount environment file
      - ../.env:/app/.env:ro
    
    environment:
      # Development mode
      - ENV=development
      - DEBUG=true
      
      # Provider mode: "mock" or "live"
      - PROVIDER_MODE=mock
      
      # Artifact storage
      - ARTIFACT_DIR=/artifacts
      
      # Load from .env file
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - RUNWAY_API_KEY=${RUNWAY_API_KEY:-}
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY:-}
    
    # Keep container running for development
    stdin_open: true
    tty: true
    
    # Healthcheck
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Optional: Redis for caching/queuing
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

## FastAPI Server

### server/main.py

```python
"""
FastAPI server for invoking agents and workflows.
Enables rapid development with hot reload.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from server.routes import agents, workflows, artifacts
from server.config import settings
from core.providers.base import ProviderRegistry


# Global registry - configured at startup
provider_registry: ProviderRegistry = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure providers based on PROVIDER_MODE"""
    global provider_registry
    
    provider_registry = ProviderRegistry()
    
    if settings.provider_mode == "mock":
        print("🔧 Starting in MOCK mode")
        from tests.mocks.providers import (
            MockVideoProvider, MockAudioProvider, MockMusicProvider
        )
        provider_registry.register_video(MockVideoProvider())
        provider_registry.register_audio(MockAudioProvider())
        provider_registry.register_music(MockMusicProvider())
    else:
        print("🚀 Starting in LIVE mode")
        from core.providers.video.runway import RunwayProvider
        from core.providers.audio.elevenlabs import ElevenLabsProvider
        provider_registry.register_video(RunwayProvider())
        provider_registry.register_audio(ElevenLabsProvider())
    
    yield
    
    print("Shutting down...")


app = FastAPI(
    title="Claude Studio Producer",
    description="Multi-agent video production API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return {
        "status": "healthy",
        "mode": settings.provider_mode,
        "debug": settings.debug
    }


@app.get("/")
async def root():
    return {
        "name": "Claude Studio Producer",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "agents": "/agents",
            "workflows": "/workflows",
            "artifacts": "/artifacts"
        }
    }
```

### server/config.py

```python
"""Server configuration"""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # Environment
    env: Literal["development", "production"] = "development"
    debug: bool = True
    
    # Provider mode
    provider_mode: Literal["mock", "live"] = "mock"
    
    # Storage
    artifact_dir: str = "/artifacts"
    
    # API Keys (loaded from .env)
    anthropic_api_key: str = ""
    runway_api_key: str = ""
    elevenlabs_api_key: str = ""
    
    class Config:
        env_file = ".env"


settings = Settings()
```

### server/routes/agents.py

```python
"""Agent invocation endpoints"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import uuid

from server.main import provider_registry
from server.models.requests import AgentRequest, AgentResponse
from core.claude_client import ClaudeClient


router = APIRouter()

# Agent registry
AGENTS = {
    "producer": "agents.producer.ProducerAgent",
    "critic": "agents.critic.CriticAgent",
    "script_writer": "agents.script_writer.ScriptWriterAgent",
    "video_generator": "agents.video_generator.VideoGeneratorAgent",
    "audio_generator": "agents.audio_generator.AudioGeneratorAgent",
    "qa_verifier": "agents.qa_verifier.QAVerifierAgent",
    "editor": "agents.editor.EditorAgent",
}


@router.get("/")
async def list_agents():
    """List available agents"""
    return {
        "agents": list(AGENTS.keys())
    }


@router.post("/{agent_name}/run")
async def run_agent(agent_name: str, request: AgentRequest) -> AgentResponse:
    """
    Invoke an agent by name.
    
    Example:
        POST /agents/producer/run
        {
            "inputs": {
                "user_request": "Create a 60-second developer video",
                "total_budget": 150.0
            }
        }
    """
    if agent_name not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    try:
        # Dynamic import
        module_path = AGENTS[agent_name]
        module_name, class_name = module_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        agent_class = getattr(module, class_name)
        
        # Instantiate with providers
        claude = ClaudeClient()
        
        if agent_name == "video_generator":
            agent = agent_class(
                claude_client=claude,
                video_provider=provider_registry.get_video("mock_video")
            )
        elif agent_name == "audio_generator":
            agent = agent_class(
                claude_client=claude,
                audio_provider=provider_registry.get_audio("mock_audio")
            )
        else:
            agent = agent_class(claude_client=claude)
        
        # Run agent
        result = await agent.run(**request.inputs)
        
        # Generate run ID
        run_id = str(uuid.uuid4())[:8]
        
        return AgentResponse(
            run_id=run_id,
            agent=agent_name,
            status="completed",
            result=result
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_name}/schema")
async def get_agent_schema(agent_name: str):
    """Get input/output schema for an agent"""
    if agent_name not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    # Return schema info (could be generated from type hints)
    schemas = {
        "producer": {
            "inputs": {
                "user_request": "str - Video concept description",
                "total_budget": "float - Total budget in USD"
            },
            "outputs": "List[PilotStrategy]"
        },
        "script_writer": {
            "inputs": {
                "video_concept": "str - Video concept",
                "target_duration": "int - Duration in seconds",
                "num_scenes": "int - Number of scenes"
            },
            "outputs": "List[Scene]"
        },
        # ... add others
    }
    
    return schemas.get(agent_name, {"inputs": {}, "outputs": "unknown"})
```

### server/routes/workflows.py

```python
"""Workflow invocation endpoints"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Any, Dict, Optional
import uuid
import asyncio
from datetime import datetime

from server.main import provider_registry
from server.config import settings
from server.models.requests import WorkflowRequest, WorkflowResponse
from workflows.orchestrator import StudioOrchestrator


router = APIRouter()

# Track running workflows
RUNNING_WORKFLOWS: Dict[str, Dict] = {}


@router.get("/")
async def list_workflows():
    """List available workflows"""
    return {
        "workflows": [
            {
                "name": "full_production",
                "description": "Complete video production pipeline"
            },
            {
                "name": "pilot_only",
                "description": "Run pilot phase only (test scenes)"
            },
            {
                "name": "audio_only",
                "description": "Generate audio for existing scenes"
            }
        ]
    }


@router.post("/{workflow_name}/run")
async def run_workflow(
    workflow_name: str, 
    request: WorkflowRequest,
    background_tasks: BackgroundTasks
) -> WorkflowResponse:
    """
    Start a workflow.
    
    Example:
        POST /workflows/full_production/run
        {
            "inputs": {
                "user_request": "Create a 60-second developer video",
                "total_budget": 150.0
            },
            "async": true
        }
    """
    run_id = str(uuid.uuid4())[:8]
    
    if workflow_name == "full_production":
        orchestrator = StudioOrchestrator(
            provider_registry=provider_registry,
            debug=settings.debug
        )
        
        if request.run_async:
            # Run in background
            background_tasks.add_task(
                _run_workflow_async,
                run_id,
                orchestrator,
                request.inputs
            )
            
            return WorkflowResponse(
                run_id=run_id,
                workflow=workflow_name,
                status="running",
                result=None,
                message="Workflow started. Poll /workflows/status/{run_id} for updates."
            )
        else:
            # Run synchronously
            result = await orchestrator.run(**request.inputs)
            
            return WorkflowResponse(
                run_id=run_id,
                workflow=workflow_name,
                status="completed",
                result=result
            )
    else:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_name}' not found")


async def _run_workflow_async(run_id: str, orchestrator, inputs: Dict):
    """Run workflow in background and store result"""
    RUNNING_WORKFLOWS[run_id] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "result": None,
        "error": None
    }
    
    try:
        result = await orchestrator.run(**inputs)
        RUNNING_WORKFLOWS[run_id]["status"] = "completed"
        RUNNING_WORKFLOWS[run_id]["result"] = result
    except Exception as e:
        RUNNING_WORKFLOWS[run_id]["status"] = "failed"
        RUNNING_WORKFLOWS[run_id]["error"] = str(e)


@router.get("/status/{run_id}")
async def get_workflow_status(run_id: str):
    """Get status of a running/completed workflow"""
    if run_id not in RUNNING_WORKFLOWS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    return RUNNING_WORKFLOWS[run_id]


@router.post("/{workflow_name}/resume/{run_id}")
async def resume_workflow(workflow_name: str, run_id: str):
    """
    Resume a workflow from a previous run's artifacts.
    Useful for:
    - Continuing after a failure
    - Re-running with modified agents
    - Testing changes without regenerating everything
    """
    artifact_path = f"{settings.artifact_dir}/runs/{run_id}"
    
    # Load previous state
    # ... implementation depends on what we persist
    
    return {"message": f"Resuming {workflow_name} from run {run_id}"}
```

### server/routes/artifacts.py

```python
"""Artifact management endpoints"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from pathlib import Path
from typing import List

from server.config import settings


router = APIRouter()


@router.get("/")
async def list_artifacts():
    """List all artifact categories"""
    artifact_dir = Path(settings.artifact_dir)
    
    categories = []
    for item in artifact_dir.iterdir():
        if item.is_dir():
            count = len(list(item.glob("*")))
            categories.append({
                "name": item.name,
                "count": count
            })
    
    return {"categories": categories}


@router.get("/{category}")
async def list_category_artifacts(category: str):
    """List artifacts in a category"""
    category_dir = Path(settings.artifact_dir) / category
    
    if not category_dir.exists():
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    
    artifacts = []
    for item in category_dir.iterdir():
        artifacts.append({
            "name": item.name,
            "size": item.stat().st_size if item.is_file() else None,
            "type": "file" if item.is_file() else "directory"
        })
    
    return {"artifacts": artifacts}


@router.get("/{category}/{artifact_id}")
async def get_artifact(category: str, artifact_id: str):
    """Get/download an artifact"""
    artifact_path = Path(settings.artifact_dir) / category / artifact_id
    
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact not found")
    
    return FileResponse(artifact_path)


@router.get("/runs/{run_id}")
async def get_run_artifacts(run_id: str):
    """Get all artifacts from a specific run"""
    run_dir = Path(settings.artifact_dir) / "runs" / run_id
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    artifacts = []
    for item in run_dir.rglob("*"):
        if item.is_file():
            artifacts.append({
                "path": str(item.relative_to(run_dir)),
                "size": item.stat().st_size
            })
    
    return {
        "run_id": run_id,
        "artifacts": artifacts
    }
```

### server/models/requests.py

```python
"""Pydantic models for API requests/responses"""

from pydantic import BaseModel
from typing import Any, Dict, Optional, List


class AgentRequest(BaseModel):
    inputs: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "inputs": {
                    "user_request": "Create a 60-second developer video",
                    "total_budget": 150.0
                }
            }
        }


class AgentResponse(BaseModel):
    run_id: str
    agent: str
    status: str
    result: Any
    error: Optional[str] = None


class WorkflowRequest(BaseModel):
    inputs: Dict[str, Any]
    run_async: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "inputs": {
                    "user_request": "Create a 60-second developer video",
                    "total_budget": 150.0
                },
                "async": True
            }
        }


class WorkflowResponse(BaseModel):
    run_id: str
    workflow: str
    status: str
    result: Any = None
    message: Optional[str] = None
    error: Optional[str] = None
```

## Development Workflow

### Quick Start

```bash
# Start the container
cd docker
docker-compose up -d

# Check it's running
curl http://localhost:8000/health
# {"status":"healthy","mode":"mock","debug":true}

# View API docs
open http://localhost:8000/docs
```

### Hot Reload Development

```bash
# Make changes in VS Code / your IDE
# Changes are automatically picked up (uvicorn --reload)

# Test an agent
curl -X POST http://localhost:8000/agents/producer/run \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "user_request": "Create a 60-second developer video",
      "total_budget": 150.0
    }
  }'
```

### Switch to Live APIs

```bash
# Stop current container
docker-compose down

# Start with live mode
PROVIDER_MODE=live docker-compose up -d

# Now it uses real APIs (requires valid keys in .env)
```

### Run Full Workflow

```bash
# Async run (returns immediately)
curl -X POST http://localhost:8000/workflows/full_production/run \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "user_request": "A day in the life of a developer",
      "total_budget": 150.0
    },
    "async": true
  }'
# {"run_id":"abc123","status":"running",...}

# Check status
curl http://localhost:8000/workflows/status/abc123

# Get artifacts when done
curl http://localhost:8000/artifacts/runs/abc123
```

### Resume from Previous Run

```bash
# Made changes to an agent? Resume without re-running everything
curl -X POST http://localhost:8000/workflows/full_production/resume/abc123
```

### Access Container Shell

```bash
# Get into the container for debugging
docker-compose exec studio bash

# Run tests inside container
pytest tests/

# Run a specific agent manually
python -c "
import asyncio
from agents.producer import ProducerAgent
from core.claude_client import ClaudeClient

async def test():
    agent = ProducerAgent(ClaudeClient())
    result = await agent.run('test video', 100.0)
    print(result)

asyncio.run(test())
"
```

## Convenience Scripts

### scripts/dev.sh

```bash
#!/bin/bash
# Quick development commands

case "$1" in
  up)
    docker-compose -f docker/docker-compose.yml up -d
    echo "🚀 Started at http://localhost:8000"
    ;;
  down)
    docker-compose -f docker/docker-compose.yml down
    ;;
  logs)
    docker-compose -f docker/docker-compose.yml logs -f
    ;;
  shell)
    docker-compose -f docker/docker-compose.yml exec studio bash
    ;;
  test)
    docker-compose -f docker/docker-compose.yml exec studio pytest tests/ -v
    ;;
  live)
    PROVIDER_MODE=live docker-compose -f docker/docker-compose.yml up -d
    echo "🚀 Started in LIVE mode"
    ;;
  *)
    echo "Usage: $0 {up|down|logs|shell|test|live}"
    exit 1
    ;;
esac
```

### scripts/invoke.sh

```bash
#!/bin/bash
# Quick agent/workflow invocation

ENDPOINT=${ENDPOINT:-http://localhost:8000}

case "$1" in
  agent)
    curl -s -X POST "$ENDPOINT/agents/$2/run" \
      -H "Content-Type: application/json" \
      -d "$3" | jq
    ;;
  workflow)
    curl -s -X POST "$ENDPOINT/workflows/$2/run" \
      -H "Content-Type: application/json" \
      -d "$3" | jq
    ;;
  status)
    curl -s "$ENDPOINT/workflows/status/$2" | jq
    ;;
  *)
    echo "Usage: $0 {agent|workflow|status} <name> [json_body]"
    echo "Example: $0 agent producer '{\"inputs\":{\"user_request\":\"test\",\"total_budget\":100}}'"
    exit 1
    ;;
esac
```

## Artifact Persistence Strategy

### What Gets Persisted

```
artifacts/
├── runs/
│   └── {run_id}/
│       ├── metadata.json       # Run config, timing, status
│       ├── pilots/
│       │   ├── pilot_a/
│       │   │   ├── strategy.json
│       │   │   ├── scenes/
│       │   │   └── evaluation.json
│       │   └── pilot_b/
│       │       └── ...
│       ├── videos/
│       │   ├── scene_1_v1.mp4
│       │   ├── scene_1_v2.mp4
│       │   └── ...
│       ├── audio/
│       │   ├── voiceover.mp3
│       │   └── music.mp3
│       └── final/
│           └── edit_candidates.json
│
├── videos/                    # All generated videos
├── audio/                     # All generated audio
└── scripts/                   # All generated scripts
```

### Resume Capability

```python
# In workflows/orchestrator.py

class StudioOrchestrator:
    
    async def resume_from(self, run_id: str, from_stage: str = "auto"):
        """
        Resume a previous run from a specific stage.
        
        Stages:
        - planning: Re-run everything
        - pilots: Skip planning, reuse pilot strategies
        - evaluation: Skip pilot execution, reuse generated scenes
        - completion: Skip evaluation, continue approved pilots
        - editing: Skip production, go straight to editing
        """
        
        run_dir = Path(settings.artifact_dir) / "runs" / run_id
        metadata = json.load(open(run_dir / "metadata.json"))
        
        if from_stage == "auto":
            from_stage = metadata.get("last_completed_stage", "planning")
        
        # Load artifacts from previous stages
        if from_stage in ["pilots", "evaluation", "completion", "editing"]:
            self.pilots = self._load_pilots(run_dir)
        
        if from_stage in ["evaluation", "completion", "editing"]:
            self.test_results = self._load_test_results(run_dir)
        
        if from_stage in ["completion", "editing"]:
            self.evaluations = self._load_evaluations(run_dir)
        
        # Continue from specified stage
        return await self._run_from_stage(from_stage)
```

## Environment Variables Reference

```bash
# .env file

# Mode
ENV=development
DEBUG=true
PROVIDER_MODE=mock  # or "live"

# Storage
ARTIFACT_DIR=/artifacts

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Video Providers
RUNWAY_API_KEY=...
PIKA_API_KEY=...
STABILITY_API_KEY=...

# Audio Providers
ELEVENLABS_API_KEY=...
OPENAI_API_KEY=...

# AWS (for S3 storage)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-west-2

# Optional
REDIS_URL=redis://redis:6379
```

## Summary

This Docker setup provides:

| Feature | Benefit |
|---------|---------|
| Hot reload | Edit code, see changes instantly |
| Mock mode | Develop without burning API credits |
| Live mode | Test with real APIs when ready |
| Mounted volumes | IDE changes apply immediately |
| Artifact persistence | Reuse outputs, resume runs |
| HTTP API | Easy testing from CLI, browser, or other tools |
| AWS credentials | Access S3, other AWS services |
| Container shell | Debug inside the environment |

The workflow is:
1. Start container (`./scripts/dev.sh up`)
2. Make changes in IDE
3. Test via API (`curl localhost:8000/agents/...`)
4. Changes apply instantly (no rebuild)
5. Switch to live mode when ready
