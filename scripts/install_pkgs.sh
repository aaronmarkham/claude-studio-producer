#!/bin/bash
# Auto-install project in cloud sessions (CCW / & background tasks)
# This runs via SessionStart hook when CLAUDE_CODE_REMOTE=true

set -e

# Skip if not in a cloud session
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  echo "[install_pkgs] Local session detected, skipping remote install."
  exit 0
fi

echo "[install_pkgs] Cloud session detected. Installing project..."

# Install in development mode
if [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
  pip install -e ".[dev]" 2>&1 | tail -5
  echo "[install_pkgs] Project installed in dev mode."
elif [ -f "requirements.txt" ]; then
  pip install -r requirements.txt 2>&1 | tail -5
  echo "[install_pkgs] Requirements installed."
else
  echo "[install_pkgs] No install target found (no pyproject.toml, setup.py, or requirements.txt)"
fi

# Verify key imports work
python -c "import click; print('[install_pkgs] click OK')" 2>/dev/null || true
python -c "import pytest; print('[install_pkgs] pytest OK')" 2>/dev/null || true

echo "[install_pkgs] Setup complete."
