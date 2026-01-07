#!/bin/bash
# Entrypoint script for Docker container

set -e

# Print environment info
echo "================================"
echo "Claude Studio Producer - Docker"
echo "================================"
echo "Environment: ${ENV:-development}"
echo "Debug: ${DEBUG:-false}"
echo "Provider Mode: ${PROVIDER_MODE:-mock}"
echo "Artifact Dir: ${ARTIFACT_DIR:-/artifacts}"
echo "================================"

# Ensure artifacts directory exists
mkdir -p "${ARTIFACT_DIR:-/artifacts}"

# Run any initialization tasks here
# (e.g., database migrations, cache warming, etc.)

# Execute the main command
exec "$@"
