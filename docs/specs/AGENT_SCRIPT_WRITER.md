# Script Writer Agent Specification

## Purpose

The Script Writer Agent takes a high-level video concept and breaks it down into individual scenes with detailed descriptions, timing, and visual direction.

## Inputs

- `video_concept`: High-level description of the video
- `target_duration`: Total video length in seconds (default: 60)
- `production_tier`: The quality tier (affects scene complexity)
- `num_scenes`: Optional override for number of scenes

## Outputs

```python
@dataclass
class Scene:
    scene_id: str
    title: str
    description: str
    duration: float  # seconds
    visual_elements: List[str]
    audio_notes: str
    transition_in: str
    transition_out: str
    prompt_hints: List[str]  # Hints for video generation
```

## Behavior

1. Analyze the video concept for key narrative beats
2. Determine optimal number of scenes based on duration
3. Create scene breakdown with:
   - Logical narrative flow
   - Appropriate pacing
   - Visual variety
   - Consistent style
4. Generate prompt hints optimized for video generation

## Prompt Template

```
You are a professional video scriptwriter.

VIDEO CONCEPT: {video_concept}
TARGET DURATION: {target_duration} seconds
PRODUCTION TIER: {production_tier}
ESTIMATED SCENES: {num_scenes}

Break this concept into individual scenes. Each scene should:
- Be 3-8 seconds long
- Have a clear visual focus
- Flow naturally to the next scene
- Include specific visual elements for video generation

Return JSON:
{
  "scenes": [
    {
      "scene_id": "scene_1",
      "title": "Morning Standup",
      "description": "Developer joins video call with team",
      "duration": 5.0,
      "visual_elements": ["laptop screen", "video call grid", "coffee cup"],
      "audio_notes": "Upbeat background music, muted voices",
      "transition_in": "fade_in",
      "transition_out": "cut",
      "prompt_hints": ["professional office setting", "morning light"]
    }
  ]
}
```

## Integration

- Called by: `StudioOrchestrator` after Producer creates pilot strategies
- Calls: None (pure analysis)
- Output used by: `VideoGeneratorAgent` for actual generation

## Example Usage

```python
from agents.script_writer import ScriptWriterAgent

writer = ScriptWriterAgent(claude_client=claude)

scenes = await writer.create_script(
    video_concept="A day in the life of a developer using AI tools",
    target_duration=60,
    production_tier=ProductionTier.ANIMATED,
    num_scenes=12
)

for scene in scenes:
    print(f"{scene.scene_id}: {scene.title} ({scene.duration}s)")
```

## Quality Considerations

- Scenes should have visual variety
- Pacing should match the narrative tone
- Each scene should be achievable by video generation
- Prompt hints should be specific and actionable
