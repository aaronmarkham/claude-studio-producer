"""
Secure API key management using OS keychain.

Thin wrapper around spiritwriter.secrets, configured for claude-studio-producer.

Usage:
    from core.secrets import get_api_key, set_api_key

    # Get key (checks keychain first, falls back to env var)
    key = get_api_key("OPENAI_API_KEY")

    # Store key in keychain
    set_api_key("OPENAI_API_KEY", "sk-...")
"""

import os
import re

from spiritwriter.secrets.keychain import (  # noqa: F401
    get_api_key,
    set_api_key,
    delete_api_key,
    list_api_keys,
    import_from_env_file,
    is_keyring_available,
    configure,
    register_keys,
    KNOWN_KEYS,
    SERVICE_NAME,
)

# Configure for claude-studio-producer
# Keeps existing keychain entries working under "claude-studio" service name
configure(
    service_name="claude-studio",
    extra_keys={
        "LUMA_API_KEY": "Luma AI API key (video)",
        "RUNWAY_API_KEY": "Runway ML API key (video)",
        "ELEVENLABS_API_KEY": "ElevenLabs API key (TTS)",
        "GOOGLE_CLOUD_API_KEY": "Google Cloud API key (TTS)",
        "PIKA_API_KEY": "Pika Labs API key (video)",
        "STABILITY_API_KEY": "Stability AI API key (image/video)",
        "KLING_API_KEY": "Kling AI API key (video)",
        "MUBERT_API_KEY": "Mubert API key (music)",
        "SUNO_API_KEY": "Suno API key (music)",
        "YOUTUBE_CLIENT_ID": "YouTube OAuth2 client ID (Desktop app)",
        "YOUTUBE_CLIENT_SECRET": "YouTube OAuth2 client secret",
        "YOUTUBE_CLIENT_SECRETS_PATH": "Path to YouTube OAuth2 client secrets JSON (legacy)",
        "YOUTUBE_API_KEY": "YouTube Data API key",
    },
)


# =============================================================================
# REDACTION
# =============================================================================
#
# Onboarding/test harnesses capture provider output verbatim into checkpoint
# files that get committed. A provider's get_headers() legitimately returns the
# live API key, so any such capture must be scrubbed before it hits disk.

REDACTED = "***REDACTED***"

# Shape-based backstop: catches keys regardless of where they came from
# (env var, keychain, or hardcoded in a fixture).
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),          # Anthropic
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),         # OpenAI (project)
    re.compile(r"sk_[A-Za-z0-9]{24,}"),                 # ElevenLabs
    re.compile(r"sk-[A-Za-z0-9]{24,}"),                 # OpenAI (legacy)
    re.compile(r"luma-[0-9a-fA-F\-]{20,}"),             # Luma
    re.compile(r"key-[A-Za-z0-9]{24,}"),                # Runway
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),             # Google
    re.compile(r"(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}"),  # GitHub
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),       # Slack
)

# Minimum length for a literal value to be worth redacting. Guards against a
# short/empty env var (e.g. "test") blanking out unrelated text.
_MIN_LITERAL_LEN = 8


def redact_secrets(text, extra_values=None):
    """Replace API keys in ``text`` with a redaction marker.

    Scrubs three sources, in order of precision:
      1. ``extra_values`` -- literals the caller knows are secret (e.g. the
         ``api_key`` off a provider instance, which may come from the keychain).
      2. Live values of known secret env vars.
      3. Well-known key shapes (see ``_SECRET_PATTERNS``).

    Args:
        text: Value to scrub. Non-strings are returned unchanged.
        extra_values: Optional iterable of literal secret values to redact.

    Returns:
        The scrubbed string, or ``text`` unchanged if it is not a string.
    """
    if not isinstance(text, str) or not text:
        return text

    literals = set()
    for value in extra_values or ():
        if isinstance(value, str) and len(value) >= _MIN_LITERAL_LEN:
            literals.add(value)
    for name in KNOWN_KEYS:
        value = os.environ.get(name)
        if value and len(value) >= _MIN_LITERAL_LEN:
            literals.add(value)

    # Longest first, so an embedded shorter secret can't partially mask a longer one.
    for value in sorted(literals, key=len, reverse=True):
        text = text.replace(value, REDACTED)

    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)

    return text
