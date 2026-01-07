"""Test the QAVerifierAgent"""

import asyncio
import os
from dotenv import load_dotenv
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.qa_verifier import QAVerifierAgent, QAResult, QA_THRESHOLDS
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from core.budget import ProductionTier


async def main():
    load_dotenv()

    print("\n" + "="*60)
    print("QA VERIFIER AGENT TEST")
    print("="*60)

    # Create test scene
    test_scene = Scene(
        scene_id="scene_1",
        title="Morning Standup",
        description="Developer joins video call with team for morning standup meeting",
        duration=5.0,
        visual_elements=["laptop screen", "video call grid", "coffee cup", "morning light"],
        audio_notes="Upbeat background music, muted conversation",
        transition_in="fade_in",
        transition_out="cut",
        prompt_hints=["professional office setting", "natural morning lighting", "focused developer"]
    )

    # Create test video
    test_video = GeneratedVideo(
        scene_id="scene_1",
        variation_id=0,
        video_url="https://mock-cdn.example.com/scene_1_v0.mp4",
        thumbnail_url="https://mock-cdn.example.com/scene_1_v0_thumb.jpg",
        duration=5.0,
        generation_cost=1.25,
        provider="pika",
        metadata={
            "prompt": "Developer joins video call with team, laptop screen, video call grid, coffee cup",
            "tier": "animated",
            "model": "pika_latest"
        }
    )

    original_request = "Create a 60-second video: 'A day in the life of a developer using AI tools'"

    # Test 1: Verify single video
    print("\n" + "="*60)
    print("TEST 1: Single Video Verification")
    print("="*60)

    qa = QAVerifierAgent(mock_mode=True)

    result = await qa.verify_video(
        scene=test_scene,
        generated_video=test_video,
        original_request=original_request,
        production_tier=ProductionTier.ANIMATED
    )

    print(f"\nScene: {result.scene_id}")
    print(f"Overall Score: {result.overall_score}/100")
    print(f"Threshold: {result.threshold}")
    print(f"Status: {'PASSED' if result.passed else 'FAILED'}")
    print(f"\nDetailed Scores:")
    print(f"  Visual Accuracy:   {result.visual_accuracy}/100")
    print(f"  Style Consistency: {result.style_consistency}/100")
    print(f"  Technical Quality: {result.technical_quality}/100")
    print(f"  Narrative Fit:     {result.narrative_fit}/100")
    print(f"\nIssues Found:")
    for issue in result.issues:
        print(f"  - {issue}")
    print(f"\nSuggestions:")
    for suggestion in result.suggestions:
        print(f"  - {suggestion}")

    quality_gate = qa.get_quality_gate(result.overall_score)
    print(f"\nQuality Gate: {quality_gate.upper()}")

    # Test 2: Different production tiers
    print("\n" + "="*60)
    print("TEST 2: Different Production Tiers")
    print("="*60)

    tiers = [
        ProductionTier.STATIC_IMAGES,
        ProductionTier.MOTION_GRAPHICS,
        ProductionTier.ANIMATED,
        ProductionTier.PHOTOREALISTIC
    ]

    for tier in tiers:
        result = await qa.verify_video(
            scene=test_scene,
            generated_video=test_video,
            original_request=original_request,
            production_tier=tier
        )

        status = "PASS" if result.passed else "FAIL"
        print(f"\n{tier.value.upper()}")
        print(f"  Score: {result.overall_score}/100")
        print(f"  Threshold: {result.threshold}")
        print(f"  Status: {status}")
        print(f"  Quality Gate: {qa.get_quality_gate(result.overall_score)}")

    # Test 3: Batch verification
    print("\n" + "="*60)
    print("TEST 3: Batch Verification")
    print("="*60)

    # Create multiple test videos
    scenes = []
    videos = []

    for i in range(3):
        scenes.append(Scene(
            scene_id=f"scene_{i+1}",
            title=f"Test Scene {i+1}",
            description=f"Test description for scene {i+1}",
            duration=5.0,
            visual_elements=["element1", "element2"],
            audio_notes="ambient",
            transition_in="fade_in",
            transition_out="cut",
            prompt_hints=["hint1"]
        ))

        videos.append(GeneratedVideo(
            scene_id=f"scene_{i+1}",
            variation_id=0,
            video_url=f"https://mock-cdn.example.com/scene_{i+1}.mp4",
            thumbnail_url=f"https://mock-cdn.example.com/scene_{i+1}_thumb.jpg",
            duration=5.0,
            generation_cost=1.25,
            provider="pika",
            metadata={}
        ))

    print(f"\nVerifying {len(videos)} videos in parallel...")

    results = await qa.verify_batch(
        scenes=scenes,
        videos=videos,
        original_request=original_request,
        production_tier=ProductionTier.ANIMATED
    )

    print(f"\nResults:")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"  {result.scene_id}: {result.overall_score}/100 [{status}]")

    # Calculate average
    avg_score = sum(r.overall_score for r in results) / len(results)
    pass_rate = sum(1 for r in results if r.passed) / len(results) * 100
    print(f"\nAverage Score: {avg_score:.1f}/100")
    print(f"Pass Rate: {pass_rate:.0f}%")

    # Test 4: Regeneration decision logic
    print("\n" + "="*60)
    print("TEST 4: Regeneration Decision Logic")
    print("="*60)

    test_cases = [
        (45.0, 10.0, 5.0, "Hard fail - should regenerate"),
        (65.0, 10.0, 5.0, "Soft fail - may regenerate"),
        (85.0, 20.0, 5.0, "Pass - regenerate only with ample budget"),
        (92.0, 50.0, 5.0, "Excellent - no need to regenerate"),
    ]

    for score, budget, cost, description in test_cases:
        mock_result = QAResult(
            scene_id="test",
            video_url="test.mp4",
            overall_score=score,
            visual_accuracy=score,
            style_consistency=score,
            technical_quality=score,
            narrative_fit=score,
            issues=[],
            suggestions=[],
            passed=score >= 80,
            threshold=80
        )

        should_regen = qa.should_regenerate(mock_result, budget, cost)
        decision = "YES" if should_regen else "NO"

        print(f"\n{description}")
        print(f"  Score: {score}/100, Budget: ${budget}, Cost: ${cost}")
        print(f"  Regenerate: {decision}")

    # Test 5: Testing the skill interface
    print("\n" + "="*60)
    print("TEST 5: Skill Interface")
    print("="*60)

    from skills.scene_analysis.verify_quality import verify_quality

    scene_dict = {
        "scene_id": "scene_skill",
        "title": "Skill Test",
        "description": "Testing skill interface",
        "duration": 5.0,
        "visual_elements": ["test"],
        "audio_notes": "ambient",
        "transition_in": "fade_in",
        "transition_out": "fade_out",
        "prompt_hints": ["test"]
    }

    video_dict = {
        "scene_id": "scene_skill",
        "variation_id": 0,
        "video_url": "https://example.com/test.mp4",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration": 5.0,
        "generation_cost": 1.25,
        "provider": "pika",
        "metadata": {}
    }

    skill_result = await verify_quality(
        scene_data=scene_dict,
        video_data=video_dict,
        original_request="Test request",
        production_tier="animated",
        mock_mode=True
    )

    print(f"\nSkill Result:")
    print(f"  Score: {skill_result['overall_score']}/100")
    print(f"  Passed: {skill_result['passed']}")
    print(f"  Quality Gate: {skill_result['quality_gate']}")
    print(f"  Issues: {len(skill_result['issues'])}")

    print("\n" + "="*60)
    print("All tests complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
