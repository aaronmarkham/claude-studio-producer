"""
OpenAI DALL-E Image Generation Provider

Pricing (as of 2025):
- DALL-E 3: $0.04 (standard) / $0.08 (HD) for 1024x1024
- DALL-E 3: $0.08 (standard) / $0.12 (HD) for 1792x1024 or 1024x1792
- DALL-E 2: $0.02 for 1024x1024, $0.018 for 512x512, $0.016 for 256x256

Features:
- Text-to-image generation (DALL-E 2 & 3)
- Image editing with masks (DALL-E 2 only)
- Image variations (DALL-E 2 only)
- Style and quality controls (DALL-E 3 only)

API Docs: https://platform.openai.com/docs/guides/images
"""

import asyncio
import aiohttp
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from ..base import ImageProvider, ImageProviderConfig, ImageGenerationResult


class DalleProvider(ImageProvider):
    """OpenAI DALL-E image generation provider"""

    _is_stub = False  # Fully implemented

    # Size presets for convenience
    SIZES = {
        "square": "1024x1024",
        "portrait": "1024x1792",
        "landscape": "1792x1024"
    }

    # Pricing per size and model
    COSTS_DALLE3 = {
        "1024x1024": {"standard": 0.04, "hd": 0.08},
        "1024x1792": {"standard": 0.08, "hd": 0.12},
        "1792x1024": {"standard": 0.08, "hd": 0.12}
    }

    COSTS_DALLE2 = {
        "1024x1024": 0.02,
        "512x512": 0.018,
        "256x256": 0.016
    }

    # API endpoint
    API_URL = "https://api.openai.com/v1/images/generations"

    def __init__(self, config: Optional[ImageProviderConfig] = None):
        """
        Initialize DALL-E provider.

        Args:
            config: Provider configuration. If None, creates default config
                   using OPENAI_API_KEY from environment.
        """
        if config is None:
            import os
            api_key = os.environ.get("OPENAI_API_KEY")
            config = ImageProviderConfig(api_key=api_key)

        if not config.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable.")

        super().__init__(config)
        self.default_model = "dall-e-3"

    @property
    def name(self) -> str:
        return "dalle"

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        **kwargs
    ) -> ImageGenerationResult:
        """
        Generate image using DALL-E.

        Args:
            prompt: Text description of the desired image
            size: Image size. For DALL-E 3: '1024x1024', '1792x1024', '1024x1792'.
                  For DALL-E 2: '256x256', '512x512', '1024x1024'.
                  Also accepts presets: 'square', 'portrait', 'landscape'.
            **kwargs: Additional parameters:
                - model: 'dall-e-3' (default) or 'dall-e-2'
                - quality: 'standard' or 'hd' (DALL-E 3 only)
                - style: 'vivid' or 'natural' (DALL-E 3 only)
                - n: Number of images (only 1 for DALL-E 3, 1-10 for DALL-E 2)
                - response_format: 'url' or 'b64_json'

        Returns:
            ImageGenerationResult with image URL/path and metadata
        """
        model = kwargs.get("model", self.default_model)
        quality = kwargs.get("quality", "standard")
        style = kwargs.get("style", "vivid")
        n = kwargs.get("n", 1)
        response_format = kwargs.get("response_format", "url")

        # Map preset names to actual sizes
        actual_size = self.SIZES.get(size, size)

        # Validate DALL-E 3 constraints
        if model == "dall-e-3" and n > 1:
            return ImageGenerationResult(
                success=False,
                error_message="DALL-E 3 only supports n=1 (single image per request)"
            )

        # Estimate cost
        cost = self.estimate_cost(actual_size, model=model, quality=quality)

        # Build request body
        request_body = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": actual_size,
            "response_format": response_format
        }

        # DALL-E 3 specific parameters
        if model == "dall-e-3":
            request_body["quality"] = quality
            request_body["style"] = style

        try:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_body
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return ImageGenerationResult(
                            success=False,
                            error_message=f"OpenAI API error ({response.status}): {error_text}",
                            cost=cost
                        )

                    result = await response.json()

            # Extract image data
            image_data = result.get("data", [{}])[0]
            image_url = image_data.get("url")
            revised_prompt = image_data.get("revised_prompt")

            # Parse size for width/height
            width, height = map(int, actual_size.split("x"))

            # Optionally download the image
            image_path = None
            if image_url and kwargs.get("download", False):
                image_path = await self._download_image(image_url, prompt)

            return ImageGenerationResult(
                success=True,
                image_url=image_url,
                image_path=image_path,
                width=width,
                height=height,
                format="png",
                cost=cost,
                provider_metadata={
                    "model": model,
                    "quality": quality if model == "dall-e-3" else None,
                    "style": style if model == "dall-e-3" else None,
                    "revised_prompt": revised_prompt,
                    "created": result.get("created")
                }
            )

        except aiohttp.ClientError as e:
            return ImageGenerationResult(
                success=False,
                error_message=f"OpenAI API request failed: {str(e)}",
                cost=cost
            )
        except asyncio.TimeoutError:
            return ImageGenerationResult(
                success=False,
                error_message=f"OpenAI API request timed out after {self.config.timeout}s",
                cost=cost
            )
        except Exception as e:
            return ImageGenerationResult(
                success=False,
                error_message=f"DALL-E generation failed: {str(e)}",
                cost=cost
            )

    async def _download_image(self, url: str, prompt: str) -> str:
        """Download image from URL and save locally."""
        output_dir = Path("artifacts/images")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from prompt hash
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        output_path = output_dir / f"dalle_{prompt_hash}.png"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    output_path.write_bytes(await response.read())
                    return str(output_path)

        return None

    def estimate_cost(self, size: str = "1024x1024", **kwargs) -> float:
        """
        Estimate DALL-E generation cost.

        Args:
            size: Image size ("1024x1024", "1024x1792", "1792x1024", etc.)
            **kwargs: Can include:
                - model: 'dall-e-3' or 'dall-e-2'
                - quality: 'standard' or 'hd' (DALL-E 3 only)

        Returns:
            Estimated cost in USD
        """
        # Map preset names to actual sizes
        actual_size = self.SIZES.get(size, size)
        model = kwargs.get("model", self.default_model)
        quality = kwargs.get("quality", "standard")

        if model == "dall-e-3":
            size_costs = self.COSTS_DALLE3.get(actual_size, self.COSTS_DALLE3["1024x1024"])
            return size_costs.get(quality, size_costs["standard"])
        else:
            return self.COSTS_DALLE2.get(actual_size, 0.02)

    async def validate_credentials(self) -> bool:
        """
        Validate OpenAI API key by making a minimal request.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            # Use a simple models list endpoint to validate
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.config.api_key}"}
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    def get_models(self) -> List[Dict[str, Any]]:
        """Get list of available DALL-E models."""
        return [
            {
                "model_id": "dall-e-3",
                "name": "DALL-E 3",
                "description": "Latest model with improved quality and prompt understanding",
                "capabilities": ["text-to-image", "style-control", "quality-control"],
                "limitations": ["n=1 only", "no edits/variations"],
                "sizes": ["1024x1024", "1792x1024", "1024x1792"]
            },
            {
                "model_id": "dall-e-2",
                "name": "DALL-E 2",
                "description": "Previous generation, faster and cheaper, supports edits",
                "capabilities": ["text-to-image", "image-edit", "image-variation", "batch"],
                "limitations": ["lower quality", "square only"],
                "sizes": ["256x256", "512x512", "1024x1024"]
            }
        ]

    def get_tips(self) -> List[str]:
        """Get usage tips for DALL-E."""
        return [
            "DALL-E 3 automatically revises prompts for safety/quality - check revised_prompt in response",
            "Use 'natural' style for realistic images, 'vivid' for dramatic/artistic (DALL-E 3)",
            "Use 'hd' quality for fine details when needed (costs 2x)",
            "Be specific and descriptive in prompts for best results",
            "Image URLs expire after 1 hour - download if needed long-term",
            "Use b64_json response format to avoid URL expiration concerns"
        ]

    def get_gotchas(self) -> List[str]:
        """Get common gotchas and limitations."""
        return [
            "DALL-E 3 only supports n=1 (single image per request)",
            "Image edits and variations are DALL-E 2 only",
            "Image URLs expire after 60 minutes",
            "Content policy violations return 400 errors",
            "DALL-E 3: ~30-60s generation, DALL-E 2: ~10-20s",
            "No negative prompts or advanced params (CFG, steps, etc.)"
        ]

    # Alias for CLI compatibility
    async def generate(self, prompt: str, **kwargs) -> ImageGenerationResult:
        """Alias for generate_image() for CLI compatibility."""
        size = kwargs.pop("size", "1024x1024")
        return await self.generate_image(prompt, size=size, **kwargs)
