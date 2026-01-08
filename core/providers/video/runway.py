"""Runway ML video generation provider"""

import asyncio
import aiohttp
import base64
import mimetypes
import os
from pathlib import Path
from typing import Dict, Any, Optional
from ..base import VideoProvider, VideoProviderConfig, GenerationResult, ProviderType
from core.budget import ProductionTier


class RunwayProvider(VideoProvider):
    """
    Runway ML Gen-3/Gen-4 video generation provider.

    API Documentation: https://docs.dev.runwayml.com/
    Pricing: ~$0.05/second for Gen-3 Alpha Turbo (as of 2025)
    """

    _is_stub = False  # Fully implemented provider

    # Runway API endpoints (public API at api.dev.runwayml.com)
    API_BASE = "https://api.dev.runwayml.com/v1"
    IMAGE_TO_VIDEO_ENDPOINT = f"{API_BASE}/image_to_video"
    TEXT_TO_VIDEO_ENDPOINT = f"{API_BASE}/text_to_video"  # If available
    STATUS_ENDPOINT = f"{API_BASE}/tasks"
    UPLOADS_ENDPOINT = f"{API_BASE}/uploads"

    # API version header
    API_VERSION = "2024-11-06"

    # Max size for inline base64 data URIs (5MB in characters)
    MAX_INLINE_SIZE = 5_000_000

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
                    "Content-Type": "application/json",
                    "X-Runway-Version": self.API_VERSION
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
        Generate video using Runway Gen-3 Alpha Turbo.

        Args:
            prompt: Text description of video content (max 1000 chars)
            duration: Target duration in seconds (5 or 10 for Gen-3)
            aspect_ratio: Video aspect ratio (e.g., "16:9", "9:16", "1:1")
            **kwargs: Additional parameters:
                - image_url: URL of image to use as first frame (required for image_to_video)
                - seed: Random seed for reproducibility
                - model: Model to use (default: gen3a_turbo)

        Returns:
            GenerationResult with video URL and metadata
        """
        session = await self._get_session()

        # Clamp duration to Runway's limits (5 or 10 seconds)
        duration = 10 if duration > 7 else 5

        # Convert aspect ratio to Runway format
        # Valid options: "16:9", "9:16", "768:1280", "1280:768"
        ratio_map = {
            "16:9": "16:9",
            "9:16": "9:16",
            "1:1": "16:9",  # No 1:1 support, default to 16:9
            "4:3": "16:9",  # No 4:3 support, default to 16:9
            "3:4": "9:16",  # No 3:4 support, default to 9:16
            "21:9": "16:9",  # No 21:9 support, default to 16:9
        }
        runway_ratio = ratio_map.get(aspect_ratio, "16:9")

        # Get model (default to gen3a_turbo)
        model = kwargs.get("model", "gen3a_turbo")

        # Build request payload
        # Runway image_to_video requires promptImage - if not provided, we need to
        # either generate an image first or return an error
        image_input = kwargs.get("image_url") or kwargs.get("image_prompt") or kwargs.get("promptImage")

        if not image_input:
            # No image provided - Runway requires an image for image_to_video
            # Return error suggesting user provide an image or use a different provider
            return GenerationResult(
                success=False,
                error_message="Runway image_to_video requires an image URL. Provide 'image_url' parameter or use a text-to-video provider."
            )

        # Convert local file path to data URI or upload to Runway
        prompt_image = await self._resolve_image_input(image_input)

        # Image-to-video generation
        payload = {
            "model": model,
            "promptImage": prompt_image,
            "promptText": prompt[:1000],  # Max 1000 chars
            "ratio": runway_ratio,
            "duration": duration,
        }
        endpoint = self.IMAGE_TO_VIDEO_ENDPOINT

        # Add optional seed for reproducibility
        if "seed" in kwargs:
            payload["seed"] = kwargs["seed"]

        try:
            async with session.post(
                endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)  # Initial request timeout
            ) as response:
                response_text = await response.text()

                if response.status not in (200, 201):
                    return GenerationResult(
                        success=False,
                        error_message=f"Runway API error ({response.status}): {response_text}"
                    )

                try:
                    data = await response.json()
                except:
                    # If response was already read as text, parse it
                    import json
                    data = json.loads(response_text)

                task_id = data.get("id")

                if not task_id:
                    return GenerationResult(
                        success=False,
                        error_message=f"No task ID in response: {data}"
                    )

                # Poll for completion
                result = await self._poll_until_complete(task_id)
                return result

        except asyncio.TimeoutError:
            return GenerationResult(
                success=False,
                error_message="Runway API request timed out"
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

            status = status_data.get("status", "").upper()

            if status == "SUCCEEDED":
                # Get output URL from the response
                output = status_data.get("output", [])
                video_url = None

                if isinstance(output, list) and output:
                    video_url = output[0]  # First output URL
                elif isinstance(output, dict):
                    video_url = output.get("url")
                elif isinstance(output, str):
                    video_url = output

                duration = status_data.get("duration", 5.0)
                cost = self.estimate_cost(duration)

                return GenerationResult(
                    success=True,
                    video_url=video_url,
                    duration=duration,
                    cost=cost,
                    provider_metadata={
                        "task_id": task_id,
                        "provider": "runway",
                        "model": status_data.get("model", "gen3a_turbo"),
                        **status_data
                    }
                )

            elif status in ("FAILED", "CANCELLED"):
                error = status_data.get("error") or status_data.get("failure") or "Unknown error"
                return GenerationResult(
                    success=False,
                    error_message=f"Runway generation failed: {error}"
                )

            elif status in ("PENDING", "RUNNING", "PROCESSING", "THROTTLED"):
                # Still processing, wait and retry
                await asyncio.sleep(poll_interval)
            else:
                # Unknown status, wait and retry
                await asyncio.sleep(poll_interval)

        return GenerationResult(
            success=False,
            error_message=f"Runway generation timed out after {self.config.timeout}s"
        )

    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check status of Runway generation task"""
        session = await self._get_session()

        try:
            async with session.get(
                f"{self.STATUS_ENDPOINT}/{job_id}",
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "status": "ERROR",
                        "error": f"Status check failed ({response.status}): {error_text}"
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

    async def _resolve_image_input(self, image_input: str) -> str:
        """
        Resolve image input to a format Runway accepts.

        Runway accepts:
        - HTTPS URLs to images
        - Data URIs (base64 encoded, max ~5MB)
        - runway:// URIs (from upload API, for larger files)

        This method converts local file paths to data URIs for small files,
        or uploads to Runway for larger files.

        Args:
            image_input: URL, local file path, or existing data URI

        Returns:
            String suitable for Runway's promptImage field
        """
        # Already a runway:// URI
        if image_input.startswith("runway://"):
            return image_input

        # Already a data URI
        if image_input.startswith("data:"):
            return image_input

        # Already an HTTPS URL
        if image_input.startswith("https://"):
            return image_input

        # HTTP URL - Runway may not accept, but pass through
        if image_input.startswith("http://"):
            return image_input

        # Local file path - check size and convert appropriately
        path = Path(image_input)
        if path.exists():
            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type is None:
                # Default to JPEG for unknown image types
                mime_type = "image/jpeg"

            # Read file
            with open(path, "rb") as f:
                image_data = f.read()

            # Encode to base64
            encoded = base64.b64encode(image_data).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{encoded}"

            # If small enough, use inline data URI
            if len(data_uri) <= self.MAX_INLINE_SIZE:
                return data_uri

            # Too large - use Runway's upload API
            return await self._upload_image(path, mime_type, image_data)

        # Path doesn't exist - return as-is (will likely fail at API)
        return image_input

    async def _upload_image(self, path: Path, mime_type: str, image_data: bytes) -> str:
        """
        Upload an image to Runway's upload API.

        For images larger than 5MB (base64 encoded), we need to use Runway's
        upload endpoint to get a runway:// URI.

        See: https://docs.dev.runwayml.com/assets/uploads

        Args:
            path: Path to the image file
            mime_type: MIME type of the image
            image_data: Raw image bytes

        Returns:
            runway:// URI to use in promptImage
        """
        session = await self._get_session()

        # Step 1: Request an upload URL from Runway
        upload_request = {
            "type": "ephemeral",  # Required by Runway API
            "filename": path.name,
            "contentType": mime_type
        }

        try:
            async with session.post(
                self.UPLOADS_ENDPOINT,
                json=upload_request,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise RuntimeError(f"Failed to get upload URL: {error_text}")

                upload_info = await response.json()

            # Step 2: Upload the file to the presigned URL
            upload_url = upload_info.get("uploadUrl")
            runway_uri = upload_info.get("id")  # This is the runway:// URI

            if not upload_url or not runway_uri:
                raise RuntimeError(f"Invalid upload response: {upload_info}")

            # Upload using a new session without auth headers
            async with aiohttp.ClientSession() as upload_session:
                async with upload_session.put(
                    upload_url,
                    data=image_data,
                    headers={"Content-Type": mime_type},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as upload_response:
                    if upload_response.status not in (200, 201):
                        error_text = await upload_response.text()
                        raise RuntimeError(f"Failed to upload image: {error_text}")

            return runway_uri

        except Exception as e:
            raise RuntimeError(f"Image upload failed: {str(e)}")

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
            # Try to hit the tasks endpoint to verify auth
            async with session.get(
                f"{self.STATUS_ENDPOINT}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                # 200 or 404 (no tasks) means auth worked
                return response.status in (200, 404)

        except Exception:
            return False

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
