"""
CLI commands for secure API key management.

Re-exported from spiritwriter-core. CSP mounts this into its own CLI group.

Usage:
    cs secrets list          # Show configured keys
    cs secrets set KEY       # Store a key securely
    cs secrets delete KEY    # Remove a key
    cs secrets import .env   # Import from .env file
"""

from spiritwriter.secrets.cli import secrets_cli  # noqa: F401

__all__ = ["secrets_cli"]
