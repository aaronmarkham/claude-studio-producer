---
layout: default
title: Editor Agent Specification
---
# Editor Agent Specification

## Purpose

The Editor Agent assembles final videos from generated scenes, creating Edit Decision Lists (EDLs) and selecting the best variations to create cohesive final cuts.

## Inputs

- `scenes`: List of scene specifications
- `video_candidates`: All generated video variations per scene
- `qa_results`: QA scores for each video
- `original_request`: High-level video concept
- `num_candidates`: How many final edit candidates to create

## Outputs

```python
@dataclass
class EditDecision:
    scene_id: str
    selected_variation: int
    video_url: str
    in_point: float  # Trim start (seconds)
    out_point: float  # Trim end (seconds)
    transition: str  # "cut", "dissolve", "fade"
    transition_duration: float

@dataclass
class EDLCandidate:
    candidate_id: str
    edits: List[EditDecision]
    total_duration: float
    estimated_quality: float
    editorial_approach: str  # "safe", "creative", "balanced"
    reasoning: str
```

## Behavior

1. Analyze all video candidates per scene
2. Consider QA scores, visual continuity, pacing
3. Create multiple EDL candidates with different approaches
4. Generate assembly instructions for final render

## Editorial Approaches

### Safe (Conservative)
- Always picks highest QA score per scene
- Standard cuts, minimal transitions
- Predictable, reliable result

### Creative (Artistic)
- May pick lower-scored but more interesting variations
- Uses varied transitions
- Takes visual risks for impact

### Balanced (Recommended)
- Weighs QA score + visual interest
- Maintains narrative flow
- Best overall quality

## Prompt Template

```
You are a professional video editor creating an Edit Decision List.

ORIGINAL REQUEST:
{original_request}

SCENES AND CANDIDATES:
{for each scene}
Scene {id}: {title}
  - Variation A: QA {score}, {notes}
  - Variation B: QA {score}, {notes}
  - Variation C: QA {score}, {notes}
{end for}

Create {num_candidates} different edit candidates:
1. SAFE: Highest quality, standard editing
2. CREATIVE: Most visually interesting, artistic choices
3. BALANCED: Best overall narrative flow

For each candidate, select one variation per scene and specify:
- Which variation to use
- Trim points (if needed)
- Transition to next scene

Return JSON:
{
  "candidates": [
    {
      "candidate_id": "safe_cut",
      "editorial_approach": "safe",
      "reasoning": "Selected highest QA scores throughout",
      "estimated_quality": 88,
      "edits": [
        {
          "scene_id": "scene_1",
          "selected_variation": 0,
          "video_url": "...",
          "in_point": 0.0,
          "out_point": 5.0,
          "transition": "fade_in",
          "transition_duration": 0.5
        }
      ],
      "total_duration": 58.5
    }
  ]
}
```

## EDL Export Formats

```python
def export_edl(self, candidate: EDLCandidate, format: str) -> str:
    """Export EDL in various formats"""
    
    if format == "cmx3600":
        return self._to_cmx3600(candidate)  # Industry standard
    elif format == "fcpxml":
        return self._to_fcpxml(candidate)   # Final Cut Pro
    elif format == "premiere":
        return self._to_premiere_xml(candidate)  # Adobe Premiere
    elif format == "json":
        return self._to_json(candidate)     # For programmatic use
```

## Integration

- Called by: `StudioOrchestrator` after all scenes are generated
- Receives from: `VideoGeneratorAgent` (videos), `QAVerifierAgent` (scores)
- Output used by: Video assembly/rendering pipeline

## Example Usage

```python
from agents.editor import EditorAgent

editor = EditorAgent(claude_client=claude)

candidates = await editor.create_edl_candidates(
    scenes=scenes,
    video_candidates=all_videos,
    qa_results=qa_scores,
    original_request=request,
    num_candidates=3
)

# Present to user for selection
for candidate in candidates:
    print(f"{candidate.candidate_id}: {candidate.editorial_approach}")
    print(f"  Quality: {candidate.estimated_quality}/100")
    print(f"  Duration: {candidate.total_duration}s")
    print(f"  Reasoning: {candidate.reasoning}")

# Export selected EDL
selected = candidates[0]
edl_file = editor.export_edl(selected, format="fcpxml")
```

## Visual Continuity Analysis

The Editor also checks for visual continuity:

```python
async def analyze_continuity(
    self,
    edit_sequence: List[EditDecision]
) -> List[str]:
    """Check for visual continuity issues between scenes"""
    
    issues = []
    
    for i in range(len(edit_sequence) - 1):
        current = edit_sequence[i]
        next_scene = edit_sequence[i + 1]
        
        # Use Claude Vision to compare end of current with start of next
        continuity_score = await self._check_transition(current, next_scene)
        
        if continuity_score < 70:
            issues.append(f"Jarring transition: {current.scene_id} → {next_scene.scene_id}")
    
    return issues
```

## Human Review Integration

The Editor supports human-in-the-loop review:

```python
@dataclass
class HumanFeedback:
    candidate_id: str
    approved: bool
    notes: str
    requested_changes: List[str]

async def incorporate_feedback(
    self,
    candidate: EDLCandidate,
    feedback: HumanFeedback
) -> EDLCandidate:
    """Revise EDL based on human feedback"""
    # Re-edit with feedback incorporated
```
