"""Provider interfaces for external services (video generation, etc.)"""

from .base import (
    VideoProvider,
    VideoProviderConfig,
    GenerationResult,
    ProviderType,
    AudioProvider,
    AudioProviderConfig,
    AudioGenerationResult,
    MusicProvider,
    MusicProviderConfig,
    MusicGenerationResult,
    ImageProvider,
    ImageProviderConfig,
    ImageGenerationResult,
    StorageProvider,
    StorageProviderConfig,
    StorageResult,
)
from .mock import MockVideoProvider

# Video providers
from .video import (
    RunwayProvider,
    PikaProvider,
    StabilityProvider,
    LumaProvider,
    KlingProvider,
)

# Audio providers
from .audio import (
    ElevenLabsProvider,
    OpenAITTSProvider,
    GoogleTTSProvider,
)

# Music providers
from .music import (
    MubertProvider,
    SunoProvider,
)

# Image providers
from .image import (
    DalleProvider,
)

# Storage providers
from .storage import (
    LocalStorageProvider,
    S3StorageProvider,
)

__all__ = [
    # Base interfaces - Video
    "VideoProvider",
    "VideoProviderConfig",
    "GenerationResult",
    "ProviderType",
    # Base interfaces - Audio
    "AudioProvider",
    "AudioProviderConfig",
    "AudioGenerationResult",
    # Base interfaces - Music
    "MusicProvider",
    "MusicProviderConfig",
    "MusicGenerationResult",
    # Base interfaces - Image
    "ImageProvider",
    "ImageProviderConfig",
    "ImageGenerationResult",
    # Base interfaces - Storage
    "StorageProvider",
    "StorageProviderConfig",
    "StorageResult",
    # Mock provider
    "MockVideoProvider",
    # Video providers
    "RunwayProvider",
    "PikaProvider",
    "StabilityProvider",
    "LumaProvider",
    "KlingProvider",
    # Audio providers
    "ElevenLabsProvider",
    "OpenAITTSProvider",
    "GoogleTTSProvider",
    # Music providers
    "MubertProvider",
    "SunoProvider",
    # Image providers
    "DalleProvider",
    # Storage providers
    "LocalStorageProvider",
    "S3StorageProvider",
    # Registry
    "PROVIDER_REGISTRY",
    "get_all_providers",
]


# Provider Registry for CLI introspection and dynamic loading
PROVIDER_REGISTRY = {
    # Video providers
    "runway": {
        "name": "runway",
        "category": "video",
        "class": "RunwayProvider",
        "module": "core.providers.video.runway",
        "status": "implemented",
        "api_key_env": "RUNWAY_API_KEY",
        "cost_info": "$0.05/sec",
        "features": ["text-to-video", "image-to-video", "turbo mode", "10s max"],
        "limitations": ["10 second max duration"],
    },
    "pika": {
        "name": "pika",
        "category": "video",
        "class": "PikaProvider",
        "module": "core.providers.video.pika",
        "status": "stub",
        "api_key_env": "PIKA_API_KEY",
        "cost_info": "$0.20/sec",
        "features": ["text-to-video", "image-to-video", "camera controls", "8s max"],
        "limitations": ["8 second max duration"],
    },
    "stability": {
        "name": "stability",
        "category": "video",
        "class": "StabilityProvider",
        "module": "core.providers.video.stability",
        "status": "stub",
        "api_key_env": "STABILITY_API_KEY",
        "cost_info": "$0.10/sec",
        "features": ["text-to-video", "image-to-video", "budget-friendly"],
        "limitations": ["10 second max duration"],
    },
    "luma": {
        "name": "luma",
        "category": "video",
        "class": "LumaProvider",
        "module": "core.providers.video.luma",
        "status": "stub",
        "api_key_env": "LUMA_API_KEY",
        "cost_info": "$0.30/sec",
        "features": ["text-to-video", "image-to-video", "Dream Machine", "5s max"],
        "limitations": ["5 second max duration"],
    },
    "kling": {
        "name": "kling",
        "category": "video",
        "class": "KlingProvider",
        "module": "core.providers.video.kling",
        "status": "stub",
        "api_key_env": "KLING_API_KEY",
        "cost_info": "$0.15-0.30/sec",
        "features": ["text-to-video", "image-to-video", "pro mode", "10s max"],
        "limitations": ["10 second max duration"],
    },
    # Audio providers
    "elevenlabs": {
        "name": "elevenlabs",
        "category": "audio",
        "class": "ElevenLabsProvider",
        "module": "core.providers.audio.elevenlabs",
        "status": "stub",
        "api_key_env": "ELEVENLABS_API_KEY",
        "cost_info": "$0.30/1K chars",
        "features": ["premium TTS", "voice cloning", "29 languages", "emotion control"],
        "limitations": [],
    },
    "openai_tts": {
        "name": "openai_tts",
        "category": "audio",
        "class": "OpenAITTSProvider",
        "module": "core.providers.audio.openai_tts",
        "status": "stub",
        "api_key_env": "OPENAI_API_KEY",
        "cost_info": "$0.015-0.030/1K chars",
        "features": ["6 voices", "fast generation", "HD option"],
        "limitations": ["No voice cloning"],
    },
    "google_tts": {
        "name": "google_tts",
        "category": "audio",
        "class": "GoogleTTSProvider",
        "module": "core.providers.audio.google_tts",
        "status": "stub",
        "api_key_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "cost_info": "$0.004-0.016/1K chars",
        "features": ["200+ voices", "40+ languages", "WaveNet", "most affordable"],
        "limitations": [],
    },
    # Music providers
    "mubert": {
        "name": "mubert",
        "category": "music",
        "class": "MubertProvider",
        "module": "core.providers.music.mubert",
        "status": "stub",
        "api_key_env": "MUBERT_API_KEY",
        "cost_info": "$0.50/track",
        "features": ["royalty-free", "infinite unique tracks", "genre control"],
        "limitations": [],
    },
    "suno": {
        "name": "suno",
        "category": "music",
        "class": "SunoProvider",
        "module": "core.providers.music.suno",
        "status": "stub",
        "api_key_env": "SUNO_API_KEY",
        "cost_info": "$0.05/sec",
        "features": ["vocals", "custom lyrics", "multiple genres"],
        "limitations": [],
    },
    # Image providers
    "dalle": {
        "name": "dalle",
        "category": "image",
        "class": "DalleProvider",
        "module": "core.providers.image.dalle",
        "status": "stub",
        "api_key_env": "OPENAI_API_KEY",
        "cost_info": "$0.04-0.08/image",
        "features": ["DALL-E 3", "high quality", "prompt enhancement", "HD option"],
        "limitations": ["Max 1 image per request"],
    },
    # Storage providers
    "local": {
        "name": "local",
        "category": "storage",
        "class": "LocalStorageProvider",
        "module": "core.providers.storage.local",
        "status": "stub",
        "api_key_env": None,
        "cost_info": "Free",
        "features": ["local filesystem", "file:// URLs", "fast access"],
        "limitations": ["Not suitable for production"],
    },
    "s3": {
        "name": "s3",
        "category": "storage",
        "class": "S3StorageProvider",
        "module": "core.providers.storage.s3",
        "status": "stub",
        "api_key_env": "AWS_ACCESS_KEY_ID",
        "cost_info": "$0.023/GB/month",
        "features": ["AWS S3", "presigned URLs", "high durability", "CDN integration"],
        "limitations": ["Requires AWS credentials"],
    },
}


def get_all_providers():
    """
    Get all providers with auto-detected implementation status.

    Dynamically detects provider status by checking the _is_stub class attribute.
    Returns the PROVIDER_REGISTRY with updated status information.

    Returns:
        dict: Provider registry with auto-detected status
    """
    import importlib

    # Create a copy of the registry to avoid modifying the original
    providers = {}

    for provider_name, provider_info in PROVIDER_REGISTRY.items():
        # Copy the provider info
        info = provider_info.copy()

        try:
            # Dynamically import the module
            module = importlib.import_module(info["module"])

            # Get the provider class
            provider_class = getattr(module, info["class"])

            # Check _is_stub attribute
            is_stub = getattr(provider_class, "_is_stub", True)

            # Update status based on _is_stub
            info["status"] = "stub" if is_stub else "implemented"

        except (ImportError, AttributeError) as e:
            # If we can't import or find the class, mark as stub
            info["status"] = "stub"
            info["error"] = str(e)

        providers[provider_name] = info

    return providers
