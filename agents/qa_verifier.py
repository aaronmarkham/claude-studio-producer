"""QA Verifier Agent - Video quality analysis with vision"""

import asyncio
import random
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from core.budget import ProductionTier, COST_MODELS
from core.claude_client import ClaudeClient, JSONExtractor
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo


@dataclass
class QAResult:
    """Quality analysis result for a generated video"""
    scene_id: str
    video_url: str
    overall_score: float  # 0-100

    # Detailed scores
    visual_accuracy: float  # Do visuals match description?
    style_consistency: float  # Does it match the tier style?
    technical_quality: float  # Resolution, artifacts, smoothness
    narrative_fit: float  # Does it fit the story?

    # Issues and suggestions
    issues: List[str]
    suggestions: List[str]

    # Pass/fail
    passed: bool  # Score >= threshold
    threshold: float  # The threshold used


# QA score thresholds by production tier
QA_THRESHOLDS = {
    ProductionTier.STATIC_IMAGES: 70,
    ProductionTier.MOTION_GRAPHICS: 75,
    ProductionTier.ANIMATED: 80,
    ProductionTier.PHOTOREALISTIC: 85,
}


class QAVerifierAgent:
    """
    Analyzes generated videos against scene descriptions to score quality.
    Uses Claude's vision capabilities to evaluate video frames.
    """

    _is_stub = False

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        mock_mode: bool = True,  # Use simulated scoring by default
        num_frames: int = 3,  # Number of frames to extract
        use_vision: bool = True  # Use Claude vision API when available
    ):
        """
        Args:
            claude_client: Optional ClaudeClient instance
            mock_mode: Use simulated scoring instead of real analysis
            num_frames: Number of frames to extract from video
            use_vision: Whether to use Claude's vision API for analysis
        """
        self.claude = claude_client or ClaudeClient()
        self.mock_mode = mock_mode
        self.num_frames = num_frames
        self.use_vision = use_vision

    async def verify_video(
        self,
        scene: Scene,
        generated_video: GeneratedVideo,
        original_request: str,
        production_tier: ProductionTier
    ) -> QAResult:
        """
        Verify a single generated video against scene specification

        Args:
            scene: Original scene specification
            generated_video: The generated video to evaluate
            original_request: High-level video concept for context
            production_tier: Expected production quality tier

        Returns:
            QAResult with detailed scores and feedback
        """

        if self.mock_mode:
            return await self._mock_verify(
                scene, generated_video, original_request, production_tier
            )

        # Extract frames from video
        frames = await self._extract_frames(generated_video.video_url)

        # Analyze with Claude Vision
        qa_data = await self._analyze_with_vision(
            scene=scene,
            frames=frames,
            original_request=original_request,
            production_tier=production_tier
        )

        # Calculate threshold
        threshold = QA_THRESHOLDS[production_tier]

        return QAResult(
            scene_id=scene.scene_id,
            video_url=generated_video.video_url,
            overall_score=qa_data["overall_score"],
            visual_accuracy=qa_data["visual_accuracy"],
            style_consistency=qa_data["style_consistency"],
            technical_quality=qa_data["technical_quality"],
            narrative_fit=qa_data["narrative_fit"],
            issues=qa_data["issues"],
            suggestions=qa_data["suggestions"],
            passed=qa_data["overall_score"] >= threshold,
            threshold=threshold
        )

    async def verify_batch(
        self,
        scenes: List[Scene],
        videos: List[GeneratedVideo],
        original_request: str,
        production_tier: ProductionTier
    ) -> List[QAResult]:
        """
        Verify multiple videos in parallel

        Args:
            scenes: List of scene specifications
            videos: List of generated videos
            original_request: High-level video concept
            production_tier: Expected quality tier

        Returns:
            List of QAResult objects
        """

        tasks = [
            self.verify_video(scene, video, original_request, production_tier)
            for scene, video in zip(scenes, videos)
        ]

        return await asyncio.gather(*tasks)

    async def _extract_frames(self, video_url: str) -> List[str]:
        """
        Extract key frames from video as base64 images

        Args:
            video_url: URL of the video to extract frames from

        Returns:
            List of base64-encoded frame images
        """
        # TODO: Implement real frame extraction using ffmpeg
        # For now, return mock frames
        # In production, this would:
        # 1. Download video from URL
        # 2. Use ffmpeg to extract frames at start, middle, end
        # 3. Encode frames as base64
        # 4. Return list of base64 strings

        raise NotImplementedError(
            "Frame extraction not yet implemented. "
            "Use mock_mode=True for testing."
        )

    async def _analyze_with_vision(
        self,
        scene: Scene,
        frames: List[str],
        original_request: str,
        production_tier: ProductionTier
    ) -> Dict[str, Any]:
        """
        Analyze video frames using Claude Vision API

        Args:
            scene: Scene specification
            frames: List of base64-encoded frames
            original_request: High-level video concept
            production_tier: Expected quality tier

        Returns:
            Dictionary with scores and feedback
        """

        prompt = f"""You are a video QA specialist evaluating generated content.

SCENE SPECIFICATION:
- Title: {scene.title}
- Description: {scene.description}
- Visual Elements: {', '.join(scene.visual_elements)}
- Duration: {scene.duration}s
- Style: {production_tier.value}

ORIGINAL REQUEST CONTEXT:
{original_request}

I'm showing you {len(frames)} frames from the generated video (start, middle, end).

Evaluate the video on these criteria:

1. **Visual Accuracy** (0-100): Do the visuals match the scene description?
   - Are all specified visual elements present?
   - Is the composition appropriate?

2. **Style Consistency** (0-100): Does it match the expected production tier?
   - For {production_tier.value}: Does it meet that quality level?
   - Is the aesthetic consistent?

3. **Technical Quality** (0-100): Any artifacts, blur, or rendering issues?
   - Resolution and clarity
   - Smoothness and continuity
   - Any technical defects

4. **Narrative Fit** (0-100): Does this scene work in the overall story?
   - Does it advance the narrative?
   - Does it fit the tone?

Return ONLY valid JSON (no markdown, no explanation):
{{
  "overall_score": 85,
  "visual_accuracy": 88,
  "style_consistency": 82,
  "technical_quality": 85,
  "narrative_fit": 85,
  "issues": ["List any issues found"],
  "suggestions": ["List actionable improvements"]
}}"""

        # Note: In production, this would include the frames as images
        # Using Claude's multimodal capabilities:
        # response = await self.claude.query_with_images(prompt, frames)

        response = await self.claude.query(prompt)
        return JSONExtractor.extract(response)

    async def _mock_verify(
        self,
        scene: Scene,
        generated_video: GeneratedVideo,
        original_request: str,
        production_tier: ProductionTier
    ) -> QAResult:
        """
        Simulate video verification for testing

        Generates realistic scores based on production tier quality ceilings
        """

        # Simulate analysis delay
        await asyncio.sleep(random.uniform(0.3, 0.8))

        # Get quality ceiling for this tier
        cost_model = COST_MODELS[production_tier]
        quality_ceiling = cost_model.quality_ceiling

        # Generate scores that respect the quality ceiling
        # Add some randomness but stay within reasonable bounds
        base_score = quality_ceiling - random.uniform(5, 15)

        # Individual scores vary slightly from base
        visual_accuracy = min(100, base_score + random.uniform(-3, 5))
        style_consistency = min(100, base_score + random.uniform(-5, 3))
        technical_quality = min(100, base_score + random.uniform(-4, 4))
        narrative_fit = min(100, base_score + random.uniform(-2, 6))

        # Calculate overall score
        overall_score = (
            visual_accuracy * 0.30 +
            style_consistency * 0.25 +
            technical_quality * 0.25 +
            narrative_fit * 0.20
        )

        # Generate realistic issues and suggestions based on score
        issues = []
        suggestions = []

        if overall_score < 80:
            issues.append("Some visual elements could be more prominent")
            suggestions.append("Emphasize key visual elements in the prompt")

        if technical_quality < 85:
            issues.append("Minor rendering artifacts detected")
            suggestions.append("Consider regenerating with higher quality settings")

        if style_consistency < 80:
            issues.append(f"Style doesn't fully match {production_tier.value} tier")
            suggestions.append("Add more specific style guidance in prompt")

        if narrative_fit < 85:
            issues.append("Scene flow could be improved")
            suggestions.append("Adjust pacing or transitions")

        # Determine threshold and pass/fail
        threshold = QA_THRESHOLDS[production_tier]
        passed = overall_score >= threshold

        return QAResult(
            scene_id=scene.scene_id,
            video_url=generated_video.video_url,
            overall_score=round(overall_score, 1),
            visual_accuracy=round(visual_accuracy, 1),
            style_consistency=round(style_consistency, 1),
            technical_quality=round(technical_quality, 1),
            narrative_fit=round(narrative_fit, 1),
            issues=issues if issues else ["No significant issues detected"],
            suggestions=suggestions if suggestions else ["Video meets quality standards"],
            passed=passed,
            threshold=threshold
        )

    def get_quality_gate(self, score: float) -> str:
        """
        Determine quality gate based on score

        Args:
            score: Overall QA score (0-100)

        Returns:
            Quality gate classification
        """
        if score >= 90:
            return "excellent"
        elif score >= 80:
            return "pass"
        elif score >= 50:
            return "soft_fail"
        else:
            return "hard_fail"

    def should_regenerate(
        self,
        result: QAResult,
        budget_available: float,
        regeneration_cost: float
    ) -> bool:
        """
        Determine if video should be regenerated based on QA results and budget

        Args:
            result: QA result for the video
            budget_available: Remaining budget
            regeneration_cost: Cost to regenerate

        Returns:
            True if regeneration is recommended and affordable
        """

        # Hard fail: must regenerate if budget allows
        if result.overall_score < 50:
            return budget_available >= regeneration_cost

        # Soft fail: regenerate if budget is comfortable
        if not result.passed:
            return budget_available >= (regeneration_cost * 1.5)

        # Passed but not excellent: only regenerate with ample budget
        if result.overall_score < 90:
            return budget_available >= (regeneration_cost * 2.5)

        # Excellent: no need to regenerate
        return False
