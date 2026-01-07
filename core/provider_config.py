"""Provider configuration and factory"""

import os
from typing import Optional
from .providers import (
    VideoProvider,
    VideoProviderConfig,
    ProviderType,
    MockVideoProvider,
    RunwayProvider
)


class ProviderFactory:
    """Factory for creating video providers from configuration"""

    @staticmethod
    def create_from_env(provider_type: Optional[str] = None) -> VideoProvider:
        """
        Create video provider from environment variables.

        Environment variables:
        - VIDEO_PROVIDER: "mock", "runway", "pika", "stability" (defaults to "mock")
        - RUNWAY_API_KEY: API key for Runway
        - PIKA_API_KEY: API key for Pika
        - STABILITY_API_KEY: API key for Stability AI

        Args:
            provider_type: Override provider type (defaults to VIDEO_PROVIDER env var)

        Returns:
            Configured VideoProvider instance
        """
        # Determine provider type
        provider_str = provider_type or os.getenv("VIDEO_PROVIDER", "mock")

        try:
            provider_enum = ProviderType(provider_str.lower())
        except ValueError:
            print(f"⚠️  Invalid provider type '{provider_str}', falling back to mock")
            provider_enum = ProviderType.MOCK

        # Create provider based on type
        if provider_enum == ProviderType.MOCK:
            return MockVideoProvider()

        elif provider_enum == ProviderType.RUNWAY:
            api_key = os.getenv("RUNWAY_API_KEY")
            if not api_key:
                print("⚠️  RUNWAY_API_KEY not set, falling back to mock provider")
                return MockVideoProvider()

            config = VideoProviderConfig(
                provider_type=ProviderType.RUNWAY,
                api_key=api_key
            )
            return RunwayProvider(config)

        elif provider_enum == ProviderType.PIKA:
            # TODO: Implement PikaProvider when ready
            print("⚠️  Pika provider not yet implemented, falling back to mock")
            return MockVideoProvider()

        elif provider_enum == ProviderType.STABILITY:
            # TODO: Implement StabilityProvider when ready
            print("⚠️  Stability provider not yet implemented, falling back to mock")
            return MockVideoProvider()

        else:
            return MockVideoProvider()

    @staticmethod
    def create_mock() -> VideoProvider:
        """Create mock provider (for testing)"""
        return MockVideoProvider()

    @staticmethod
    def create_runway(api_key: str) -> VideoProvider:
        """Create Runway provider with API key"""
        config = VideoProviderConfig(
            provider_type=ProviderType.RUNWAY,
            api_key=api_key
        )
        return RunwayProvider(config)


def get_default_provider() -> VideoProvider:
    """Get default video provider based on environment"""
    return ProviderFactory.create_from_env()
