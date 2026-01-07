#!/bin/bash
# Quick development commands for Claude Studio Producer

set -e

COMPOSE_FILE="docker/docker-compose.yml"

case "$1" in
  setup)
    echo "[INFO] Setting up Claude Studio Producer for the first time..."
    echo ""
    echo "Step 1: Building Docker image (this may take 2-5 minutes)..."
    docker-compose -f $COMPOSE_FILE build
    echo ""
    echo "Step 2: Creating .env file if it doesn't exist..."
    if [ ! -f .env ]; then
      echo "# Claude Studio Producer - Environment Variables" > .env
      echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> .env
      echo "PROVIDER_MODE=mock" >> .env
      echo "DEBUG=true" >> .env
      echo ""
      echo "[WARN] .env file created. Please edit it and add your ANTHROPIC_API_KEY"
      echo "       File location: .env"
    else
      echo ".env file already exists"
    fi
    echo ""
    echo "Step 3: Creating artifacts directory..."
    mkdir -p artifacts
    echo ""
    echo "Setup complete! Next steps:"
    echo "  1. Edit .env and add your ANTHROPIC_API_KEY"
    echo "  2. Run: ./scripts/dev.sh up"
    echo "  3. Test: curl http://localhost:8000/health"
    echo "  4. View docs: http://localhost:8000/docs"
    ;;

  up)
    echo "[INFO] Starting Claude Studio Producer in development mode..."

    # Check if image exists
    if ! docker images | grep -q "docker-studio"; then
      echo "[WARN] Docker image not found. Building it first..."
      docker-compose -f $COMPOSE_FILE build
    fi

    docker-compose -f $COMPOSE_FILE up -d

    # Wait a moment for server to start
    sleep 2

    echo ""
    echo "Started at http://localhost:8000"
    echo "  - API docs: http://localhost:8000/docs"
    echo "  - Health: http://localhost:8000/health"
    echo ""
    echo "Checking server health..."
    if command -v curl &> /dev/null; then
      if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "[OK] Server is healthy!"
      else
        echo "[WARN] Server health check failed. Check logs: ./scripts/dev.sh logs"
      fi
    fi
    echo ""
    echo "View logs: ./scripts/dev.sh logs"
    ;;

  down)
    echo "[INFO] Stopping Claude Studio Producer..."
    docker-compose -f $COMPOSE_FILE down
    echo "Stopped"
    ;;

  restart)
    echo "[INFO] Restarting Claude Studio Producer..."
    docker-compose -f $COMPOSE_FILE restart
    echo "Restarted"
    ;;

  logs)
    docker-compose -f $COMPOSE_FILE logs -f
    ;;

  shell)
    echo "[INFO] Opening shell in container..."
    docker-compose -f $COMPOSE_FILE exec studio bash
    ;;

  test)
    echo "[INFO] Running tests in container..."
    docker-compose -f $COMPOSE_FILE exec studio pytest tests/ -v
    ;;

  live)
    echo "[INFO] Starting in LIVE mode (using real API providers)..."
    echo "[WARN] Ensure API keys are set in .env file"
    PROVIDER_MODE=live docker-compose -f $COMPOSE_FILE up -d
    echo ""
    echo "Started in LIVE mode at http://localhost:8000"
    ;;

  build)
    echo "[INFO] Rebuilding Docker image..."
    docker-compose -f $COMPOSE_FILE build
    echo "Build complete"
    ;;

  clean)
    echo "[WARN] This will remove all containers and volumes"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      docker-compose -f $COMPOSE_FILE down -v
      echo "Cleaned"
    fi
    ;;

  ps)
    docker-compose -f $COMPOSE_FILE ps
    ;;

  *)
    echo "Claude Studio Producer - Development Commands"
    echo ""
    echo "Usage: $0 {command}"
    echo ""
    echo "Commands:"
    echo "  setup    First-time setup (build image, create .env)"
    echo "  up       Start containers in development mode"
    echo "  down     Stop containers"
    echo "  restart  Restart containers"
    echo "  logs     View container logs (follow mode)"
    echo "  shell    Open bash shell in container"
    echo "  test     Run tests in container"
    echo "  live     Start in LIVE mode (real APIs)"
    echo "  build    Rebuild Docker image"
    echo "  clean    Remove containers and volumes"
    echo "  ps       Show container status"
    echo ""
    echo "First Time Setup:"
    echo "  $0 setup       # Build image and create .env"
    echo "  $0 up          # Start dev server"
    echo ""
    echo "Examples:"
    echo "  $0 logs        # Watch logs"
    echo "  $0 test        # Run tests"
    echo "  $0 shell       # Debug in container"
    exit 1
    ;;
esac
