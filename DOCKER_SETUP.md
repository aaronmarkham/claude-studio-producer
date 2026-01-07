# Docker Development Environment - Setup Guide

This guide walks through building and testing the Docker development environment.

## Prerequisites

**Required:**
- **Docker Desktop** - Must be installed AND running
  - Download: https://www.docker.com/products/docker-desktop
  - Windows: Start from Start Menu before running setup
  - Mac: Start from Applications folder
  - Linux: `sudo systemctl start docker`

**Optional (for testing):**
- Git (for cloning the repo)
- curl and jq (for testing API endpoints)
  - Windows: Install via Chocolatey or WSL
  - Mac: Install via Homebrew (`brew install jq`)
  - Linux: Usually pre-installed

## Quick Start (TL;DR)

```bash
# 0. IMPORTANT: Start Docker Desktop first!
#    Windows: Start Menu → Docker Desktop
#    Mac: Applications → Docker Desktop
#    Linux: sudo systemctl start docker

# 1. First-time setup (builds image, creates .env)
./scripts/dev.sh setup

# 2. Edit .env and add your ANTHROPIC_API_KEY
#    (Or use mock mode without API key)

# 3. Start the server
./scripts/dev.sh up

# 4. Test it works
curl http://localhost:8000/health

# 5. View API docs
open http://localhost:8000/docs  # Mac
start http://localhost:8000/docs  # Windows
xdg-open http://localhost:8000/docs  # Linux
```

## Step-by-Step Setup

### 0. Start Docker Desktop

**BEFORE running any commands, ensure Docker Desktop is running!**

**Windows:**
```bash
# Start Docker Desktop from Start Menu
# Wait for "Docker Desktop is running" notification
```

**Mac:**
```bash
# Open Docker Desktop from Applications
# Wait for whale icon in menu bar to show "Docker Desktop is running"
```

**Linux:**
```bash
# Start Docker daemon
sudo systemctl start docker

# Verify it's running
docker info
```

If you see this error: `error during connect: ... cannot find the file specified`
→ Docker Desktop is not running. Start it first!

### 1. Build the Docker Image

The first time (or after changing dependencies), build the image:

```bash
# From project root
cd docker
docker-compose build

# Or use the convenience script
cd ..
./scripts/dev.sh build
```

This will:
- Pull Python 3.11-slim base image
- Install system dependencies (ffmpeg, git, curl)
- Install Python packages from requirements.txt
- Install dev dependencies from requirements-dev.txt
- Install the project in editable mode

**Expected output:**
```
[+] Building 45.2s (15/15) FINISHED
 => [internal] load build definition from Dockerfile
 => => transferring dockerfile: 721B
 ...
 => exporting to image
 => => writing image sha256:abc123...
```

**Build time:** ~2-5 minutes (first time), ~10-30 seconds (with cache)

### 2. Start the Container

```bash
./scripts/dev.sh up
```

This will:
- Start the container in detached mode (-d)
- Mount the repo to /app (hot reload enabled)
- Expose port 8000
- Run uvicorn with --reload

**Expected output:**
```
[INFO] Starting Claude Studio Producer in development mode...
Creating network "docker_default" with the default driver
Creating docker_studio_1 ... done

Started at http://localhost:8000
  - API docs: http://localhost:8000/docs
  - Health: http://localhost:8000/health

View logs: ./scripts/dev.sh logs
```

### 3. Verify Server is Running

#### Check Container Status
```bash
docker-compose -f docker/docker-compose.yml ps
# or
./scripts/dev.sh ps
```

**Expected output:**
```
    Name                  Command               State           Ports
--------------------------------------------------------------------------------
docker_studio_1   /entrypoint.sh uvicorn ...   Up      0.0.0.0:8000->8000/tcp
```

#### Check Health Endpoint
```bash
curl http://localhost:8000/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "service": "claude-studio-producer",
  "version": "0.1.0",
  "mode": "mock",
  "debug": true,
  "env": "development"
}
```

#### View Server Logs
```bash
./scripts/dev.sh logs
```

**Expected output:**
```
studio_1  | ==================================================
studio_1  | Claude Studio Producer - FastAPI Server
studio_1  | ==================================================
studio_1  | Environment: development
studio_1  | Debug: True
studio_1  | Provider Mode: mock
studio_1  | Artifact Dir: /artifacts
studio_1  | ==================================================
studio_1  | [INFO] Running in MOCK mode - using mock providers
studio_1  | INFO:     Will watch for changes in these directories: ['/app']
studio_1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
studio_1  | INFO:     Started reloader process [1] using StatReload
studio_1  | INFO:     Started server process [8]
studio_1  | INFO:     Waiting for application startup.
studio_1  | INFO:     Application startup complete.
```

### 4. Test API Endpoints

#### Test Root Endpoint
```bash
curl http://localhost:8000/ | jq
```

#### List Available Agents
```bash
curl http://localhost:8000/agents | jq
# or
./scripts/invoke.sh list agents
```

**Expected output:**
```json
{
  "agents": [
    {"name": "producer", "module": "agents.producer.ProducerAgent"},
    {"name": "critic", "module": "agents.critic.CriticAgent"},
    ...
  ]
}
```

#### List Available Workflows
```bash
curl http://localhost:8000/workflows | jq
# or
./scripts/invoke.sh list workflows
```

#### Test Agent Invocation
```bash
./scripts/invoke.sh agent producer '{
  "inputs": {
    "user_request": "Test video about AI development",
    "total_budget": 100.0
  }
}'
```

**Expected:** Should return pilot strategies (this will call Claude API if ANTHROPIC_API_KEY is set)

#### Test Workflow Invocation (Async)
```bash
./scripts/invoke.sh workflow full_production '{
  "inputs": {
    "user_request": "A quick test video",
    "total_budget": 50.0
  },
  "run_async": true
}'
```

**Expected output:**
```json
{
  "run_id": "abc12345",
  "workflow": "full_production",
  "status": "running",
  "result": null,
  "message": "Workflow started. Poll /workflows/status/abc12345 for updates."
}
```

#### Check Workflow Status
```bash
./scripts/invoke.sh status abc12345
```

### 5. Test Hot Reload

1. Make a change to any Python file (e.g., add a comment in `server/main.py`)
2. Save the file
3. Watch the logs - you should see:
   ```
   INFO:     Detected file change in 'server/main.py'
   INFO:     Reloading...
   ```

The server automatically restarts without rebuilding!

### 6. Test Interactive Shell

```bash
./scripts/dev.sh shell
```

Inside the container:
```bash
# Check Python version
python --version

# Test imports
python -c "from agents.producer import ProducerAgent; print('OK')"

# Run tests
pytest tests/unit/test_producer.py -v

# Exit
exit
```

## Common Issues and Solutions

### Issue: Port 8000 already in use

**Error:**
```
Error starting userland proxy: listen tcp4 0.0.0.0:8000: bind: address already in use
```

**Solution:**
```bash
# Find what's using port 8000
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Kill it or use a different port in docker-compose.yml
# Change "8000:8000" to "8001:8000"
```

### Issue: Build fails with dependency errors

**Error:**
```
ERROR: Could not find a version that satisfies the requirement <package>
```

**Solution:**
```bash
# Clear Docker build cache
docker builder prune

# Rebuild without cache
docker-compose -f docker/docker-compose.yml build --no-cache
```

### Issue: Module import errors

**Error:**
```
ModuleNotFoundError: No module named 'agents'
```

**Solution:**
```bash
# Restart the container to pick up code changes
./scripts/dev.sh restart

# Or rebuild if you changed setup.py/pyproject.toml
./scripts/dev.sh build
```

### Issue: Healthcheck failing

**Error:**
```
Healthcheck: unhealthy
```

**Solution:**
```bash
# Check logs for errors
./scripts/dev.sh logs

# Common causes:
# - Missing .env file with ANTHROPIC_API_KEY
# - Syntax error in Python code
# - Dependency installation failed
```

## Environment Variables

Create a `.env` file in the project root:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional (for live mode)
RUNWAY_API_KEY=...
ELEVENLABS_API_KEY=...
OPENAI_API_KEY=...

# Override defaults
ENV=development
DEBUG=true
PROVIDER_MODE=mock
ARTIFACT_DIR=/artifacts
```

## Testing in LIVE Mode

**⚠️ Warning:** This will use real API credits!

```bash
# 1. Ensure API keys are in .env
echo $ANTHROPIC_API_KEY  # Should not be empty

# 2. Start in live mode
./scripts/dev.sh live

# 3. Test with a small budget
./scripts/invoke.sh agent producer '{
  "inputs": {
    "user_request": "Very short test",
    "total_budget": 5.0
  }
}'
```

## Cleanup

```bash
# Stop containers
./scripts/dev.sh down

# Remove containers and volumes
./scripts/dev.sh clean

# Remove Docker image
docker rmi claude-studio-producer:latest
```

## Next Steps

Once the Docker environment is working:

1. **Explore the API**: http://localhost:8000/docs
2. **Run the full workflow**: See examples in `scripts/invoke.sh`
3. **Develop agents**: Edit files in `agents/`, changes apply instantly
4. **Add new endpoints**: Modify `server/routes/*.py`
5. **Run tests**: `./scripts/dev.sh test`

## Architecture Reference

```
┌─────────────────────────────────────┐
│         HOST MACHINE                │
│  ┌──────────┐      ┌──────────┐    │
│  │ VS Code  │      │ Browser  │    │
│  └────┬─────┘      └────┬─────┘    │
│       │                 │           │
│       └────────┬────────┘           │
│                ▼                    │
│       http://localhost:8000         │
├────────────────┼────────────────────┤
│    DOCKER      ▼                    │
│  ┌─────────────────────────┐        │
│  │  FastAPI Server         │        │
│  │  /agents, /workflows    │        │
│  │  /artifacts             │        │
│  └─────────────────────────┘        │
│  Volumes:                           │
│  - .:/app (hot reload)              │
│  - ./artifacts:/artifacts           │
│  - ./.env:/app/.env                 │
└─────────────────────────────────────┘
```

## Troubleshooting Checklist

- [ ] Docker Desktop is running
- [ ] Built the image: `./scripts/dev.sh build`
- [ ] Started the container: `./scripts/dev.sh up`
- [ ] Container is running: `./scripts/dev.sh ps`
- [ ] Port 8000 is available: `curl localhost:8000/health`
- [ ] .env file exists with ANTHROPIC_API_KEY
- [ ] Logs show no errors: `./scripts/dev.sh logs`
- [ ] Can access docs: http://localhost:8000/docs

If all checks pass, you're ready to develop! 🚀
