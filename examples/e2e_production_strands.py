"""
End-to-end production pipeline with Strands Orchestrator

Runs the full video production pipeline using the new StudioOrchestrator
which coordinates all Strands-enabled agents in parallel.

Usage:
    python examples/e2e_production_strands.py --mock
    python examples/e2e_production_strands.py --live --budget 15 --concept "Product demo for a todo app"
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows import StudioOrchestrator, ProductionResult
from core.models.audio import AudioTier


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run end-to-end video production pipeline with Strands orchestrator"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock providers (default)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live API providers (Runway + OpenAI TTS)"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=20.0,
        help="Total budget in USD (default: 20.0)"
    )
    parser.add_argument(
        "--concept",
        type=str,
        default="A 30-second video about a developer building an AI app",
        help="Video concept description"
    )
    parser.add_argument(
        "--num-variations",
        type=int,
        default=2,
        help="Number of video variations per scene (default: 2)"
    )
    parser.add_argument(
        "--max-concurrent-pilots",
        type=int,
        default=2,
        help="Maximum number of pilots to run in parallel (default: 2)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )

    args = parser.parse_args()

    # Determine mode
    use_live = args.live
    if not args.mock and not args.live:
        use_live = False  # Default to mock

    # Create run directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("artifacts/runs") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Setup metadata
    metadata = {
        "run_id": run_id,
        "concept": args.concept,
        "budget": args.budget,
        "use_live_providers": use_live,
        "num_variations": args.num_variations,
        "max_concurrent_pilots": args.max_concurrent_pilots,
        "start_time": datetime.now().isoformat(),
    }

    print("\n" + "="*70)
    print("CLAUDE STUDIO PRODUCER - STRANDS ORCHESTRATOR")
    print("="*70)
    print(f"\nRun ID: {run_id}")
    print(f"Concept: {args.concept}")
    print(f"Budget: ${args.budget:.2f}")
    print(f"Mode: {'LIVE' if use_live else 'MOCK'}")
    print(f"Variations per scene: {args.num_variations}")
    print(f"Max concurrent pilots: {args.max_concurrent_pilots}")
    print()

    # Create orchestrator
    orchestrator = StudioOrchestrator(
        num_variations=args.num_variations,
        max_concurrent_pilots=args.max_concurrent_pilots,
        debug=args.debug
    )

    try:
        # Run the full production pipeline
        start_time = datetime.now()

        result: ProductionResult = await orchestrator.run(
            user_request=args.concept,
            total_budget=args.budget
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Update metadata
        metadata["end_time"] = end_time.isoformat()
        metadata["duration_seconds"] = duration
        metadata["status"] = result.status
        metadata["budget_used"] = result.budget_used
        metadata["budget_remaining"] = result.budget_remaining
        metadata["total_scenes"] = result.total_scenes
        metadata["num_pilots_evaluated"] = len(result.all_pilots)

        if result.best_pilot:
            metadata["best_pilot"] = {
                "pilot_id": result.best_pilot.pilot_id,
                "tier": result.best_pilot.tier,
                "critic_score": result.best_pilot.critic_score,
                "avg_qa_score": result.best_pilot.avg_qa_score,
                "total_cost": result.best_pilot.total_cost,
                "approved": result.best_pilot.approved
            }

        # Save metadata
        metadata_path = run_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Print summary
        print("\n" + "="*70)
        if result.status == "success":
            print("PRODUCTION COMPLETE - SUCCESS")
        else:
            print("PRODUCTION FAILED")
        print("="*70)

        print(f"\nRun ID: {run_id}")
        print(f"Duration: {duration:.1f}s")
        print(f"Status: {result.status}")

        print(f"\nBudget:")
        print(f"  - Total: ${args.budget:.2f}")
        print(f"  - Used: ${result.budget_used:.2f}")
        print(f"  - Remaining: ${result.budget_remaining:.2f}")
        print(f"  - Utilization: {100*result.budget_used/args.budget:.1f}%")

        print(f"\nPilots Evaluated: {len(result.all_pilots)}")
        for pilot_result in result.all_pilots:
            status = "[OK] APPROVED" if pilot_result.approved else "[X] REJECTED"
            print(f"  - {pilot_result.pilot_id} ({pilot_result.tier}): {status}")
            print(f"    Critic: {pilot_result.critic_score}/100, QA: {pilot_result.avg_qa_score:.1f}/100")
            print(f"    Cost: ${pilot_result.total_cost:.2f}, Scenes: {len(pilot_result.scenes_generated)}")

        if result.best_pilot:
            print(f"\n[WINNER] Best Pilot: {result.best_pilot.pilot_id}")
            print(f"   Tier: {result.best_pilot.tier}")
            print(f"   Critic Score: {result.best_pilot.critic_score}/100")
            print(f"   Avg QA Score: {result.best_pilot.avg_qa_score:.1f}/100")
            print(f"   Scenes: {result.total_scenes}")
            print(f"   Cost: ${result.best_pilot.total_cost:.2f}")

        print(f"\nArtifacts saved to: {run_dir}")
        print("="*70 + "\n")

        sys.exit(0 if result.status == "success" else 1)

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed with exception: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()

        # Save error metadata
        metadata["end_time"] = datetime.now().isoformat()
        metadata["status"] = "error"
        metadata["error"] = str(e)

        metadata_path = run_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
