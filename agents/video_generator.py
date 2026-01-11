"""Video Generator Agent - Generates videos via external APIs"""

import asyncio
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from strands import tool

from core.budget import ProductionTier, COST_MODELS
from core.providers import VideoProvider, MockVideoProvider
from core.models.execution import ExecutionGraph, ExecutionMode, SceneGroup
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
        num_variations: Optional[int] = None,
        image_url: Optional[str] = None
    ) -> List[GeneratedVideo]:
        """
        Generate video variations for a scene

        Args:
            scene: Scene to generate video for
            production_tier: Quality tier for generation
            budget_limit: Maximum budget for this scene
            num_variations: Override default number of variations
            image_url: Optional input image for image-to-video providers (e.g., Runway)

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
                tier=production_tier,
                image_url=image_url
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
        tier: ProductionTier,
        image_url: Optional[str] = None
    ) -> Optional[GeneratedVideo]:
        """Generate a single video with retry logic"""

        for attempt in range(self.retry_attempts):
            try:
                video = await self._generate_single(
                    scene=scene,
                    variation_id=variation_id,
                    tier=tier,
                    image_url=image_url
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
        tier: ProductionTier,
        image_url: Optional[str] = None
    ) -> GeneratedVideo:
        """Generate a single video variation using the injected provider"""

        # Build prompt for video generation
        prompt = self._build_prompt(scene, tier)

        # Call provider to generate video
        result = await self.provider.generate_video(
            prompt=prompt,
            duration=scene.duration,
            aspect_ratio="16:9",
            tier=tier,
            image_url=image_url  # For image-to-video providers like Runway
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

    async def generate_scenes_parallel(
        self,
        scenes: List[Scene],
        production_tier: ProductionTier,
        budget_per_scene: float,
        num_variations: int = 1,
        seed_asset_lookup: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, List[GeneratedVideo]]:
        """
        Generate videos for multiple scenes in parallel.

        Submits all generation requests at once, then waits for all to complete.
        This is much faster than sequential generation for providers like Luma.

        Args:
            scenes: List of scenes to generate
            production_tier: Quality tier
            budget_per_scene: Budget limit per scene
            num_variations: Number of variations per scene
            seed_asset_lookup: Optional dict mapping asset IDs to asset objects
            progress_callback: Optional callback(scene_id, status, elapsed) for updates

        Returns:
            Dict mapping scene_id to list of GeneratedVideo objects
        """
        # Check if provider supports parallel generation
        if not hasattr(self.provider, 'submit_generation'):
            # Fall back to sequential for providers without parallel support
            results = {}
            for scene in scenes:
                start_image_url = self._get_seed_image(scene, seed_asset_lookup)
                videos = await self.generate_scene(
                    scene=scene,
                    production_tier=production_tier,
                    budget_limit=budget_per_scene,
                    num_variations=num_variations,
                    image_url=start_image_url
                )
                results[scene.scene_id] = videos
            return results

        # Phase 1: Submit all generations
        pending = []  # List of (scene, variation_id, generation_id, submission_info)

        for scene in scenes:
            start_image_url = self._get_seed_image(scene, seed_asset_lookup)
            prompt = self._build_prompt(scene, production_tier)

            for var_id in range(num_variations):
                try:
                    kwargs = {}
                    if start_image_url:
                        kwargs["start_image_url"] = start_image_url

                    submission = await self.provider.submit_generation(
                        prompt=prompt,
                        duration=scene.duration,
                        aspect_ratio="16:9",
                        **kwargs
                    )

                    pending.append({
                        "scene": scene,
                        "variation_id": var_id,
                        "generation_id": submission["generation_id"],
                        "submission_info": submission,
                        "prompt": prompt
                    })

                    print(f"[Parallel] Submitted {scene.scene_id} v{var_id}: {submission['generation_id'][:12]}...")

                except Exception as e:
                    print(f"[Parallel] Failed to submit {scene.scene_id} v{var_id}: {e}")

        if not pending:
            return {}

        print(f"[Parallel] All {len(pending)} generations submitted, waiting for completion...")

        # Phase 2: Wait for all generations in parallel
        async def wait_single(item):
            try:
                result = await self.provider.wait_for_generation(
                    generation_id=item["generation_id"],
                    submission_info=item["submission_info"],
                    quiet=True  # Suppress individual status messages
                )
                return {
                    "scene": item["scene"],
                    "variation_id": item["variation_id"],
                    "result": result,
                    "prompt": item["prompt"]
                }
            except Exception as e:
                return {
                    "scene": item["scene"],
                    "variation_id": item["variation_id"],
                    "result": None,
                    "error": str(e),
                    "prompt": item["prompt"]
                }

        # Wait for all in parallel
        completed = await asyncio.gather(*[wait_single(item) for item in pending])

        # Phase 3: Organize results by scene
        results: Dict[str, List[GeneratedVideo]] = {}

        for item in completed:
            scene = item["scene"]
            if scene.scene_id not in results:
                results[scene.scene_id] = []

            if item.get("result") and item["result"].success:
                video = GeneratedVideo(
                    scene_id=scene.scene_id,
                    variation_id=item["variation_id"],
                    video_url=item["result"].video_url or "",
                    thumbnail_url="",
                    duration=item["result"].duration or scene.duration,
                    generation_cost=item["result"].cost or 0.0,
                    provider=item["result"].provider_metadata.get("provider", "unknown"),
                    metadata={
                        "prompt": item["prompt"],
                        "tier": production_tier.value,
                        **item["result"].provider_metadata
                    }
                )
                results[scene.scene_id].append(video)
                print(f"[Parallel] Completed {scene.scene_id} v{item['variation_id']}")
            else:
                error = item.get("error", "Unknown error")
                print(f"[Parallel] Failed {scene.scene_id} v{item['variation_id']}: {error}")

        return results

    async def generate_with_graph(
        self,
        scenes: List[Scene],
        graph: ExecutionGraph,
        production_tier: ProductionTier,
        budget_per_scene: float,
        num_variations: int = 1,
        seed_asset_lookup: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Any] = None
    ) -> Dict[str, List[GeneratedVideo]]:
        """
        Generate videos according to execution graph.

        Handles mixed parallel/sequential execution based on graph structure.
        Sequential groups use generation chaining for visual continuity.

        Args:
            scenes: List of all scenes
            graph: ExecutionGraph defining execution order and dependencies
            production_tier: Quality tier for generation
            budget_per_scene: Budget limit per scene
            num_variations: Number of variations per scene
            seed_asset_lookup: Optional dict mapping asset IDs to asset objects
            progress_callback: Optional callback for progress updates

        Returns:
            Dict mapping scene_id to list of GeneratedVideo objects
        """
        all_results: Dict[str, List[GeneratedVideo]] = {}
        scene_lookup = {s.scene_id: s for s in scenes}

        # Get execution waves - scenes that can run in parallel within each wave
        waves = graph.get_execution_waves()

        # Track the last generation ID for chaining sequential scenes
        last_generation_id: Optional[str] = None

        for wave_idx, wave_scene_ids in enumerate(waves):
            print(f"\n[Graph] Executing wave {wave_idx + 1}/{len(waves)}: {wave_scene_ids}")

            # Get scenes for this wave
            wave_scenes = [scene_lookup[sid] for sid in wave_scene_ids if sid in scene_lookup]
            if not wave_scenes:
                print(f"[Graph]   No scenes found for wave, skipping")
                continue

            # Determine if this wave is parallel or sequential based on the scenes' groups
            # If all scenes are in the same sequential group, process them sequentially
            # Otherwise process in parallel
            scene_groups = [graph.get_scene_group(sid) for sid in wave_scene_ids]
            first_group = scene_groups[0] if scene_groups else None

            if len(wave_scenes) == 1 and first_group and first_group.mode == ExecutionMode.SEQUENTIAL:
                # Single scene from a sequential group - use chained generation
                scene = wave_scenes[0]
                print(f"[Graph]   Sequential scene: {scene.scene_id}")

                # Get seed image for first scene in the group
                start_image_url = None
                if scene.scene_id == first_group.scene_ids[0]:
                    start_image_url = self._get_seed_image(scene, seed_asset_lookup)

                videos = await self._generate_scene_chained(
                    scene=scene,
                    production_tier=production_tier,
                    budget_limit=budget_per_scene,
                    num_variations=num_variations,
                    start_image_url=start_image_url,
                    chain_from_generation_id=last_generation_id
                )

                all_results[scene.scene_id] = videos

                # Update last generation ID for next scene in chain
                if videos:
                    last_generation_id = videos[0].metadata.get("generation_id")

            else:
                # Multiple scenes or parallel group - run in parallel
                print(f"[Graph]   Parallel scenes: {[s.scene_id for s in wave_scenes]}")

                results = await self.generate_scenes_parallel(
                    scenes=wave_scenes,
                    production_tier=production_tier,
                    budget_per_scene=budget_per_scene,
                    num_variations=num_variations,
                    seed_asset_lookup=seed_asset_lookup
                )

                all_results.update(results)

                # Get last generation ID from results (for potential chaining)
                if results:
                    last_scene_id = wave_scenes[-1].scene_id
                    if last_scene_id in results and results[last_scene_id]:
                        last_video = results[last_scene_id][0]
                        last_generation_id = last_video.metadata.get("generation_id")

        return all_results

    async def _generate_group_parallel(
        self,
        group: 'SceneGroup',
        scenes: List[Scene],
        production_tier: ProductionTier,
        budget_per_scene: float,
        num_variations: int,
        seed_asset_lookup: Optional[Dict[str, Any]],
        chain_from_generation_id: Optional[str] = None
    ) -> tuple[Dict[str, List[GeneratedVideo]], Optional[str]]:
        """
        Generate all scenes in a group in parallel.

        Returns:
            Tuple of (results dict, last_generation_id for chaining)
        """
        print(f"[Graph] Parallel group '{group.group_id}': {len(scenes)} scenes")

        # Use existing parallel generation
        results = await self.generate_scenes_parallel(
            scenes=scenes,
            production_tier=production_tier,
            budget_per_scene=budget_per_scene,
            num_variations=num_variations,
            seed_asset_lookup=seed_asset_lookup
        )

        # Get last generation ID from results (for potential chaining)
        last_gen_id = None
        if results:
            # Get from last scene's first video
            last_scene_id = scenes[-1].scene_id
            if last_scene_id in results and results[last_scene_id]:
                last_video = results[last_scene_id][0]
                last_gen_id = last_video.metadata.get("generation_id")

        return results, last_gen_id

    async def _generate_group_sequential(
        self,
        group: 'SceneGroup',
        scenes: List[Scene],
        production_tier: ProductionTier,
        budget_per_scene: float,
        num_variations: int,
        seed_asset_lookup: Optional[Dict[str, Any]],
        chain_from_generation_id: Optional[str] = None
    ) -> tuple[Dict[str, List[GeneratedVideo]], Optional[str]]:
        """
        Generate scenes sequentially with generation chaining.

        Each scene uses the last frame of the previous scene as a keyframe
        to maintain visual continuity.

        Returns:
            Tuple of (results dict, last_generation_id for chaining)
        """
        print(f"[Graph] Sequential group '{group.group_id}': {len(scenes)} scenes (chained)")

        results: Dict[str, List[GeneratedVideo]] = {}
        current_chain_id = chain_from_generation_id

        for i, scene in enumerate(scenes):
            print(f"[Graph]   Scene {i+1}/{len(scenes)}: {scene.scene_id}")

            # Get seed image for first scene if available
            start_image_url = None
            if i == 0:
                start_image_url = self._get_seed_image(scene, seed_asset_lookup)

            # Generate with chaining support
            videos = await self._generate_scene_chained(
                scene=scene,
                production_tier=production_tier,
                budget_limit=budget_per_scene,
                num_variations=num_variations,
                start_image_url=start_image_url,
                chain_from_generation_id=current_chain_id
            )

            results[scene.scene_id] = videos

            # Update chain ID for next scene
            if videos:
                current_chain_id = videos[0].metadata.get("generation_id")

        return results, current_chain_id

    async def _generate_scene_chained(
        self,
        scene: Scene,
        production_tier: ProductionTier,
        budget_limit: float,
        num_variations: int,
        start_image_url: Optional[str] = None,
        chain_from_generation_id: Optional[str] = None
    ) -> List[GeneratedVideo]:
        """
        Generate scene with optional chaining from previous generation.

        Uses the provider's keyframe/continuation feature if available.
        """
        videos = []
        spent = 0.0
        prompt = self._build_prompt(scene, production_tier)

        for var_id in range(num_variations):
            estimated_cost = self.provider.estimate_cost(scene.duration, tier=production_tier)

            if spent + estimated_cost > budget_limit:
                print(f"⚠️  Budget limit reached after {var_id} variations")
                break

            try:
                # Use submit/wait pattern if provider supports it (needed for chaining)
                if hasattr(self.provider, 'submit_generation'):
                    # Build kwargs for generation
                    kwargs = {}
                    if start_image_url:
                        kwargs["start_image_url"] = start_image_url
                    if chain_from_generation_id:
                        kwargs["continue_from_generation_id"] = chain_from_generation_id

                    # Submit generation
                    try:
                        submission = await self.provider.submit_generation(
                            prompt=prompt,
                            duration=scene.duration,
                            aspect_ratio="16:9",
                            **kwargs
                        )
                        print(f"[Chained] Submitted {scene.scene_id} v{var_id}: {submission['generation_id'][:12]}...")
                    except Exception as submit_err:
                        print(f"❌ Submit failed for {scene.scene_id} v{var_id}: {submit_err}")
                        continue  # Skip to next variation

                    # Wait for completion
                    try:
                        result = await self.provider.wait_for_generation(
                            generation_id=submission["generation_id"],
                            submission_info=submission,
                            quiet=True
                        )
                    except Exception as wait_err:
                        print(f"❌ Wait failed for {scene.scene_id} v{var_id}: {wait_err}")
                        continue  # Skip to next variation

                    if result.success:
                        video = GeneratedVideo(
                            scene_id=scene.scene_id,
                            variation_id=var_id,
                            video_url=result.video_url or "",
                            thumbnail_url="",
                            duration=result.duration or scene.duration,
                            generation_cost=result.cost or 0.0,
                            provider=result.provider_metadata.get("provider", "unknown"),
                            metadata={
                                "prompt": prompt,
                                "tier": production_tier.value,
                                "generation_id": submission["generation_id"],
                                "chained_from": chain_from_generation_id,
                                **result.provider_metadata
                            }
                        )
                        videos.append(video)
                        spent += video.generation_cost
                        print(f"[Chained] Completed {scene.scene_id} v{var_id}")
                    else:
                        print(f"❌ Generation failed for {scene.scene_id} v{var_id}: {result.error_message}")
                else:
                    # Fall back to standard generation (for providers without submit/wait)
                    video = await self._generate_with_retry(
                        scene=scene,
                        variation_id=var_id,
                        tier=production_tier,
                        image_url=start_image_url
                    )
                    if video:
                        videos.append(video)
                        spent += video.generation_cost

            except Exception as e:
                import traceback
                print(f"❌ Failed to generate {scene.scene_id} v{var_id}: {e}")
                print(f"   Traceback: {traceback.format_exc()}")

        return videos

    def _get_seed_image(self, scene: Scene, seed_asset_lookup: Optional[Dict[str, Any]]) -> Optional[str]:
        """Get seed image URL for a scene if available"""
        if not scene.seed_asset_refs or not seed_asset_lookup:
            return None

        for ref in scene.seed_asset_refs:
            if ref.usage == "source_frame" and ref.asset_id in seed_asset_lookup:
                asset = seed_asset_lookup[ref.asset_id]
                return getattr(asset, 'local_path', None)
        return None

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
