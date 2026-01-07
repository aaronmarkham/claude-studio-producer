"""Video Generator Agent - Generates videos via external APIs"""

import asyncio
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from strands import tool

from core.budget import ProductionTier, COST_MODELS
from core.providers import VideoProvider, MockVideoProvider
from agents.script_writer import Scene
from .base import StudioAgent


@dataclass
class GeneratedVideo:
    """A single generated video variation"""
    scene_id: str
    variation_id: int
    video_url: str
    thumbnail_url: str
    duration: float
    generation_cost: float
    provider: str
    metadata: Dict[str, Any]
    quality_score: Optional[float] = None  # Set by QA agent later


# Style guidance for each tier
TIER_STYLES = {
    ProductionTier.STATIC_IMAGES: "clean illustration, high contrast, professional presentation",
    ProductionTier.MOTION_GRAPHICS: "smooth motion graphics, modern design, infographic style",
    ProductionTier.ANIMATED: "stylized animation, engaging movement, vibrant colors",
    ProductionTier.PHOTOREALISTIC: "cinematic realism, natural lighting, professional cinematography",
}


class VideoGeneratorAgent(StudioAgent):
    """
    Generates video content by calling external video generation APIs.

    Uses dependency injection with VideoProvider interface for testability
    and flexibility in switching between providers.
    """

    _is_stub = False

    def __init__(
        self,
        provider: Optional[VideoProvider] = None,
        num_variations: int = 3,
        retry_attempts: int = 3,
        backoff_seconds: float = 2.0
    ):
        """
        Args:
            provider: VideoProvider instance (defaults to MockVideoProvider)
            num_variations: Number of video variations to generate per scene
            retry_attempts: Number of retries on failure
            backoff_seconds: Initial backoff delay for retries
        """
        super().__init__(claude_client=None)  # VideoGenerator doesn't use Claude directly
        self.provider = provider or MockVideoProvider()
        self.num_variations = num_variations
        self.retry_attempts = retry_attempts
        self.backoff_seconds = backoff_seconds

    @tool
    async def generate_scene(
        self,
        scene: Scene,
        production_tier: ProductionTier,
        budget_limit: float,
        num_variations: Optional[int] = None
    ) -> List[GeneratedVideo]:
        """
        Generate video variations for a scene

        Args:
            scene: Scene to generate video for
            production_tier: Quality tier for generation
            budget_limit: Maximum budget for this scene
            num_variations: Override default number of variations

        Returns:
            List of generated video variations
        """
        variations_to_generate = num_variations or self.num_variations

        videos = []
        spent = 0.0

        for i in range(variations_to_generate):
            # Estimate cost before generating
            estimated_cost = self.provider.estimate_cost(scene.duration, tier=production_tier)

            if spent + estimated_cost > budget_limit:
                print(f"⚠️  Budget limit reached after {i} variations (${spent:.2f}/${budget_limit:.2f})")
                break

            # Generate single variation with retries
            video = await self._generate_with_retry(
                scene=scene,
                variation_id=i,
                tier=production_tier
            )

            if video:
                videos.append(video)
                spent += video.generation_cost
            else:
                print(f"❌ Failed to generate variation {i} for {scene.scene_id}")

        return videos

    async def _generate_with_retry(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> Optional[GeneratedVideo]:
        """Generate a single video with retry logic"""

        for attempt in range(self.retry_attempts):
            try:
                video = await self._generate_single(
                    scene=scene,
                    variation_id=variation_id,
                    tier=tier
                )
                return video

            except Exception as e:
                if attempt < self.retry_attempts - 1:
                    delay = self.backoff_seconds * (2 ** attempt)
                    print(f"⚠️  Generation failed (attempt {attempt + 1}): {e}")
                    print(f"   Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    print(f"❌ Generation failed after {self.retry_attempts} attempts: {e}")
                    return None

    async def _generate_single(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate a single video variation using the injected provider"""

        # Build prompt for video generation
        prompt = self._build_prompt(scene, tier)

        # Call provider to generate video
        result = await self.provider.generate_video(
            prompt=prompt,
            duration=scene.duration,
            aspect_ratio="16:9",
            tier=tier
        )

        if not result.success:
            raise RuntimeError(f"Provider generation failed: {result.error_message}")

        # Convert provider result to GeneratedVideo
        return GeneratedVideo(
            scene_id=scene.scene_id,
            variation_id=variation_id,
            video_url=result.video_url or "",
            thumbnail_url=f"{result.video_url}_thumb.jpg" if result.video_url else "",
            duration=result.duration or scene.duration,
            generation_cost=result.cost or 0.0,
            provider=result.provider_metadata.get("provider", "unknown"),
            metadata={
                "prompt": prompt,
                "tier": tier.value,
                **result.provider_metadata
            }
        )

    def _build_prompt(self, scene: Scene, tier: ProductionTier) -> str:
        """Build optimized video generation prompt"""

        base = scene.description

        # Add visual elements
        if scene.visual_elements:
            elements = ", ".join(scene.visual_elements)
            base += f". Visual elements: {elements}"

        # Add style guidance
        style = TIER_STYLES[tier]
        base += f". Style: {style}"

        # Add scene-specific hints
        if scene.prompt_hints:
            hints = ", ".join(scene.prompt_hints)
            base += f". {hints}"

        # Add duration hint for providers that support it
        base += f". Duration: {scene.duration}s"

        return base
