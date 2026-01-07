"""Cost estimation tool for video production"""
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.budget import COST_MODELS, ProductionTier, estimate_realistic_cost


def main():
    print("\n" + "="*70)
    print("CLAUDE STUDIO PRODUCER - COST ESTIMATOR")
    print("="*70)
    
    # Example project
    num_scenes = 12
    duration_per_scene = 5
    num_variations = 3
    
    print(f"\nProject Specs:")
    print(f"  Scenes: {num_scenes}")
    print(f"  Duration per scene: {duration_per_scene}s")
    print(f"  Variations per scene: {num_variations}")
    print(f"  Total video length: ~{num_scenes * duration_per_scene}s")
    
    print("\n" + "-"*70)
    print("COST ESTIMATES BY TIER")
    print("-"*70)
    
    for tier in ProductionTier:
        model = COST_MODELS[tier]
        costs = estimate_realistic_cost(
            tier=tier,
            num_scenes=num_scenes,
            num_variations=num_variations,
            avg_scene_duration=duration_per_scene
        )
        
        print(f"\n{tier.value.upper()}")
        print(f"  Provider examples: {model.provider_examples}")
        print(f"  Video generation:  ${costs['video_generation']:6.2f}")
        print(f"  Claude API costs:  ${costs['claude_api']:6.2f}")
        print(f"  Failure buffer:    ${costs['failure_buffer']:6.2f}")
        print(f"  ---")
        print(f"  TOTAL:            ${costs['total']:6.2f}")
        print(f"  Per scene:        ${costs['cost_per_scene']:6.2f}")
    
    print("\n" + "="*70)
    print("\nRECOMMENDATIONS:")
    print("  • Budget < $50:  Use static_images tier")
    print("  • Budget $50-150: Use motion_graphics tier")
    print("  • Budget $150-300: Use animated tier")
    print("  • Budget > $300:  Use photorealistic tier")
    print("\n  • Always run 2-3 pilots to compare quality/cost tradeoffs")
    print("  • Test with 3-4 scenes first before committing full budget")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
