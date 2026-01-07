"""Video Generator Agent - Generates videos via external APIs"""

import asyncio
import random
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from enum import Enum

from core.budget import ProductionTier, COST_MODELS
from agents.script_writer import Scene


class VideoProvider(Enum):
    """Video generation providers"""
    RUNWAY_GEN3 = "runway_gen3"
    PIKA = "pika"
    STABILITY = "stability"
    DALLE = "dalle"
    MOCK = "mock"  # For testing without real APIs


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


# Provider selection based on production tier
TIER_TO_PROVIDER = {
    ProductionTier.STATIC_IMAGES: VideoProvider.DALLE,
    ProductionTier.MOTION_GRAPHICS: VideoProvider.STABILITY,
    ProductionTier.ANIMATED: VideoProvider.PIKA,
    ProductionTier.PHOTOREALISTIC: VideoProvider.RUNWAY_GEN3,
}

# Style guidance for each tier
TIER_STYLES = {
    ProductionTier.STATIC_IMAGES: "clean illustration, high contrast, professional presentation",
    ProductionTier.MOTION_GRAPHICS: "smooth motion graphics, modern design, infographic style",
    ProductionTier.ANIMATED: "stylized animation, engaging movement, vibrant colors",
    ProductionTier.PHOTOREALISTIC: "cinematic realism, natural lighting, professional cinematography",
}


class VideoGeneratorAgent:
    """
    Generates video content by calling external video generation APIs
    """

    def __init__(
        self,
        provider: Optional[VideoProvider] = None,
        num_variations: int = 3,
        mock_mode: bool = True,  # Use mock generation by default
        retry_attempts: int = 3,
        backoff_seconds: float = 2.0
    ):
        """
        Args:
            provider: Video provider to use (auto-selected if None)
            num_variations: Number of video variations to generate per scene
            mock_mode: Use simulated generation instead of real APIs
            retry_attempts: Number of retries on failure
            backoff_seconds: Initial backoff delay for retries
        """
        self.default_provider = provider
        self.num_variations = num_variations
        self.mock_mode = mock_mode
        self.retry_attempts = retry_attempts
        self.backoff_seconds = backoff_seconds

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
        provider = self.default_provider or TIER_TO_PROVIDER[production_tier]

        videos = []
        spent = 0.0

        for i in range(variations_to_generate):
            # Estimate cost before generating
            estimated_cost = self._estimate_cost(scene.duration, production_tier)

            if spent + estimated_cost > budget_limit:
                print(f"⚠️  Budget limit reached after {i} variations (${spent:.2f}/${budget_limit:.2f})")
                break

            # Generate single variation with retries
            video = await self._generate_with_retry(
                scene=scene,
                variation_id=i,
                provider=provider,
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
        provider: VideoProvider,
        tier: ProductionTier
    ) -> Optional[GeneratedVideo]:
        """Generate a single video with retry logic"""

        for attempt in range(self.retry_attempts):
            try:
                video = await self._generate_single(
                    scene=scene,
                    variation_id=variation_id,
                    provider=provider,
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
        provider: VideoProvider,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate a single video variation"""

        if self.mock_mode or provider == VideoProvider.MOCK:
            return await self._mock_generate(scene, variation_id, provider, tier)

        # Real API generation (to be implemented when API keys are available)
        if provider == VideoProvider.RUNWAY_GEN3:
            return await self._generate_runway(scene, variation_id, tier)
        elif provider == VideoProvider.PIKA:
            return await self._generate_pika(scene, variation_id, tier)
        elif provider == VideoProvider.STABILITY:
            return await self._generate_stability(scene, variation_id, tier)
        elif provider == VideoProvider.DALLE:
            return await self._generate_dalle(scene, variation_id, tier)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def _mock_generate(
        self,
        scene: Scene,
        variation_id: int,
        provider: VideoProvider,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Simulate video generation for testing"""

        # Simulate API delay
        await asyncio.sleep(random.uniform(0.5, 1.5))

        cost_model = COST_MODELS[tier]
        generation_cost = scene.duration * cost_model.cost_per_second

        # Create mock video
        return GeneratedVideo(
            scene_id=scene.scene_id,
            variation_id=variation_id,
            video_url=f"https://mock-cdn.example.com/{scene.scene_id}_v{variation_id}.mp4",
            thumbnail_url=f"https://mock-cdn.example.com/{scene.scene_id}_v{variation_id}_thumb.jpg",
            duration=scene.duration,
            generation_cost=generation_cost,
            provider=provider.value,
            metadata={
                "prompt": self._build_prompt(scene, tier),
                "tier": tier.value,
                "model": f"{provider.value}_latest",
                "resolution": "1920x1080",
                "fps": 30
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

    def _estimate_cost(self, duration: float, tier: ProductionTier) -> float:
        """Estimate generation cost for a scene"""
        cost_model = COST_MODELS[tier]
        return duration * cost_model.cost_per_second

    # Placeholder methods for real API integrations
    # These will be implemented when API keys are available

    async def _generate_runway(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate video using Runway Gen-3 API"""
        # TODO: Implement Runway API integration
        # Requires RUNWAY_API_KEY environment variable
        raise NotImplementedError("Runway API integration not yet implemented. Use mock_mode=True for testing.")

    async def _generate_pika(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate video using Pika Labs API"""
        # TODO: Implement Pika API integration
        # Requires PIKA_API_KEY environment variable
        raise NotImplementedError("Pika API integration not yet implemented. Use mock_mode=True for testing.")

    async def _generate_stability(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate video using Stability AI API"""
        # TODO: Implement Stability AI integration
        # Requires STABILITY_API_KEY environment variable
        raise NotImplementedError("Stability AI integration not yet implemented. Use mock_mode=True for testing.")

    async def _generate_dalle(
        self,
        scene: Scene,
        variation_id: int,
        tier: ProductionTier
    ) -> GeneratedVideo:
        """Generate static images using DALL-E"""
        # TODO: Implement DALL-E API integration + Ken Burns effect
        # Requires OPENAI_API_KEY environment variable
        raise NotImplementedError("DALL-E integration not yet implemented. Use mock_mode=True for testing.")
