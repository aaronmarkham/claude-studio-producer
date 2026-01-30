"""Abstract base classes for provider interfaces"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class ProviderType(Enum):
    """Available video provider types"""
    MOCK = "mock"
    RUNWAY = "runway"
    PIKA = "pika"
    STABILITY = "stability"
    LUMA = "luma"
    KLING = "kling"


def _mask_secret(value: Optional[str]) -> str:
    """Mask a secret value for safe display in logs/repr."""
    if value is None:
        return "None"
    if len(value) <= 8:
        return "'***'"
    return f"'{value[:4]}...{value[-4:]}'"


@dataclass
class VideoProviderConfig:
    """Configuration for video provider"""
    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 300  # seconds
    max_retries: int = 3
    retry_delay: int = 5  # seconds
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}

    def __repr__(self) -> str:
        """Safe repr that masks API key to prevent accidental exposure in logs."""
        return (
            f"VideoProviderConfig(provider_type={self.provider_type}, "
            f"api_key={_mask_secret(self.api_key)}, "
            f"base_url={self.base_url!r}, timeout={self.timeout}, "
            f"max_retries={self.max_retries}, retry_delay={self.retry_delay})"
        )


@dataclass
class GenerationResult:
    """Result from video generation"""
    success: bool
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    duration: Optional[float] = None
    cost: Optional[float] = None
    error_message: Optional[str] = None
    provider_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.provider_metadata is None:
            self.provider_metadata = {}


class VideoProvider(ABC):
    """
    Abstract base class for video generation providers.

    All video providers (Runway, Pika, Stability AI, Mock) must implement this interface.
    This enables dependency injection and makes the system testable without API keys.
    """

    def __init__(self, config: VideoProviderConfig):
        self.config = config

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """
        Generate a video from a text prompt.

        Args:
            prompt: Text description of video content
            duration: Target duration in seconds
            aspect_ratio: Video aspect ratio (e.g., "16:9", "9:16", "1:1")
            **kwargs: Provider-specific parameters

        Returns:
            GenerationResult with video URL/path and metadata
        """
        pass

    @abstractmethod
    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """
        Check status of async video generation job.

        Args:
            job_id: Provider's job identifier

        Returns:
            Status information including completion state
        """
        pass

    @abstractmethod
    async def download_video(self, video_url: str, output_path: str) -> bool:
        """
        Download generated video to local filesystem.

        Args:
            video_url: URL of generated video
            output_path: Local path to save video

        Returns:
            True if download successful
        """
        pass

    @abstractmethod
    def estimate_cost(self, duration: float, **kwargs) -> float:
        """
        Estimate cost for generating video of given duration.

        Args:
            duration: Target duration in seconds
            **kwargs: Provider-specific parameters

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.

        Returns:
            True if credentials are valid
        """
        pass


@dataclass
class AudioProviderConfig:
    """Configuration for audio provider"""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 60  # seconds
    max_retries: int = 3
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}

    def __repr__(self) -> str:
        """Safe repr that masks API key to prevent accidental exposure in logs."""
        return (
            f"AudioProviderConfig(api_key={_mask_secret(self.api_key)}, "
            f"base_url={self.base_url!r}, timeout={self.timeout}, "
            f"max_retries={self.max_retries})"
        )


@dataclass
class AudioGenerationResult:
    """Result from audio generation"""
    success: bool
    audio_url: Optional[str] = None
    audio_path: Optional[str] = None
    audio_data: Optional[bytes] = None  # Raw audio bytes when not saving to file
    duration: Optional[float] = None
    format: str = "mp3"
    sample_rate: int = 44100
    channels: int = 1
    cost: Optional[float] = None
    error_message: Optional[str] = None
    provider_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.provider_metadata is None:
            self.provider_metadata = {}


class AudioProvider(ABC):
    """
    Abstract base class for audio/TTS providers.

    All audio providers (ElevenLabs, OpenAI TTS, Google TTS) must implement this interface.
    """

    def __init__(self, config: AudioProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier"""
        pass

    @abstractmethod
    async def generate_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Generate speech from text.

        Args:
            text: Text to convert to speech
            voice_id: Voice identifier (provider-specific)
            speed: Speech speed multiplier (1.0 = normal)
            **kwargs: Provider-specific parameters

        Returns:
            AudioGenerationResult with audio URL/path and metadata
        """
        pass

    @abstractmethod
    async def list_voices(self) -> list:
        """
        List available voices.

        Returns:
            List of voice information dicts
        """
        pass

    @abstractmethod
    def estimate_cost(self, text: str, **kwargs) -> float:
        """
        Estimate cost for generating speech from text.

        Args:
            text: Text to be spoken
            **kwargs: Provider-specific parameters

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.

        Returns:
            True if credentials are valid
        """
        pass


@dataclass
class MusicProviderConfig:
    """Configuration for music provider"""
    api_key: Optional[str] = None
    timeout: int = 180  # seconds (music generation can be slow)
    max_retries: int = 3
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}

    def __repr__(self) -> str:
        """Safe repr that masks API key to prevent accidental exposure in logs."""
        return (
            f"MusicProviderConfig(api_key={_mask_secret(self.api_key)}, "
            f"timeout={self.timeout}, max_retries={self.max_retries})"
        )


@dataclass
class MusicGenerationResult:
    """Result from music generation"""
    success: bool
    audio_url: Optional[str] = None
    audio_path: Optional[str] = None
    duration: Optional[float] = None
    format: str = "mp3"
    sample_rate: int = 44100
    channels: int = 2  # Stereo for music
    cost: Optional[float] = None
    error_message: Optional[str] = None
    provider_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.provider_metadata is None:
            self.provider_metadata = {}


class MusicProvider(ABC):
    """
    Abstract base class for music generation providers.

    All music providers (Mubert, Suno) must implement this interface.
    """

    def __init__(self, config: MusicProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier"""
        pass

    @abstractmethod
    async def generate_music(
        self,
        mood: str,
        duration: float,
        tempo: str = "medium",
        **kwargs
    ) -> MusicGenerationResult:
        """
        Generate background music.

        Args:
            mood: Musical mood (e.g., "upbeat", "calm", "energetic")
            duration: Target duration in seconds
            tempo: Tempo setting ("slow", "medium", "fast")
            **kwargs: Provider-specific parameters (genre, intensity, etc.)

        Returns:
            MusicGenerationResult with audio URL/path and metadata
        """
        pass

    @abstractmethod
    async def list_moods(self) -> list:
        """
        List available moods/styles.

        Returns:
            List of available mood/style options
        """
        pass

    @abstractmethod
    def estimate_cost(self, duration: float, **kwargs) -> float:
        """
        Estimate cost for generating music.

        Args:
            duration: Music duration in seconds
            **kwargs: Provider-specific parameters

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.

        Returns:
            True if credentials are valid
        """
        pass


@dataclass
class ImageProviderConfig:
    """Configuration for image provider"""
    api_key: Optional[str] = None
    timeout: int = 60  # seconds
    max_retries: int = 3
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}

    def __repr__(self) -> str:
        """Safe repr that masks API key to prevent accidental exposure in logs."""
        return (
            f"ImageProviderConfig(api_key={_mask_secret(self.api_key)}, "
            f"timeout={self.timeout}, max_retries={self.max_retries})"
        )


@dataclass
class ImageGenerationResult:
    """Result from image generation"""
    success: bool
    image_url: Optional[str] = None
    image_path: Optional[str] = None
    width: int = 1024
    height: int = 1024
    format: str = "png"
    cost: Optional[float] = None
    error_message: Optional[str] = None
    provider_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.provider_metadata is None:
            self.provider_metadata = {}


class ImageProvider(ABC):
    """
    Abstract base class for image generation providers.

    All image providers (DALL-E, Midjourney, Stability) must implement this interface.
    """

    def __init__(self, config: ImageProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier"""
        pass

    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        **kwargs
    ) -> ImageGenerationResult:
        """
        Generate image from text prompt.

        Args:
            prompt: Text description of image
            size: Image size (e.g., "1024x1024", "1792x1024")
            **kwargs: Provider-specific parameters

        Returns:
            ImageGenerationResult with image URL/path and metadata
        """
        pass

    @abstractmethod
    def estimate_cost(self, size: str = "1024x1024", **kwargs) -> float:
        """
        Estimate cost for generating an image.

        Args:
            size: Image size
            **kwargs: Provider-specific parameters

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.

        Returns:
            True if credentials are valid
        """
        pass


@dataclass
class StorageProviderConfig:
    """Configuration for storage provider"""
    bucket: Optional[str] = None
    base_path: str = "./artifacts"
    region: Optional[str] = None
    extra_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra_params is None:
            self.extra_params = {}


@dataclass
class StorageResult:
    """Result from storage operation"""
    success: bool
    file_url: Optional[str] = None
    file_path: Optional[str] = None
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    error_message: Optional[str] = None
    provider_metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.provider_metadata is None:
            self.provider_metadata = {}


class StorageProvider(ABC):
    """
    Abstract base class for storage providers.

    All storage providers (Local, S3) must implement this interface.
    """

    def __init__(self, config: StorageProviderConfig):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier"""
        pass

    @abstractmethod
    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        **kwargs
    ) -> StorageResult:
        """
        Upload file to storage.

        Args:
            local_path: Path to local file
            remote_path: Destination path in storage
            **kwargs: Provider-specific parameters

        Returns:
            StorageResult with file URL and metadata
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        remote_path: str,
        local_path: str,
        **kwargs
    ) -> StorageResult:
        """
        Download file from storage.

        Args:
            remote_path: Path in storage
            local_path: Destination local path
            **kwargs: Provider-specific parameters

        Returns:
            StorageResult with download status
        """
        pass

    @abstractmethod
    async def get_url(
        self,
        remote_path: str,
        expires_in: int = 3600,
        **kwargs
    ) -> str:
        """
        Get public URL for stored file.

        Args:
            remote_path: Path in storage
            expires_in: URL expiration time in seconds
            **kwargs: Provider-specific parameters

        Returns:
            Public URL string
        """
        pass

    @abstractmethod
    async def delete_file(self, remote_path: str, **kwargs) -> bool:
        """
        Delete file from storage.

        Args:
            remote_path: Path in storage
            **kwargs: Provider-specific parameters

        Returns:
            True if deletion successful
        """
        pass
