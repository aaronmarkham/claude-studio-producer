"""Test the Critic agent"""
import asyncio
import os
from dotenv import load_dotenv
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.claude_client import ClaudeClient
from core.producer import ProducerAgent, PilotStrategy
from core.critic import CriticAgent, SceneResult
from core.budget import ProductionTier


async def main():
    load_dotenv()
    
    print("="*60)
    print("TESTING CRITIC AGENT")
    print("="*60)
    print()
    
    # Create shared Claude client
    claude = ClaudeClient(debug=False)
    
    # Create critic
    critic = CriticAgent(claude_client=claude)
    
    # Simulate a pilot strategy
    pilot = PilotStrategy(
        pilot_id="pilot_a",
        tier=ProductionTier.MOTION_GRAPHICS,
        allocated_budget=50.0,
        test_scene_count=3,
        full_scene_count=12,
        rationale="Cost-effective baseline"
    )
    
    # Original request
    request = """
    Create a 60-second video: "A day in the life of a software developer
    using AI tools". Show: morning standup, coding with AI assistant, 
    code review, debugging with AI help, deploying to production, celebration.
    """
    
    # Simulate some test scene results
    # In real usage, these would come from actual video generation
    test_scenes = [
        SceneResult(
            scene_id="scene_1",
            description="Developer at morning standup meeting, discussing sprint goals",
            video_url="https://example.com/scene1.mp4",
            qa_score=82.0,
            generation_cost=3.50
        ),
        SceneResult(
            scene_id="scene_2",
            description="Developer coding with AI assistant, showing code suggestions",
            video_url="https://example.com/scene2.mp4",
            qa_score=75.0,
            generation_cost=3.50
        ),
        SceneResult(
            scene_id="scene_3",
            description="Developer reviewing pull request with AI-powered analysis",
            video_url="https://example.com/scene3.mp4",
            qa_score=88.0,
            generation_cost=3.50
        ),
    ]
    
    budget_spent = sum(s.generation_cost for s in test_scenes)
    
    print("PILOT UNDER EVALUATION:")
    print(f"  ID: {pilot.pilot_id}")
    print(f"  Tier: {pilot.tier.value}")
    print(f"  Budget allocated: ${pilot.allocated_budget}")
    print(f"  Budget spent: ${budget_spent}")
    print()
    
    print("TEST SCENES GENERATED:")
    for scene in test_scenes:
        print(f"  • {scene.scene_id}: {scene.description[:50]}...")
        print(f"    QA Score: {scene.qa_score}/100")
    print()
    
    print("Critic evaluating pilot...")
    print()
    
    try:
        result = await critic.evaluate_pilot(
            original_request=request,
            pilot=pilot,
            scene_results=test_scenes,
            budget_spent=budget_spent,
            budget_allocated=pilot.allocated_budget
        )
        
        # Display results
        print("="*60)
        print("CRITIC EVALUATION")
        print("="*60)
        print()
        
        status = "✅ APPROVED" if result.approved else "❌ CANCELLED"
        print(f"Decision: {status}")
        print()
        print(f"Critic Score: {result.critic_score}/100")
        print(f"Avg QA Score: {result.avg_qa_score:.1f}/100")
        print()
        print("Gap Analysis:")
        print(f"  Matched: {', '.join(result.gap_analysis['matched_elements'])}")
        print(f"  Missing: {', '.join(result.gap_analysis['missing_elements'])}")
        if result.gap_analysis['quality_issues']:
            print(f"  Issues: {', '.join(result.gap_analysis['quality_issues'])}")
        print()
        print(f"Reasoning: {result.critic_reasoning}")
        print()
        
        if result.approved:
            print(f"✓ Continue with ${result.budget_remaining:.2f} budget")
            if result.adjustments_needed:
                print(f"  Adjustments needed:")
                for adj in result.adjustments_needed:
                    print(f"    - {adj}")
        else:
            print("✗ Pilot cancelled - budget will be reallocated")
        
        print()
        print("="*60)
        print("SUCCESS! Critic agent working.")
        print("="*60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
