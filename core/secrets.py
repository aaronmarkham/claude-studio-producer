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
