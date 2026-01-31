---
layout: default
title: Producer Agent Specification
---
# Producer Agent Specification

## Purpose

The Producer Agent analyzes video requests and budgets to create competitive pilot strategies across different production tiers. It acts as the initial planner that sets up the multi-pilot competition.

## Inputs

- `user_request`: High-level video concept description
- `total_budget`: Total available budget in USD

## Outputs

```python
@dataclass
class PilotStrategy:
    pilot_id: str           # "pilot_a", "pilot_b", etc.
    tier: ProductionTier    # static_images, motion_graphics, animated, photorealistic
    allocated_budget: float # Budget for this pilot
    test_scene_count: int   # Scenes to generate in test phase (2-4)
    full_scene_count: int   # Total scenes if approved
    rationale: str          # Why this tier was chosen
```

## Behavior

1. Analyze the video request for complexity and requirements
2. Determine which production tiers are viable for the budget
3. Create 2-3 competitive pilot strategies
4. Allocate budget across pilots (they'll compete)
5. Set test scene counts for initial evaluation

## Decision Logic

### Tier Selection Based on Budget

```python
def select_viable_tiers(budget: float, duration: int) -> List[ProductionTier]:
    """Determine which tiers are affordable"""
    
    cost_per_minute = {
        ProductionTier.STATIC_IMAGES: 2.40,      # $0.04/sec
        ProductionTier.MOTION_GRAPHICS: 9.00,    # $0.15/sec
        ProductionTier.ANIMATED: 15.00,          # $0.25/sec
        ProductionTier.PHOTOREALISTIC: 30.00,    # $0.50/sec
    }
    
    viable = []
    for tier, cpm in cost_per_minute.items():
        estimated_cost = (duration / 60) * cpm * 1.5  # 1.5x for variations + overhead
        if estimated_cost <= budget * 0.8:  # Leave 20% buffer
            viable.append(tier)
    
    return viable
```

### Budget Allocation Strategy

```python
def allocate_budget(budget: float, num_pilots: int) -> List[float]:
    """Split budget across pilots"""
    
    # Not equal - give more to higher tiers
    if num_pilots == 2:
        return [budget * 0.45, budget * 0.55]
    elif num_pilots == 3:
        return [budget * 0.30, budget * 0.35, budget * 0.35]
    else:
        return [budget / num_pilots] * num_pilots
```

## Prompt Template

```
You are a video production planner.

REQUEST: {user_request}
BUDGET: ${total_budget}

Available production tiers:
- static_images: $0.04/sec - Slideshows (quality ceiling: 75/100)
- motion_graphics: $0.15/sec - Explainers, infographics (quality ceiling: 85/100)
- animated: $0.25/sec - Storytelling, characters (quality ceiling: 90/100)
- photorealistic: $0.50/sec - Highest quality video (quality ceiling: 95/100)

Create 2-3 pilot strategies with different tiers for competitive testing.
Each pilot gets initial budget and produces 2-4 test scenes first.
Assume ~60 second video = 10-15 scenes total.

Return ONLY valid JSON:
{
  "total_scenes_estimated": 12,
  "pilots": [
    {
      "pilot_id": "pilot_a",
      "tier": "motion_graphics",
      "rationale": "Cost-effective baseline with good quality",
      "allocated_budget": 60.0,
      "test_scene_count": 3
    }
  ]
}
```

## Integration

- Called by: `StudioOrchestrator` at pipeline start
- Calls: None (uses Claude directly)
- Output used by: All subsequent pipeline stages

## Example Usage

```python
from agents.producer import ProducerAgent
from core.claude_client import ClaudeClient

claude = ClaudeClient()
producer = ProducerAgent(claude_client=claude)

pilots = await producer.analyze_and_plan(
    user_request="A day in the life of a developer using AI",
    total_budget=150.00
)

for pilot in pilots:
    print(f"{pilot.pilot_id}: {pilot.tier.value}")
    print(f"  Budget: ${pilot.allocated_budget}")
    print(f"  Test scenes: {pilot.test_scene_count}")
    print(f"  Rationale: {pilot.rationale}")
```

## Cost Estimation

```python
def estimate_pilot_cost(
    pilot: PilotStrategy,
    num_variations: int = 3,
    avg_duration_per_scene: float = 5.0
) -> float:
    """Estimate cost for pilot's test phase"""
    
    cost_model = COST_MODELS[pilot.tier]
    
    video_cost = (
        pilot.test_scene_count *
        avg_duration_per_scene *
        num_variations *
        cost_model.cost_per_second
    )
    
    claude_cost = (
        cost_model.claude_tokens_estimate *
        pilot.test_scene_count *
        0.003 / 1000
    )
    
    return video_cost + claude_cost
```

## Edge Cases

1. **Budget too low**: Return single cheapest viable tier
2. **Budget very high**: Cap at 3 pilots, don't over-allocate
3. **Complex request**: Recommend higher tiers, fewer pilots
4. **Simple request**: Can use lower tiers, more pilots
