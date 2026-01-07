# Video Generator Agent Specification

## Purpose

The Video Generator Agent takes scene descriptions and generates actual video content by calling external video generation APIs (Runway, Pika, etc.).

## Inputs

- `scene`: Scene object from ScriptWriterAgent
- `production_tier`: Determines which API/settings to use
- `num_variations`: How many variations to generate per scene
- `budget_limit`: Maximum spend for this scene

## Outputs

```python
@dataclass
class GeneratedVideo:
    scene_id: str
    variation_id: int
    video_url: str
    thumbnail_url: str
    duration: float
    generation_cost: float
    provider: str  # "runway", "pika", "stability", etc.
    metadata: Dict
```

## Supported Providers

### Runway Gen-3 Alpha
- Best for: Photorealistic video
- Cost: ~$0.25-0.50/second
- Max duration: 10 seconds
- API: `runway.generate()`

### Pika Labs
- Best for: Animated/stylized content
- Cost: ~$0.10-0.20/second
- Max duration: 4 seconds
- API: `pika.generate()`

### Stability AI
- Best for: Motion graphics, abstract
- Cost: ~$0.05-0.10/second
- Max duration: 4 seconds
- API: `stability.generate()`

### Static Images (DALL-E / Midjourney)
- Best for: Slideshows, Ken Burns effect
- Cost: ~$0.02-0.05/image
- Post-processing: Add motion with zoom/pan
- API: `openai.images.generate()`

## Behavior

1. Select appropriate provider based on tier
2. Build optimized prompt from scene data
3. Generate `num_variations` versions
4. Track costs in real-time
5. Return all variations for QA evaluation

## Provider Selection Logic

```python
TIER_TO_PROVIDER = {
    ProductionTier.STATIC_IMAGES: ["dalle", "midjourney"],
    ProductionTier.MOTION_GRAPHICS: ["stability", "pika"],
    ProductionTier.ANIMATED: ["pika", "runway_turbo"],
    ProductionTier.PHOTOREALISTIC: ["runway_gen3", "sora"],
}
```

## Prompt Building

```python
def build_video_prompt(scene: Scene, tier: ProductionTier) -> str:
    """Build optimized prompt for video generation"""
    
    base_prompt = scene.description
    
    # Add visual elements
    elements = ", ".join(scene.visual_elements)
    
    # Add style hints based on tier
    style = TIER_STYLES[tier]
    
    # Add prompt hints from scene
    hints = ", ".join(scene.prompt_hints)
    
    return f"{base_prompt}. {elements}. Style: {style}. {hints}"
```

## Cost Tracking

```python
async def generate_with_budget(
    self,
    scene: Scene,
    budget_limit: float
) -> List[GeneratedVideo]:
    """Generate videos while respecting budget"""
    
    videos = []
    spent = 0
    
    for i in range(self.num_variations):
        estimated_cost = self._estimate_cost(scene.duration)
        
        if spent + estimated_cost > budget_limit:
            print(f"Budget limit reached after {i} variations")
            break
        
        video = await self._generate_single(scene, variation_id=i)
        videos.append(video)
        spent += video.generation_cost
    
    return videos
```

## Integration

- Called by: `StudioOrchestrator` during pilot execution
- Receives from: `ScriptWriterAgent` (scenes)
- Output used by: `QAVerifierAgent` for quality scoring

## Example Usage

```python
from agents.video_generator import VideoGeneratorAgent

generator = VideoGeneratorAgent(
    claude_client=claude,
    provider="runway",
    num_variations=3
)

videos = await generator.generate_scene(
    scene=scene,
    production_tier=ProductionTier.ANIMATED,
    budget_limit=10.00
)

for video in videos:
    print(f"Generated: {video.video_url} (${video.generation_cost})")
```

## Error Handling

- API rate limits: Exponential backoff
- Generation failures: Retry up to 3 times
- Budget exceeded: Stop and return partial results
- Provider unavailable: Fall back to secondary provider

## Configuration

```python
VIDEO_GENERATOR_CONFIG = {
    "runway": {
        "api_key_env": "RUNWAY_API_KEY",
        "base_url": "https://api.runwayml.com/v1",
        "max_duration": 10,
        "supported_tiers": ["animated", "photorealistic"]
    },
    "pika": {
        "api_key_env": "PIKA_API_KEY",
        "base_url": "https://api.pika.art/v1",
        "max_duration": 4,
        "supported_tiers": ["motion_graphics", "animated"]
    }
}
```
