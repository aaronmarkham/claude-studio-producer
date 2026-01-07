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
]
