"""
Luma AI Video Provider - Dream Machine API

Features:
- Text-to-video (no seed image required!)
- Image-to-video with keyframes
- Generation chaining for scene continuity
- Character reference for consistent characters
- Camera motion concepts
- Video extension/looping
- 5s and 9s durations
- Up to 1080p resolution

Models:
- ray-2: Production quality (default)
- ray-3: Advanced features (character ref, HDR)

Pricing (720p):
- 5s: ~$0.40
- 9s: ~$0.72

API Docs: https://docs.lumalabs.ai/
"""

import os
import asyncio
from typing import Dict, Any, Optional, List

from lumaai import LumaAI

from ..base import VideoProvider, VideoProviderConfig, GenerationResult, ProviderType


class LumaProvider(VideoProvider):
    """
    Luma AI Dream Machine - Advanced video generation

    Key advantage: Supports text-to-video without requiring a seed image,
    making it perfect for quick E2E testing and pure prompt-based generation.
    """

    _is_stub = False  # Fully implemented

    # Cost map by (resolution, duration)
    COST_MAP = {
        ("540p", "5s"): 0.20,
        ("540p", "9s"): 0.36,
        ("720p", "5s"): 0.40,
        ("720p", "9s"): 0.72,
        ("1080p", "5s"): 0.80,
        ("1080p", "9s"): 1.44,
    }

    # Supported aspect ratios
    ASPECT_RATIOS = ["1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"]

    def __init__(self, config: Optional[VideoProviderConfig] = None, model: str = "ray-2"):
        """
        Initialize Luma provider.

        Args:
            config: Optional VideoProviderConfig (will use env var if not provided)
            model: Model to use - "ray-2" (default) or "ray-3" (advanced features)
        """
        # Handle config - allow None for simple initialization
        if config is None:
            api_key = os.getenv("LUMA_API_KEY")
            if not api_key:
                raise ValueError("LUMA_API_KEY environment variable required")
            config = VideoProviderConfig(
                provider_type=ProviderType.LUMA,
                api_key=api_key,
                timeout=300
            )

        super().__init__(config)
        self.model = model
        self.client = LumaAI(auth_token=self.config.api_key)

    @property
    def name(self) -> str:
        return "luma"

    @property
    def cost_per_second(self) -> float:
        # Base cost for 720p: $0.40 / 5s = $0.08/s
        return 0.08

    async def generate_video(
        self,
        prompt: str,
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> GenerationResult:
        """
        Generate video from text prompt.

        Args:
            prompt: Text description of desired video
            duration: Target duration in seconds (5 or 9)
            aspect_ratio: Video aspect ratio ("16:9", "9:16", "1:1", etc.)
            **kwargs: Additional options:
                - start_image_url: URL of image to start from
                - end_image_url: URL of image to end at
                - continue_from: Generation ID to continue from
                - character_ref_url: URL of character reference image (ray-3 only)
                - camera_motion: Camera concept key (e.g., "orbit", "pan_left")
                - loop: Whether to create a looping video
                - resolution: "540p", "720p", "1080p"
                - model: Override default model

        Returns:
            GenerationResult with video URL and metadata
        """
        # Map duration to Luma format (5s or 9s)
        duration_str = "5s" if duration <= 7 else "9s"
        actual_duration = 5.0 if duration_str == "5s" else 9.0

        # Determine resolution from kwargs or default to 720p
        resolution = kwargs.get("resolution", "720p")

        # Validate and normalize aspect ratio
        if aspect_ratio not in self.ASPECT_RATIOS:
            # Try to find closest match
            aspect_ratio = self._normalize_aspect_ratio(aspect_ratio)

        # Build keyframes if provided
        keyframes = self._build_keyframes(kwargs)

        # Build concepts (camera motion)
        concepts = []
        if kwargs.get("camera_motion"):
            concepts.append({"key": kwargs["camera_motion"]})

        # Build request parameters
        request_params = {
            "prompt": prompt[:2000],  # Luma has a prompt limit
            "model": kwargs.get("model", self.model),
            "aspect_ratio": aspect_ratio,
            "loop": kwargs.get("loop", False),
        }

        # Add optional params
        if keyframes:
            request_params["keyframes"] = keyframes

        if concepts:
            request_params["concepts"] = concepts

        # Character reference (ray-3 only)
        if kwargs.get("character_ref_url"):
            request_params["character_ref"] = {
                "type": "image",
                "url": kwargs["character_ref_url"]
            }

        try:
            # Create generation (synchronous call, returns generation object)
            generation = self.client.generations.create(**request_params)

            # Wait for completion
            video_url = await self._wait_for_completion(
                generation.id,
                timeout=self.config.timeout
            )

            # Calculate cost
            cost = self.COST_MAP.get((resolution, duration_str), 0.40)

            return GenerationResult(
                success=True,
                video_url=video_url,
                duration=actual_duration,
                cost=cost,
                provider_metadata={
                    "provider": "luma",
                    "generation_id": generation.id,
                    "model": request_params["model"],
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                    "has_keyframes": bool(keyframes),
                    "camera_motion": kwargs.get("camera_motion"),
                    "prompt": prompt[:200],
                }
            )

        except TimeoutError as e:
            return GenerationResult(
                success=False,
                error_message=f"Luma generation timed out: {str(e)}"
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                error_message=f"Luma generation failed: {str(e)}"
            )

    def _build_keyframes(self, kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build keyframes dict from kwargs."""
        keyframes = kwargs.get("keyframes")
        if keyframes:
            return keyframes

        keyframes = {}

        # Start frame from image URL
        if kwargs.get("start_image_url"):
            keyframes["frame0"] = {
                "type": "image",
                "url": kwargs["start_image_url"]
            }
        # Or continue from previous generation
        elif kwargs.get("continue_from"):
            keyframes["frame0"] = {
                "type": "generation",
                "id": kwargs["continue_from"]
            }

        # End frame from image URL
        if kwargs.get("end_image_url"):
            keyframes["frame1"] = {
                "type": "image",
                "url": kwargs["end_image_url"]
            }

        return keyframes if keyframes else None

    def _normalize_aspect_ratio(self, aspect_ratio: str) -> str:
        """Normalize aspect ratio to Luma-supported format."""
        # Try direct match first
        if aspect_ratio in self.ASPECT_RATIOS:
            return aspect_ratio

        # Map common variations
        ratio_map = {
            "16:9": "16:9",
            "9:16": "9:16",
            "1:1": "1:1",
            "4:3": "4:3",
            "3:4": "3:4",
            "21:9": "21:9",
            "9:21": "9:21",
            # Handle dimension-style ratios
            "1920:1080": "16:9",
            "1080:1920": "9:16",
            "1280:720": "16:9",
            "720:1280": "9:16",
        }

        return ratio_map.get(aspect_ratio, "16:9")

    async def _wait_for_completion(
        self,
        generation_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> str:
        """
        Poll until generation completes.

        Args:
            generation_id: Luma generation ID
            timeout: Maximum wait time in seconds
            poll_interval: Seconds between status checks

        Returns:
            Video URL

        Raises:
            TimeoutError: If generation doesn't complete in time
            Exception: If generation fails
        """
        elapsed = 0

        while elapsed < timeout:
            # Get current status (synchronous call)
            generation = self.client.generations.get(generation_id)

            if generation.state == "completed":
                # Return video URL from assets
                if hasattr(generation, 'assets') and generation.assets:
                    return generation.assets.video
                raise Exception("Generation completed but no video URL found")

            elif generation.state == "failed":
                reason = getattr(generation, 'failure_reason', 'Unknown error')
                raise Exception(f"Luma generation failed: {reason}")

            # Still processing (queued, dreaming, etc.)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Luma generation timed out after {timeout}s")

    async def generate_continuous(
        self,
        scenes: List[Dict[str, Any]],
        character_ref_url: Optional[str] = None
    ) -> List[GenerationResult]:
        """
        Generate multiple scenes with continuity.

        Each scene automatically continues from the previous one,
        creating seamless transitions between scenes.

        Args:
            scenes: List of scene dicts with:
                - prompt: str (required)
                - duration: float (optional, default 5.0)
                - start_image_url: str (optional, for first scene)
                - camera_motion: str (optional)
            character_ref_url: Optional character reference for consistency

        Returns:
            List of GenerationResult, one per scene
        """
        results = []
        previous_id = None

        for i, scene in enumerate(scenes):
            kwargs = {
                "camera_motion": scene.get("camera_motion"),
            }

            # Add character reference if provided
            if character_ref_url:
                kwargs["character_ref_url"] = character_ref_url

            # First scene might have a start image
            if i == 0 and scene.get("start_image_url"):
                kwargs["start_image_url"] = scene["start_image_url"]
            # Subsequent scenes continue from previous
            elif previous_id:
                kwargs["continue_from"] = previous_id

            result = await self.generate_video(
                prompt=scene["prompt"],
                duration=scene.get("duration", 5.0),
                aspect_ratio=scene.get("aspect_ratio", "16:9"),
                **kwargs
            )

            results.append(result)

            # Track generation ID for chaining
            if result.success and result.provider_metadata:
                previous_id = result.provider_metadata.get("generation_id")

        return results

    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """
        Check generation status.

        Args:
            job_id: Luma generation ID

        Returns:
            Status dict with id, status, video_url, failure_reason
        """
        try:
            generation = self.client.generations.get(job_id)
            return {
                "id": generation.id,
                "status": generation.state,
                "video_url": generation.assets.video if generation.state == "completed" and hasattr(generation, 'assets') else None,
                "failure_reason": getattr(generation, 'failure_reason', None) if generation.state == "failed" else None
            }
        except Exception as e:
            return {
                "id": job_id,
                "status": "error",
                "error": str(e)
            }

    async def download_video(self, video_url: str, output_path: str) -> bool:
        """
        Download generated video to local path.

        Args:
            video_url: URL of the video to download
            output_path: Local path to save the video

        Returns:
            True if successful, False otherwise
        """
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(video_url, follow_redirects=True)
                response.raise_for_status()

                with open(output_path, "wb") as f:
                    f.write(response.content)

            return True
        except Exception:
            return False

    def estimate_cost(self, duration: float, **kwargs) -> float:
        """
        Estimate generation cost.

        Args:
            duration: Video duration in seconds
            **kwargs: Optional resolution param

        Returns:
            Estimated cost in USD
        """
        resolution = kwargs.get("resolution", "720p")
        duration_str = "5s" if duration <= 7 else "9s"
        return self.COST_MAP.get((resolution, duration_str), 0.40)

    async def validate_credentials(self) -> bool:
        """
        Validate API credentials by making a simple API call.

        Returns:
            True if credentials are valid
        """
        try:
            # Try to list camera motions as a simple validation call
            self.client.generations.camera_motion.list()
            return True
        except Exception:
            return False

    async def list_camera_motions(self) -> List[str]:
        """
        Get available camera motion concepts.

        Returns:
            List of camera motion keys (e.g., ["orbit", "pan_left", ...])
        """
        try:
            concepts = self.client.generations.camera_motion.list()
            return [c.key for c in concepts] if concepts else []
        except Exception:
            return []
