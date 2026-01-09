#!/usr/bin/env python3
"""
Test script to run QA vision evaluation on an existing video.
This tests the real frame extraction and Claude vision analysis without generating new videos.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from agents.qa_verifier import QAVerifierAgent
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from core.budget import ProductionTier
from core.claude_client import ClaudeClient


async def main():
    # Find a video to test with
    run_id = "20260108_230859"  # Latest run with video
    video_path = Path(f"artifacts/runs/{run_id}/videos/scene_1_v0.mp4")

    if not video_path.exists():
        print(f"Video not found: {video_path}")
        print("Available runs:")
        runs_dir = Path("artifacts/runs")
        for run_dir in sorted(runs_dir.iterdir(), reverse=True)[:5]:
            videos = list((run_dir / "videos").glob("*.mp4")) if (run_dir / "videos").exists() else []
            if videos:
                print(f"  {run_dir.name}: {len(videos)} videos")
        return

    print(f"Testing QA Vision on: {video_path}")
    print("=" * 60)

    # Create a mock scene for testing
    scene = Scene(
        scene_id="scene_1",
        title="Product Demo Introduction",
        description="A sleek smartphone rotating slowly on a reflective surface with soft ambient lighting",
        duration=5.0,
        visual_elements=["smartphone", "reflective surface", "ambient lighting", "slow rotation"],
        audio_notes="Soft ambient music",
        transition_in="fade",
        transition_out="cut",
        prompt_hints=["product shot", "cinematic", "soft lighting"]
    )

    # Create mock generated video pointing to real file
    video = GeneratedVideo(
        scene_id="scene_1",
        variation_id=0,
        video_url=str(video_path.absolute()),
        thumbnail_url="",
        duration=5.0,
        generation_cost=0.50,
        provider="luma",
        metadata={},
        quality_score=None  # Will be determined by QA
    )

    original_request = "Create a product demo video showcasing a mobile app"

    # Initialize QA Verifier in LIVE mode (mock_mode=False)
    claude = ClaudeClient(debug=True)
    qa_verifier = QAVerifierAgent(
        claude_client=claude,
        mock_mode=False,  # Use real vision analysis
        num_frames=3,
        use_vision=True
    )

    print("\n[1] Extracting frames from video...")
    try:
        frames = await qa_verifier._extract_frames(str(video_path.absolute()))
        print(f"    Extracted {len(frames)} frames")
        for i, frame in enumerate(frames):
            print(f"    Frame {i+1}: {len(frame['data'])} bytes base64, type={frame['media_type']}")
    except Exception as e:
        print(f"    ERROR extracting frames: {e}")
        return

    print("\n[2] Running vision analysis with Claude...")
    try:
        result = await qa_verifier.verify_video(
            scene=scene,
            generated_video=video,
            original_request=original_request,
            production_tier=ProductionTier.ANIMATED
        )

        print("\n" + "=" * 60)
        print("QA RESULT")
        print("=" * 60)
        print(f"Overall Score: {result.overall_score}/100 {'PASSED' if result.passed else 'FAILED'}")
        print(f"Threshold: {result.threshold}")
        print()
        print("Detailed Scores:")
        print(f"  Visual Accuracy:   {result.visual_accuracy}/100")
        print(f"  Style Consistency: {result.style_consistency}/100")
        print(f"  Technical Quality: {result.technical_quality}/100")
        print(f"  Narrative Fit:     {result.narrative_fit}/100")
        print()
        print("Issues Found:")
        for issue in result.issues:
            print(f"  - {issue}")
        print()
        print("Suggestions:")
        for suggestion in result.suggestions:
            print(f"  - {suggestion}")
        print("=" * 60)

    except Exception as e:
        print(f"    ERROR during QA: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
