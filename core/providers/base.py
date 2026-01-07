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
