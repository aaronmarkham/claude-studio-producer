# Docker Development Environment

This directory contains the Docker configuration for Claude Studio Producer.

## Quick Start

```bash
# First time setup
cd ..
./scripts/dev.sh setup

# Start the server
./scripts/dev.sh up

# Test it works
curl http://localhost:8000/health
```

## Files

- **Dockerfile** - Development image definition
  - Based on Python 3.11-slim
  - Installs ffmpeg, git, curl
  - Installs Python dependencies
  - Sets up hot reload with editable install

- **docker-compose.yml** - Container orchestration
  - Mounts repo for hot reload
  - Persists artifacts directory
  - Configures environment variables
  - Exposes port 8000
  - Includes healthcheck

- **entrypoint.sh** - Container startup script
  - Prints environment configuration
  - Creates artifact directories
  - Executes main command (uvicorn)

## Environment Variables

Set these in `.env` file in project root:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
RUNWAY_API_KEY=...
ELEVENLABS_API_KEY=...
OPENAI_API_KEY=...

# Configuration (defaults shown)
ENV=development
DEBUG=true
PROVIDER_MODE=mock
ARTIFACT_DIR=/artifacts
```

## Usage

From project root:

```bash
# Build image
./scripts/dev.sh build

# Start server
./scripts/dev.sh up

# View logs
./scripts/dev.sh logs

# Open shell in container
./scripts/dev.sh shell

# Run tests
./scripts/dev.sh test

# Stop server
./scripts/dev.sh down
```

## How It Works

1. **Build**: Docker builds image with all dependencies
2. **Mount**: Your code is mounted to `/app` in container
3. **Hot Reload**: Uvicorn watches for file changes
4. **Persistence**: Artifacts saved to `artifacts/` directory
5. **API**: Server runs on http://localhost:8000

## Volumes

- `.:/app` - Source code (read-write, hot reload)
- `./artifacts:/artifacts` - Persistent outputs
- `./.env:/app/.env:ro` - Environment variables (read-only)

## Ports

- `8000` - FastAPI server (HTTP API)

## Development Workflow

1. Edit code in your IDE (VS Code, etc.)
2. Save file
3. Uvicorn detects change and reloads
4. Test via API: `curl localhost:8000/...`
5. Changes apply instantly, no rebuild needed!

## Switching to Live Mode

```bash
# Stop current container
./scripts/dev.sh down

# Start in live mode (uses real APIs!)
./scripts/dev.sh live

# Or set in .env:
# PROVIDER_MODE=live
```

## Troubleshooting

**Container won't start:**
```bash
# Check logs
./scripts/dev.sh logs

# Rebuild image
./scripts/dev.sh build
```

**Port 8000 in use:**
```bash
# Find what's using it
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Change port in docker-compose.yml
# Change "8000:8000" to "8001:8000"
```

**Module not found:**
```bash
# Restart container
./scripts/dev.sh restart

# Or rebuild if you changed dependencies
./scripts/dev.sh build
```

## See Also

- [DOCKER_SETUP.md](../DOCKER_SETUP.md) - Complete setup guide
- [API Documentation](http://localhost:8000/docs) - When server is running
- [Development Scripts](../scripts/) - Helper scripts
