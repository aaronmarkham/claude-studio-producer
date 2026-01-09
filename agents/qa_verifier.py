"""QA Verifier Agent - Video quality analysis with vision"""

import asyncio
import base64
import os
import random
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import httpx
from strands import tool

from core.budget import ProductionTier, COST_MODELS
from core.claude_client import ClaudeClient, JSONExtractor
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from .base import StudioAgent


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


class QAVerifierAgent(StudioAgent):
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
        super().__init__(claude_client=claude_client)
        self.mock_mode = mock_mode
        self.num_frames = num_frames
        self.use_vision = use_vision

    @tool
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

    async def _extract_frames(self, video_path: str) -> List[Dict[str, str]]:
        """
        Extract key frames from video as base64 images

        Args:
            video_path: URL or local path of the video to extract frames from

        Returns:
            List of dicts with 'data' (base64) and 'media_type' keys
        """
        # Download video if it's a URL
        if video_path.startswith("http"):
            local_path = await self._download_video(video_path)
            cleanup_after = True
        else:
            local_path = video_path
            cleanup_after = False

        try:
            # Get video duration using ffprobe
            duration = await self._get_video_duration(local_path)

            frames = []
            # Extract frames at evenly spaced intervals
            for i in range(self.num_frames):
                # Calculate timestamp (avoid very start/end)
                timestamp = (duration / (self.num_frames + 1)) * (i + 1)

                # Create temp file for frame
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp_path = tmp.name

                try:
                    # Extract frame with ffmpeg
                    result = subprocess.run(
                        [
                            'ffmpeg', '-ss', str(timestamp),
                            '-i', local_path,
                            '-vframes', '1',
                            '-q:v', '2',  # High quality JPEG
                            '-y', tmp_path
                        ],
                        capture_output=True,
                        timeout=30
                    )

                    if result.returncode != 0:
                        print(f"[QA] Warning: ffmpeg frame extraction failed: {result.stderr.decode()[:200]}")
                        continue

                    # Read and encode as base64
                    with open(tmp_path, 'rb') as f:
                        frame_data = base64.b64encode(f.read()).decode('utf-8')

                    frames.append({
                        "data": frame_data,
                        "media_type": "image/jpeg"
                    })
                finally:
                    # Clean up temp frame file
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            if not frames:
                raise RuntimeError("Failed to extract any frames from video")

            return frames

        finally:
            # Clean up downloaded video
            if cleanup_after and os.path.exists(local_path):
                os.unlink(local_path)

    async def _download_video(self, url: str) -> str:
        """Download video from URL to temp file"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Create temp file with appropriate extension
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix or '.mp4'

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(response.content)
                return tmp.name

    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe"""
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ],
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            # Default to 5 seconds if we can't determine duration
            print(f"[QA] Warning: Could not determine video duration, defaulting to 5s")
            return 5.0

        try:
            return float(result.stdout.decode().strip())
        except ValueError:
            return 5.0

    async def _analyze_with_vision(
        self,
        scene: Scene,
        frames: List[Dict[str, str]],
        original_request: str,
        production_tier: ProductionTier
    ) -> Dict[str, Any]:
        """
        Analyze video frames using Claude Vision API

        Args:
            scene: Scene specification
            frames: List of dicts with 'data' (base64) and 'media_type' keys
            original_request: High-level video concept
            production_tier: Expected quality tier

        Returns:
            Dictionary with scores and feedback
        """

        prompt = f"""You are a video QA specialist evaluating AI-generated video content.

SCENE SPECIFICATION:
- Title: {scene.title}
- Description: {scene.description}
- Visual Elements: {', '.join(scene.visual_elements)}
- Duration: {scene.duration}s
- Style: {production_tier.value}

ORIGINAL REQUEST CONTEXT:
{original_request}

I'm showing you {len(frames)} frames from the generated video (extracted at evenly-spaced intervals from start to end).

Evaluate the video on these criteria:

1. **Visual Accuracy** (0-100): Do the visuals match the scene description?
   - Are the specified visual elements present?
   - Is the composition appropriate for the description?
   - Does it capture the intended mood/atmosphere?

2. **Style Consistency** (0-100): Does it match the expected production tier?
   - For {production_tier.value}: Does it meet that quality level?
   - Is the aesthetic consistent across frames?
   - Does it look like professional {production_tier.value} content?

3. **Technical Quality** (0-100): Any artifacts, blur, or rendering issues?
   - Resolution and clarity of the frames
   - Any visual glitches, artifacts, or distortions
   - Color consistency and lighting quality

4. **Narrative Fit** (0-100): Does this scene work in the overall story?
   - Does it fit the tone of the original request?
   - Would it work well in context?

Be honest and critical. AI video generation often has issues - call them out.
Common issues to look for: morphing/warping, unnatural motion blur, inconsistent objects between frames, text/writing problems.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "overall_score": 85,
  "visual_accuracy": 88,
  "style_consistency": 82,
  "technical_quality": 85,
  "narrative_fit": 85,
  "issues": ["Specific issue 1", "Specific issue 2"],
  "suggestions": ["Actionable improvement 1", "Actionable improvement 2"]
}}"""

        # Use Claude's vision API with the extracted frames
        if self.use_vision and frames:
            response = await self.claude.query_with_images(prompt, frames)
        else:
            # Fallback to text-only (won't have frame context)
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
