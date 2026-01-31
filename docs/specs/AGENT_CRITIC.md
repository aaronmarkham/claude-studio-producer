---
layout: default
title: Critic Agent Specification
---
# Critic Agent Specification

## Purpose

The Critic Agent evaluates pilot results against the original creative intent, performs gap analysis, and makes budget continuation/cancellation decisions. It's the quality gatekeeper that ensures only worthy pilots continue.

## Inputs

- `original_request`: The original video concept
- `pilot`: The pilot strategy being evaluated
- `scene_results`: List of generated scenes with QA scores
- `budget_spent`: Amount spent so far
- `budget_allocated`: Total budget for this pilot

## Outputs

```python
@dataclass
class PilotResults:
    pilot_id: str
    tier: str
    scenes_generated: List[SceneResult]
    total_cost: float
    avg_qa_score: float
    
    # Critic's evaluation
    critic_score: float          # 0-100 overall score
    approved: bool               # Continue or cancel?
    budget_remaining: float      # How much to continue with
    gap_analysis: Dict           # What matched/missed
    critic_reasoning: str        # Explanation of decision
    adjustments_needed: List[str] # Improvements for next phase
```

## Behavior

1. Analyze generated scenes against original request
2. Identify matched elements and gaps
3. Score overall quality (0-100)
4. Make continue/cancel decision
5. Recommend budget allocation for continuation
6. Suggest adjustments for next phase

## Scoring Rubric

| Score Range | Decision | Budget Multiplier |
|-------------|----------|-------------------|
| 90-100 | Excellent, continue | 100% remaining |
| 75-89 | Good, continue | 75% remaining |
| 65-74 | Acceptable, continue | 50% remaining |
| < 65 | Poor, CANCEL | 0% (reallocate) |

## Gap Analysis

```python
@dataclass
class GapAnalysis:
    matched_elements: List[str]   # What was captured well
    missing_elements: List[str]   # What's missing
    quality_issues: List[str]     # Technical problems
    style_notes: str              # Style consistency
```

## Prompt Template

```
You are a production critic evaluating test scenes from a video pilot.

ORIGINAL REQUEST:
{original_request}

PILOT DETAILS:
- ID: {pilot.pilot_id}
- Tier: {pilot.tier.value}
- Budget allocated: ${budget_allocated}
- Budget spent: ${budget_spent}
- Scenes produced: {len(scene_results)}

TEST SCENE RESULTS:
{formatted_scene_results}

AVERAGE QA SCORE: {avg_qa}/100

Perform gap analysis:
1. How well do these scenes match the creative intent?
2. What's missing or incorrectly interpreted?
3. Is the quality acceptable for this tier?
4. Should we continue this pilot with more budget?

SCORING RUBRIC:
- 90-100: Excellent match, continue with 100% remaining budget
- 75-89: Good match, continue with 75% remaining budget
- 65-74: Acceptable, continue with 50% remaining budget
- Below 65: Poor match, CANCEL pilot

Return JSON:
{
  "overall_score": 82,
  "gap_analysis": {
    "matched_elements": ["element1", "element2"],
    "missing_elements": ["element3"],
    "quality_issues": ["issue1"]
  },
  "decision": "continue",
  "budget_multiplier": 0.75,
  "reasoning": "Good execution but needs adjustment in X",
  "adjustments_needed": ["adjustment1", "adjustment2"]
}
```

## Integration

- Called by: `StudioOrchestrator` after pilot test phase
- Receives from: `QAVerifierAgent` (QA scores)
- Output used by: Orchestrator for budget decisions

## Example Usage

```python
from agents.critic import CriticAgent, SceneResult
from core.claude_client import ClaudeClient

claude = ClaudeClient()
critic = CriticAgent(claude_client=claude)

result = await critic.evaluate_pilot(
    original_request="A day in the life of a developer...",
    pilot=pilot_strategy,
    scene_results=test_scenes,
    budget_spent=15.00,
    budget_allocated=50.00
)

if result.approved:
    print(f"✅ Continue with ${result.budget_remaining}")
    print(f"Adjustments: {result.adjustments_needed}")
else:
    print(f"❌ Cancelled: {result.critic_reasoning}")
```

## Comparative Evaluation

When multiple pilots complete, the Critic can compare:

```python
def compare_pilots(results: List[PilotResults]) -> PilotResults:
    """Select the best pilot from approved candidates"""
    
    approved = [r for r in results if r.approved]
    
    if not approved:
        return None
    
    # Sort by critic score, then cost efficiency
    best = max(approved, key=lambda r: (
        r.critic_score,
        r.avg_qa_score / r.total_cost  # Quality per dollar
    ))
    
    return best
```

## Feedback Loop

The Critic's adjustments feed back into production:

```python
# Critic identifies issues
adjustments = [
    "Improve lighting in office scenes",
    "Add more dynamic camera movement",
    "Include developer's face in coding shots"
]

# These are passed to VideoGenerator for remaining scenes
for scene in remaining_scenes:
    scene.prompt_hints.extend(adjustments)
```

## Edge Cases

1. **All pilots fail**: Return None, orchestrator stops production
2. **Tie in scores**: Prefer lower-cost pilot
3. **Close scores**: May continue multiple pilots
4. **Budget exhausted**: Only evaluate, no continuation recommendation
