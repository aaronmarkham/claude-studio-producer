"""
Full production example - Complete pipeline
"""
import asyncio
import os
from dotenv import load_dotenv
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import StudioOrchestrator


async def main():
    load_dotenv()
    
    # Create orchestrator
    orchestrator = StudioOrchestrator(
        num_variations=3,
        debug=False  # Set True for verbose output
    )
    
    # Your video concept
    request = """
    Create a 60-second video: "A day in the life of a software developer
    using AI tools". 
    
    Show the complete workflow:
    - Morning standup meeting discussing sprint goals
    - Coding with AI assistant providing smart suggestions
    - Code review with AI-powered analysis
    - Debugging a tricky bug with AI help
    - Deploying to production with confidence
    - Team celebration after successful launch
    
    Style: Modern, professional, engaging. Should feel authentic to
    real developer experience.
    """
    
    budget = 150.00
    
    # Run full production
    result = await orchestrator.produce_video(
        user_request=request,
        total_budget=budget
    )
    
    # Display final results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(f"Status: {result.status}")
    
    if result.best_pilot:
        print(f"\nBest Pilot: {result.best_pilot.pilot_id}")
        print(f"  Tier: {result.best_pilot.tier}")
        print(f"  Quality Score: {result.best_pilot.critic_score}/100")
        print(f"  Avg QA Score: {result.best_pilot.avg_qa_score:.1f}/100")
        print(f"  Total Scenes: {len(result.best_pilot.scenes_generated)}")
        print(f"  Total Cost: ${result.best_pilot.total_cost:.2f}")
        
        print(f"\n  Critic's Reasoning:")
        print(f"  {result.best_pilot.critic_reasoning}")
    
    print(f"\nBudget Summary:")
    print(f"  Total Budget: ${budget:.2f}")
    print(f"  Used: ${result.budget_used:.2f}")
    print(f"  Remaining: ${result.budget_remaining:.2f}")
    
    print(f"\nAll Pilots Evaluated: {len(result.all_pilots)}")
    for pilot_result in result.all_pilots:
        status = "✅" if pilot_result.approved else "❌"
        print(f"  {status} {pilot_result.pilot_id}: {pilot_result.critic_score}/100")
    
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
