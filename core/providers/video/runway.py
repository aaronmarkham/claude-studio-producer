"""Runway ML video generation provider"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional
from ..base import VideoProvider, VideoProviderConfig, GenerationResult, ProviderType
from core.budget import ProductionTier


class RunwayProvider(VideoProvider):
    """
    Runway ML Gen-3 Alpha video generation provider.

    API Documentation: https://docs.runwayml.com/
    Pricing: ~$0.05/second for Gen-3 Alpha (as of 2025)
    """

    _is_stub = False  # Fully implemented provider

    # Runway API endpoints
    API_BASE = "https://api.runwayml.com/v1"
    GENERATE_ENDPOINT = f"{API_BASE}/generate"
    STATUS_ENDPOINT = f"{API_BASE}/tasks"

    def __init__(self, config: VideoProviderConfig):
        super().__init__(config)

        if not self.config.api_key:
            raise ValueError("Runway API key required")

        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self.session

    async def generate_video(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """
        Generate video using Runway Gen-3 Alpha.

        Args:
            prompt: Text description of video content
            duration: Target duration (max 10s for Gen-3 Alpha)
            aspect_ratio: Video aspect ratio
            **kwargs: Additional parameters:
                - image_prompt: Optional image to use as first frame
                - motion_intensity: 0-100 (default 50)
                - seed: Random seed for reproducibility
        """
        session = await self._get_session()

        # Clamp duration to Runway's limits
        duration = min(duration, 10.0)

        # Build request payload
        payload = {
            "prompt": prompt,
            "duration": duration,
            "aspectRatio": aspect_ratio,
            "model": "gen3a_turbo"  # Gen-3 Alpha Turbo
        }

        # Add optional parameters
        if "image_prompt" in kwargs:
            payload["imagePrompt"] = kwargs["image_prompt"]
        if "motion_intensity" in kwargs:
            payload["motionIntensity"] = kwargs["motion_intensity"]
        if "seed" in kwargs:
            payload["seed"] = kwargs["seed"]

        try:
            async with session.post(
                self.GENERATE_ENDPOINT,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return GenerationResult(
                        success=False,
                        error_message=f"Runway API error ({response.status}): {error_text}"
                    )

                data = await response.json()
                task_id = data.get("id")

                # Poll for completion
                result = await self._poll_until_complete(task_id)
                return result

        except asyncio.TimeoutError:
            return GenerationResult(
                success=False,
                error_message=f"Runway generation timed out after {self.config.timeout}s"
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"Runway generation failed: {str(e)}"
            )

    async def _poll_until_complete(
        self,
        task_id: str,
        poll_interval: int = 5
    ) -> GenerationResult:
        """Poll task status until completion"""
        max_attempts = self.config.timeout // poll_interval

        for attempt in range(max_attempts):
            status_data = await self.check_status(task_id)

            if status_data.get("status") == "SUCCEEDED":
                video_url = status_data.get("output", {}).get("url")
                duration = status_data.get("output", {}).get("duration")
                cost = self.estimate_cost(duration or 5.0)

                return GenerationResult(
                    success=True,
                    video_url=video_url,
                    duration=duration,
                    cost=cost,
                    provider_metadata={
                        "task_id": task_id,
                        "provider": "runway",
                        "model": "gen3a_turbo",
                        **status_data
                    }
                )

            elif status_data.get("status") == "FAILED":
                return GenerationResult(
                    success=False,
                    error_message=f"Runway generation failed: {status_data.get('error')}"
                )

            # Still processing, wait and retry
            await asyncio.sleep(poll_interval)

        return GenerationResult(
            success=False,
            error_message="Runway generation timed out during polling"
        )

    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of Runway generation task"""
        session = await self._get_session()

        try:
            async with session.get(f"{self.STATUS_ENDPOINT}/{job_id}") as response:
                if response.status != 200:
                    return {
                        "status": "ERROR",
                        "error": f"Status check failed: {response.status}"
                    }

                return await response.json()

        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e)
            }

    async def download_video(self, video_url: str, output_path: str) -> bool:
        """Download generated video from Runway CDN"""
        session = await self._get_session()

        try:
            async with session.get(video_url) as response:
                if response.status != 200:
                    return False

                with open(output_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

                return True

        except Exception:
            return False

    def estimate_cost(self, duration: float, **kwargs) -> float:
        """
        Estimate Runway generation cost.

        Runway Gen-3 Alpha Turbo pricing (2025):
        - $0.05 per second
        """
        return duration * 0.05

    async def validate_credentials(self) -> bool:
        """Validate Runway API key"""
        session = await self._get_session()

        try:
            # Try to hit a simple endpoint to verify auth
            async with session.get(f"{self.API_BASE}/user") as response:
                return response.status == 200

        except Exception:
            return False

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
