# QA Verifier Agent Specification

## Purpose

The QA Verifier Agent analyzes generated videos against scene descriptions to score quality and detect mismatches. Uses Claude's vision capabilities to evaluate video frames.

## Inputs

- `scene`: Original scene specification
- `generated_video`: The video to evaluate
- `original_request`: High-level video concept for context

## Outputs

```python
@dataclass
class QAResult:
    scene_id: str
    video_url: str
    overall_score: float  # 0-100
    
    # Detailed scores
    visual_accuracy: float  # Do visuals match description?
    style_consistency: float  # Does it match the tier style?
    technical_quality: float  # Resolution, artifacts, smoothness
    narrative_fit: float  # Does it fit the story?
    
    # Issues found
    issues: List[str]
    suggestions: List[str]
    
    # Pass/fail
    passed: bool  # Score >= threshold
```

## Behavior

1. Extract key frames from video (start, middle, end)
2. Send frames + scene description to Claude Vision
3. Analyze visual match to description
4. Check for technical issues (artifacts, blur, etc.)
5. Score and provide actionable feedback

## Frame Extraction

```python
async def extract_frames(video_url: str, num_frames: int = 3) -> List[str]:
    """Extract key frames as base64 images"""
    # Using ffmpeg or similar
    # Returns: ["base64_frame1", "base64_frame2", "base64_frame3"]
```

## Prompt Template

```
You are a video QA specialist evaluating generated content.

SCENE SPECIFICATION:
- Title: {scene.title}
- Description: {scene.description}
- Visual Elements: {scene.visual_elements}
- Style: {production_tier}

ORIGINAL REQUEST CONTEXT:
{original_request}

I'm showing you 3 frames from the generated video (start, middle, end).

Evaluate:
1. Visual Accuracy (0-100): Do the visuals match the scene description?
2. Style Consistency (0-100): Does it match the expected production tier?
3. Technical Quality (0-100): Any artifacts, blur, or rendering issues?
4. Narrative Fit (0-100): Does this scene work in the overall story?

Return JSON:
{
  "overall_score": 82,
  "visual_accuracy": 85,
  "style_consistency": 80,
  "technical_quality": 78,
  "narrative_fit": 85,
  "issues": ["Background slightly inconsistent", "Minor blur in frame 2"],
  "suggestions": ["Regenerate with sharper focus", "Specify indoor lighting"],
  "passed": true
}
```

## Scoring Thresholds

```python
QA_THRESHOLDS = {
    ProductionTier.STATIC_IMAGES: 70,
    ProductionTier.MOTION_GRAPHICS: 75,
    ProductionTier.ANIMATED: 80,
    ProductionTier.PHOTOREALISTIC: 85,
}
```

## Integration

- Called by: `StudioOrchestrator` after video generation
- Receives from: `VideoGeneratorAgent` (generated videos)
- Output used by: `CriticAgent` for pilot evaluation

## Example Usage

```python
from agents.qa_verifier import QAVerifierAgent

qa = QAVerifierAgent(claude_client=claude)

result = await qa.verify_video(
    scene=scene,
    generated_video=video,
    original_request=request,
    production_tier=ProductionTier.ANIMATED
)

if result.passed:
    print(f"✓ Video passed QA: {result.overall_score}/100")
else:
    print(f"✗ Video failed: {result.issues}")
```

## Batch Processing

```python
async def verify_batch(
    self,
    scenes: List[Scene],
    videos: List[GeneratedVideo]
) -> List[QAResult]:
    """Verify multiple videos in parallel"""
    
    tasks = [
        self.verify_video(scene, video)
        for scene, video in zip(scenes, videos)
    ]
    
    return await asyncio.gather(*tasks)
```

## Quality Gates

The QA Verifier enforces quality gates:

1. **Hard Fail**: Score < 50 (unusable, must regenerate)
2. **Soft Fail**: Score 50-threshold (may regenerate if budget allows)
3. **Pass**: Score >= threshold (acceptable quality)
4. **Excellent**: Score >= 90 (no improvements needed)
