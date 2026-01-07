"""Test the Producer agent"""
import asyncio
import os
from dotenv import load_dotenv
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.claude_client import ClaudeClient
from agents.producer import ProducerAgent


async def main():
    load_dotenv()
    
    print("="*60)
    print("TESTING PRODUCER AGENT")
    print("="*60)
    print()
    
    # Create shared Claude client
    claude = ClaudeClient(debug=False)  # Set to True for debugging
    
    # Create producer
    producer = ProducerAgent(claude_client=claude)
    
    # Test request
    request = """
    Create a 60-second video: "A day in the life of a software developer
    using AI tools". Show: morning standup, coding with AI assistant, 
    code review, debugging with AI help, deploying to production, celebration.
    """
    
    budget = 150.00
    
    print("REQUEST:")
    print(request.strip())
    print()
    print(f"BUDGET: ${budget}")
    print()
    print("Analyzing and creating pilot strategies...")
    print()
    
    try:
        pilots = await producer.analyze_and_plan(request, budget)
        
        print(f"✓ Created {len(pilots)} pilot strategies:")
        print()
        
        for pilot in pilots:
            est_cost = producer.estimate_pilot_cost(pilot, num_variations=3)
            print(f"  {pilot.pilot_id.upper()}")
            print(f"    Tier: {pilot.tier.value}")
            print(f"    Rationale: {pilot.rationale}")
            print(f"    Budget: ${pilot.allocated_budget}")
            print(f"    Test scenes: {pilot.test_scene_count}")
            print(f"    Est. test cost: ~${est_cost}")
            print()
        
        print("="*60)
        print("SUCCESS! Producer agent working.")
        print("="*60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
