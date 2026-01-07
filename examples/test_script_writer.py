"""Test the ScriptWriterAgent"""

import asyncio
import os
from dotenv import load_dotenv
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.script_writer import ScriptWriterAgent
from core.budget import ProductionTier
from core.claude_client import ClaudeClient


async def main():
    load_dotenv()

    print("\n" + "="*60)
    print("SCRIPT WRITER AGENT TEST")
    print("="*60)

    # Create shared Claude client
    claude = ClaudeClient(debug=False)

    # Create the agent
    writer = ScriptWriterAgent(claude_client=claude)

    # Test case: Developer using AI tools
    video_concept = """
    Create a 60-second video: 'A day in the life of a developer using AI tools'.
    Show: morning standup, coding with AI pair programming, debugging with AI help,
    reviewing pull requests, deploying to production, celebrating success.
    """

    print("\n📝 Generating script for concept:")
    print(video_concept.strip())
    print("\nTarget Duration: 60 seconds")
    print("Production Tier: ANIMATED")

    # Generate the script
    scenes = await writer.create_script(
        video_concept=video_concept,
        target_duration=60,
        production_tier=ProductionTier.ANIMATED,
        num_scenes=12  # ~5 seconds per scene
    )

    # Display results
    writer.print_script_summary(scenes)

    # Show some detailed examples
    print("\n" + "="*60)
    print("DETAILED SCENE EXAMPLES")
    print("="*60)

    for scene in scenes[:3]:  # Show first 3 scenes in detail
        print(f"\n🎬 {scene.title}")
        print(f"   ID: {scene.scene_id}")
        print(f"   Duration: {scene.duration}s")
        print(f"\n   Description:")
        print(f"   {scene.description}")
        print(f"\n   Visual Elements:")
        for element in scene.visual_elements:
            print(f"   • {element}")
        print(f"\n   Audio: {scene.audio_notes}")
        print(f"   Transitions: {scene.transition_in} → {scene.transition_out}")
        print(f"\n   Prompt Hints for Video Generation:")
        for hint in scene.prompt_hints:
            print(f"   → {hint}")

    # Test with different production tier
    print("\n\n" + "="*60)
    print("TESTING DIFFERENT PRODUCTION TIER")
    print("="*60)

    print("\n📝 Same concept but with PHOTOREALISTIC tier:")

    photorealistic_scenes = await writer.create_script(
        video_concept=video_concept,
        target_duration=60,
        production_tier=ProductionTier.PHOTOREALISTIC,
        num_scenes=10  # Slightly longer scenes for photorealistic
    )

    print(f"\nGenerated {len(photorealistic_scenes)} scenes")
    print(f"Total duration: {writer.get_total_duration(photorealistic_scenes):.1f}s")

    print("\nFirst scene (photorealistic tier):")
    scene = photorealistic_scenes[0]
    print(f"   {scene.title}")
    print(f"   {scene.description}")
    print(f"   Prompt hints: {', '.join(scene.prompt_hints)}")

    print("\n✅ Script Writer Agent test complete!\n")


if __name__ == "__main__":
    asyncio.run(main())
