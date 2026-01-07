"""Mock video provider for testing without API keys"""

import asyncio
from typing import Dict, Any
from .base import VideoProvider, VideoProviderConfig, GenerationResult, ProviderType
from core.budget import ProductionTier, COST_MODELS


class MockVideoProvider(VideoProvider):
    """
    Mock video provider that simulates video generation without hitting real APIs.

    Used for:
    - Testing without API keys
    - Development without incurring costs
    - CI/CD pipeline testing
    """

    _is_stub = False

    def __init__(self, config: VideoProviderConfig = None):
        if config is None:
            config = VideoProviderConfig(provider_type=ProviderType.MOCK)
        super().__init__(config)
        self.generation_count = 0
        self.jobs: Dict[str, Dict[str, Any]] = {}

    async def generate_video(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """
        Simulate video generation with realistic delay.

        Returns a mock result that mimics real provider behavior.
        """
        # Simulate API delay (0.5-2 seconds instead of real 30-120 seconds)
        await asyncio.sleep(0.5)

        self.generation_count += 1
        job_id = f"mock_job_{self.generation_count}"

        # Extract production tier for cost estimation
        tier = kwargs.get("tier", ProductionTier.ANIMATED)
        cost = self.estimate_cost(duration, tier=tier)

        # Simulate successful generation
        mock_url = f"https://mock-cdn.example.com/videos/{job_id}.mp4"

        result = GenerationResult(
            success=True,
            video_url=mock_url,
            video_path=f"/mock/videos/{job_id}.mp4",
            duration=duration,
            cost=cost,
            provider_metadata={
                "job_id": job_id,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "tier": tier.value,
                "generation_time": 0.5,
                "provider": "mock"
            }
        )

        # Store job for status checking
        self.jobs[job_id] = {
            "status": "completed",
            "result": result
        }

        return result

    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of mock job"""
        if job_id not in self.jobs:
            return {
                "status": "not_found",
                "error": f"Job {job_id} not found"
            }

        return self.jobs[job_id]

    async def download_video(self, video_url: str, output_path: str) -> bool:
        """Simulate video download"""
        # In mock mode, just simulate success
        await asyncio.sleep(0.1)
        return True

    def estimate_cost(self, duration: float, **kwargs) -> float:
        """
        Estimate cost based on production tier.

        Uses the same cost models as the budget system.
        """
        tier = kwargs.get("tier", ProductionTier.ANIMATED)
        cost_model = COST_MODELS.get(tier)

        if cost_model:
            return duration * cost_model.cost_per_second

        # Fallback to animated tier pricing
        return duration * COST_MODELS[ProductionTier.ANIMATED].cost_per_second

    async def validate_credentials(self) -> bool:
        """Mock provider always has valid credentials"""
        return True

    def reset(self):
        """Reset mock state (useful for testing)"""
        self.generation_count = 0
        self.jobs.clear()
