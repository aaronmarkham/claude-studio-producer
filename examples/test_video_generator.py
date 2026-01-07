"""Test the VideoGeneratorAgent"""

import asyncio
import os
from dotenv import load_dotenv
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.video_generator import VideoGeneratorAgent, VideoProvider
from agents.script_writer import Scene
from core.budget import ProductionTier


async def main():
    load_dotenv()

    print("\n" + "="*60)
    print("VIDEO GENERATOR AGENT TEST")
    print("="*60)

    # Create a test scene
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

    print("\n📹 Test Scene:")
    print(f"   {test_scene.scene_id}: {test_scene.title}")
    print(f"   Duration: {test_scene.duration}s")
    print(f"   Description: {test_scene.description}")

    # Test 1: Generate with ANIMATED tier
    print("\n" + "="*60)
    print("TEST 1: Generate Animated Video (Mock Mode)")
    print("="*60)

    generator = VideoGeneratorAgent(
        num_variations=3,
        mock_mode=True  # Using mock mode since we don't have real API keys
    )

    videos = await generator.generate_scene(
        scene=test_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=10.00
    )

    print(f"\n✅ Generated {len(videos)} variations")
    total_cost = sum(v.generation_cost for v in videos)
    print(f"💰 Total cost: ${total_cost:.2f}")

    for video in videos:
        print(f"\n   Variation {video.variation_id}:")
        print(f"   • URL: {video.video_url}")
        print(f"   • Provider: {video.provider}")
        print(f"   • Duration: {video.duration}s")
        print(f"   • Cost: ${video.generation_cost:.2f}")
        print(f"   • Prompt: {video.metadata['prompt'][:100]}...")

    # Test 2: Different production tiers
    print("\n" + "="*60)
    print("TEST 2: Different Production Tiers")
    print("="*60)

    tiers_to_test = [
        (ProductionTier.STATIC_IMAGES, 15.00),
        (ProductionTier.MOTION_GRAPHICS, 15.00),
        (ProductionTier.PHOTOREALISTIC, 15.00),
    ]

    for tier, budget in tiers_to_test:
        print(f"\n🎬 Testing {tier.value.upper()} tier...")

        generator = VideoGeneratorAgent(num_variations=2, mock_mode=True)

        videos = await generator.generate_scene(
            scene=test_scene,
            production_tier=tier,
            budget_limit=budget
        )

        total_cost = sum(v.generation_cost for v in videos)
        print(f"   Generated: {len(videos)} variations")
        print(f"   Cost: ${total_cost:.2f} / ${budget:.2f}")
        print(f"   Provider: {videos[0].provider if videos else 'N/A'}")

    # Test 3: Budget constraints
    print("\n" + "="*60)
    print("TEST 3: Budget Constraints")
    print("="*60)

    print("\n⚠️  Testing with limited budget (should stop early)...")

    generator = VideoGeneratorAgent(num_variations=5, mock_mode=True)

    # Request 5 variations but only provide budget for ~2
    videos = await generator.generate_scene(
        scene=test_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=2.50  # Only enough for 2 variations at $1.25 each
    )

    print(f"\n   Requested: 5 variations")
    print(f"   Generated: {len(videos)} variations (budget limited)")
    total_cost = sum(v.generation_cost for v in videos)
    print(f"   Total cost: ${total_cost:.2f} / $2.50")

    # Test 4: Prompt building
    print("\n" + "="*60)
    print("TEST 4: Prompt Building")
    print("="*60)

    scene_with_hints = Scene(
        scene_id="scene_2",
        title="Coding Session",
        description="Developer writing code with AI pair programming assistant",
        duration=6.0,
        visual_elements=["IDE", "code suggestions", "cursor movement"],
        audio_notes="Keyboard typing, soft electronic music",
        transition_in="dissolve",
        transition_out="fade_out",
        prompt_hints=[
            "screen glow on face",
            "dynamic code completion",
            "focused concentration",
            "modern tech aesthetic"
        ]
    )

    generator = VideoGeneratorAgent(num_variations=1, mock_mode=True)

    videos = await generator.generate_scene(
        scene=scene_with_hints,
        production_tier=ProductionTier.PHOTOREALISTIC,
        budget_limit=5.00
    )

    print("\n📝 Generated Prompt:")
    print(f"   {videos[0].metadata['prompt']}")

    # Test 5: Testing the skill interface
    print("\n" + "="*60)
    print("TEST 5: Skill Interface")
    print("="*60)

    # Import and test the skill
    from skills.video_generation.generate_video import generate_video

    scene_dict = {
        "scene_id": "scene_skill_test",
        "title": "Skill Test Scene",
        "description": "Testing the skill interface",
        "duration": 4.0,
        "visual_elements": ["test", "interface"],
        "audio_notes": "ambient",
        "transition_in": "fade_in",
        "transition_out": "fade_out",
        "prompt_hints": ["test prompt"]
    }

    result = await generate_video(
        scene_data=scene_dict,
        production_tier="animated",
        budget_limit=5.0,
        num_variations=2,
        mock_mode=True
    )

    print(f"\n✅ Skill generated {result['variations_generated']} videos")
    print(f"💰 Total cost: ${result['total_cost']:.2f}")
    print(f"💵 Budget remaining: ${result['budget_remaining']:.2f}")

    print("\n" + "="*60)
    print("✅ All tests complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
