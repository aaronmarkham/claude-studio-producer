# Seed Assets and Multi-Modal Inputs Specification

## Overview

Productions can be seeded with reference materials that inform creative direction: images, sketches, storyboards, mood boards, existing videos, audio samples, brand guidelines, etc. The Producer and ScriptWriter agents use these to create more personalized, on-brand content.

## Use Cases

### 1. Personal/Authentic Content
```
User: "Make a video about building this app with Claude"
Seed: Photos of handwritten notebook sketches
Result: Video incorporates the actual notebook aesthetic, hand-drawn feel
```

### 2. Brand Consistency
```
User: "Product demo for our SaaS platform"
Seed: Brand guidelines PDF, logo, color palette, existing marketing video
Result: Video matches brand colors, typography, tone
```

### 3. Storyboard Execution
```
User: "Execute this storyboard"
Seed: Hand-drawn storyboard images with scene descriptions
Result: Video follows the exact shot sequence and framing
```

### 4. Style Reference
```
User: "Make it look like this"
Seed: Reference video clips, movie stills, art style examples
Result: Video mimics the visual style
```

### 5. Documentary/Real Footage
```
User: "Tell the story of our company retreat"
Seed: Raw phone footage, photos from the event
Result: Polished video incorporating real moments
```

## Data Models

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path


class SeedAssetType(Enum):
    """Types of seed assets"""
    
    # Images
    IMAGE = "image"                      # General reference image
    SKETCH = "sketch"                    # Hand-drawn sketch/doodle
    STORYBOARD = "storyboard"            # Storyboard frame(s)
    MOOD_BOARD = "mood_board"            # Collection of style references
    SCREENSHOT = "screenshot"            # UI/app screenshots
    PHOTO = "photo"                      # Real photographs
    LOGO = "logo"                        # Brand logo
    
    # Documents
    BRAND_GUIDELINES = "brand_guidelines" # Brand guide PDF
    SCRIPT = "script"                    # Existing script/screenplay
    NOTES = "notes"                      # Handwritten or typed notes
    OUTLINE = "outline"                  # Story outline
    
    # Video
    REFERENCE_VIDEO = "reference_video"  # Style reference
    RAW_FOOTAGE = "raw_footage"          # Real footage to incorporate
    EXISTING_AD = "existing_ad"          # Previous ad/video to match
    
    # Audio
    MUSIC_REFERENCE = "music_reference"  # "Make it sound like this"
    VOICEOVER_SAMPLE = "voiceover_sample" # Voice to match/clone
    
    # Other
    COLOR_PALETTE = "color_palette"      # Specific colors to use
    FONT_SAMPLE = "font_sample"          # Typography reference
    CHARACTER_DESIGN = "character_design" # Character reference sheets


class AssetRole(Enum):
    """How the asset should be used"""
    
    STYLE_REFERENCE = "style_reference"   # "Make it look like this"
    CONTENT_SOURCE = "content_source"     # "Include this in the video"
    BRAND_GUIDE = "brand_guide"           # "Follow these guidelines"
    STORYBOARD = "storyboard"             # "Follow this sequence"
    TEXTURE = "texture"                   # "Use this texture/pattern"
    CHARACTER = "character"               # "This is what X looks like"
    SETTING = "setting"                   # "This is the environment"
    MOOD = "mood"                         # "This is the feeling/vibe"


@dataclass
class SeedAsset:
    """A single seed asset with metadata"""
    
    asset_id: str
    asset_type: SeedAssetType
    role: AssetRole
    file_path: str                        # Local path or URL
    
    # User's description of what this is
    description: str
    
    # How to use it (user instructions)
    usage_instructions: str
    
    # Optional metadata
    tags: List[str] = field(default_factory=list)
    
    # For storyboards/sequences - which part?
    sequence_index: Optional[int] = None
    
    # For images - extracted description (from vision model)
    extracted_description: Optional[str] = None
    
    # For brand assets
    brand_info: Optional[Dict[str, Any]] = None


@dataclass
class SeedAssetCollection:
    """Collection of seed assets for a production"""
    
    assets: List[SeedAsset] = field(default_factory=list)
    
    # Global instructions for how to use these
    global_instructions: str = ""
    
    # Extracted themes/patterns (populated by analysis)
    extracted_themes: List[str] = field(default_factory=list)
    extracted_color_palette: List[str] = field(default_factory=list)
    extracted_style_keywords: List[str] = field(default_factory=list)
    
    def get_by_type(self, asset_type: SeedAssetType) -> List[SeedAsset]:
        return [a for a in self.assets if a.asset_type == asset_type]
    
    def get_by_role(self, role: AssetRole) -> List[SeedAsset]:
        return [a for a in self.assets if a.role == role]
    
    def get_storyboard_sequence(self) -> List[SeedAsset]:
        storyboard = self.get_by_type(SeedAssetType.STORYBOARD)
        return sorted(storyboard, key=lambda a: a.sequence_index or 0)


@dataclass
class ProductionRequest:
    """Complete production request with concept and seed assets"""
    
    # The main concept/prompt
    concept: str
    
    # Budget
    total_budget: float
    
    # Target duration
    target_duration: int = 60
    
    # Seed assets
    seed_assets: SeedAssetCollection = field(default_factory=SeedAssetCollection)
    
    # Style preferences (can be derived from seeds)
    style_preferences: Dict[str, Any] = field(default_factory=dict)
    
    # Audio preferences
    audio_tier: str = "time_synced"
    voice_style: str = "professional"
    music_mood: str = "corporate"
    
    # Output preferences
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
```

## Asset Analyzer Agent

A new agent that processes seed assets to extract useful information:

```python
# agents/asset_analyzer.py

class AssetAnalyzerAgent(StudioAgent):
    """
    Analyzes seed assets to extract:
    - Visual descriptions (from images)
    - Color palettes
    - Style keywords
    - Storyboard sequences
    - Brand information
    """
    
    def __init__(self, claude_client: ClaudeClient):
        super().__init__(name="asset_analyzer", claude_client=claude_client)
    
    async def analyze_collection(
        self,
        collection: SeedAssetCollection
    ) -> SeedAssetCollection:
        """Analyze all assets and enrich the collection"""
        
        # Analyze each asset
        for asset in collection.assets:
            if asset.asset_type in [
                SeedAssetType.IMAGE, 
                SeedAssetType.SKETCH,
                SeedAssetType.STORYBOARD,
                SeedAssetType.PHOTO
            ]:
                asset.extracted_description = await self.analyze_image(asset)
        
        # Extract global themes
        collection.extracted_themes = await self.extract_themes(collection)
        collection.extracted_color_palette = await self.extract_colors(collection)
        collection.extracted_style_keywords = await self.extract_style(collection)
        
        return collection
    
    async def analyze_image(self, asset: SeedAsset) -> str:
        """Use Claude vision to describe an image asset"""
        
        prompt = f"""Analyze this image for video production purposes.

Asset Type: {asset.asset_type.value}
Role: {asset.role.value}
User Description: {asset.description}
Usage Instructions: {asset.usage_instructions}

Describe:
1. What is visually depicted
2. Key visual elements that should be replicated
3. Color palette (list specific colors)
4. Mood/atmosphere
5. Style characteristics
6. If it's a sketch/storyboard: what scene/action is shown

Be specific and detailed - this will guide video generation."""

        # Would send image to Claude vision
        response = await self.claude.query_with_image(
            prompt=prompt,
            image_path=asset.file_path
        )
        
        return response
    
    async def extract_themes(self, collection: SeedAssetCollection) -> List[str]:
        """Extract common themes across all assets"""
        
        descriptions = [
            a.extracted_description or a.description 
            for a in collection.assets
        ]
        
        prompt = f"""Based on these asset descriptions, identify 5-7 key themes 
that should guide the video production:

{chr(10).join(descriptions)}

Return as a simple list of theme keywords/phrases."""

        response = await self.claude.query(prompt)
        # Parse response into list
        return [line.strip("- ") for line in response.strip().split("\n") if line.strip()]
    
    async def extract_colors(self, collection: SeedAssetCollection) -> List[str]:
        """Extract color palette from visual assets"""
        # Would use vision to extract dominant colors
        # Return as hex codes or color names
        pass
    
    async def extract_style(self, collection: SeedAssetCollection) -> List[str]:
        """Extract style keywords from assets"""
        pass
```

## Updated Production Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      ProductionRequest                           │
│  - concept: "Making an app with Claude"                         │
│  - seed_assets: [notebook_photo_1, notebook_photo_2, ...]       │
│  - budget: $150                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AssetAnalyzerAgent                            │
│                                                                  │
│  Analyzes images with Claude Vision:                            │
│  - "Ruled notebook with pencil sketches of UI wireframes"       │
│  - "Hand-drawn flowchart showing agent architecture"            │
│  - "Doodles of lightbulbs and arrows connecting ideas"          │
│                                                                  │
│  Extracts:                                                       │
│  - Themes: [hand-drawn, organic, ideation, technical]           │
│  - Colors: [#F5F5DC (paper), #333 (pencil), #4A90A4 (highlights)]│
│  - Style: [sketch aesthetic, notebook texture, authentic]       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ProducerAgent                               │
│                                                                  │
│  Uses extracted info to plan pilots:                            │
│  - "Notebook aesthetic suggests ANIMATED tier with sketch style"│
│  - "Hand-drawn elements → motion graphics with paper texture"   │
│  - Recommends providers that support style transfer             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ScriptWriterAgent                             │
│                                                                  │
│  Incorporates seed assets into scenes:                          │
│                                                                  │
│  Scene 1: "Open on actual notebook page (use seed_asset_1)"     │
│           "Camera slowly zooms into the sketched wireframe"     │
│           "Pencil lines animate into working UI"                │
│                                                                  │
│  Scene 2: "Hand draws flowchart (match style of seed_asset_2)"  │
│           "Arrows animate to show data flow"                    │
│                                                                  │
│  Visual direction includes:                                      │
│  - Texture: ruled notebook paper                                │
│  - Color palette: warm paper tones + pencil gray               │
│  - Animation style: sketch-to-reality transitions              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   VideoGeneratorAgent                            │
│                                                                  │
│  Uses seed assets as:                                           │
│  - Image-to-video input (animate the actual notebook photo)     │
│  - Style reference (match the hand-drawn aesthetic)             │
│  - Texture overlay (paper grain effect)                         │
│                                                                  │
│  Prompt includes extracted descriptions:                        │
│  "Animate this notebook sketch, pencil lines coming to life,    │
│   maintaining ruled paper texture, warm lighting..."            │
└─────────────────────────────────────────────────────────────────┘
```

## Updated Scene Dataclass

```python
@dataclass
class Scene:
    """Scene with seed asset references"""
    
    scene_id: str
    title: str
    description: str
    duration: float
    visual_elements: List[str]
    
    # Seed asset references
    seed_asset_refs: List[SeedAssetRef] = field(default_factory=list)
    
    # How to use the referenced assets
    asset_usage: str = ""  # "Use as starting frame", "Match style", etc.
    
    # Extracted style to apply
    style_keywords: List[str] = field(default_factory=list)
    color_palette: List[str] = field(default_factory=list)
    texture_notes: str = ""
    
    # Audio
    voiceover_text: Optional[str] = None
    sync_points: List[SyncPoint] = field(default_factory=list)
    music_transition: str = "continue"
    sfx_cues: List[str] = field(default_factory=list)
    audio_notes: str = ""
    
    # Standard fields
    transition_in: str = "cut"
    transition_out: str = "cut"
    prompt_hints: List[str] = field(default_factory=list)


@dataclass
class SeedAssetRef:
    """Reference to a seed asset within a scene"""
    
    asset_id: str
    usage: str  # "source_frame", "style_reference", "texture", "include_directly"
    timestamp: Optional[float] = None  # When to use it in the scene
    transform: Optional[str] = None    # "animate", "zoom", "pan", "static"
```

## Example: Your Notebook Video

```python
# User provides:
request = ProductionRequest(
    concept="""
    Create a 60-second video about building an AI application with Claude.
    
    The story:
    - Starts with brainstorming in a notebook (I have actual photos)
    - Ideas come to life as the sketches animate
    - Show the evolution from doodles to working code
    - End with the finished application
    
    Tone: Authentic, creative process, "behind the scenes" feel
    Keep the hand-drawn aesthetic throughout - this isn't polished corporate,
    it's real creative work.
    """,
    
    total_budget=150.0,
    
    seed_assets=SeedAssetCollection(
        assets=[
            SeedAsset(
                asset_id="notebook_1",
                asset_type=SeedAssetType.SKETCH,
                role=AssetRole.CONTENT_SOURCE,
                file_path="./assets/notebook_page_1.jpg",
                description="First page of my notebook with initial concept sketches",
                usage_instructions="Use as opening shot, then animate the sketches"
            ),
            SeedAsset(
                asset_id="notebook_2", 
                asset_type=SeedAssetType.SKETCH,
                role=AssetRole.CONTENT_SOURCE,
                file_path="./assets/notebook_page_2.jpg",
                description="Agent architecture flowchart I drew",
                usage_instructions="Animate the arrows and connections"
            ),
            SeedAsset(
                asset_id="notebook_3",
                asset_type=SeedAssetType.SKETCH,
                role=AssetRole.STYLE_REFERENCE,
                file_path="./assets/notebook_doodles.jpg",
                description="Random doodles and margin notes",
                usage_instructions="Use style for transition elements and decorations"
            ),
        ],
        global_instructions="""
        Maintain the ruled notebook paper aesthetic throughout.
        The pencil sketch style should persist even as things animate.
        Colors should be warm and natural - paper yellows, pencil grays.
        This should feel like watching someone's actual creative process.
        """
    ),
    
    voice_style="conversational",  # Not corporate
    music_mood="ambient"           # Thoughtful, not upbeat
)
```

## AssetAnalyzer Output

After analysis, the collection would be enriched:

```python
collection.extracted_themes = [
    "creative process",
    "hand-drawn authenticity", 
    "technical architecture",
    "ideation and brainstorming",
    "sketch-to-reality transformation"
]

collection.extracted_color_palette = [
    "#F5F5DC",  # Cream paper
    "#333333",  # Pencil graphite
    "#666666",  # Light pencil
    "#4A90A4",  # Blue highlighter accent
    "#E8DCC4",  # Aged paper edge
]

collection.extracted_style_keywords = [
    "ruled notebook lines",
    "pencil sketch texture",
    "hand-drawn imperfection",
    "organic line work",
    "margin annotations",
    "paper grain texture"
]

# Each asset now has extracted_description:
assets[0].extracted_description = """
Cream-colored ruled notebook page photographed from above.
Contains pencil sketches of UI wireframes - rectangles representing 
screens with arrows showing navigation flow. Handwritten labels 
include "Producer", "Critic", "Video Gen". Small lightbulb doodle 
in corner. Paper has slight curl at edges, natural lighting creates
soft shadows. Pencil work varies from light sketching to darker 
emphasized lines.
"""
```

## ScriptWriter Output (Scene 1)

```python
Scene(
    scene_id="scene_1",
    title="The Spark",
    description="""
    Open on the actual notebook page (notebook_1). Camera slowly 
    pushes in on the sketched wireframes. The pencil lines begin 
    to glow softly, then animate - rectangles slide into place,
    arrows draw themselves, labels appear in handwritten style.
    """,
    duration=8.0,
    
    visual_elements=[
        "ruled notebook paper texture",
        "pencil sketch wireframes",
        "animating UI rectangles",
        "self-drawing arrows"
    ],
    
    seed_asset_refs=[
        SeedAssetRef(
            asset_id="notebook_1",
            usage="source_frame",
            timestamp=0.0,
            transform="animate"
        )
    ],
    
    asset_usage="Start with actual photo, then animate the sketched elements",
    
    style_keywords=["hand-drawn", "organic", "sketch-to-life"],
    color_palette=["#F5F5DC", "#333333", "#4A90A4"],
    texture_notes="Maintain paper grain throughout animation",
    
    voiceover_text="It started with a simple sketch in my notebook...",
    sync_points=[
        SyncPoint(timestamp=2.0, word_or_phrase="sketch", visual_cue="lines start animating")
    ],
    
    music_transition="fade_in",
    audio_notes="Soft ambient, pencil scratching foley"
)
```

## Video Generation Prompt

The VideoGeneratorAgent builds a prompt like:

```
Animate this notebook sketch coming to life.

SOURCE IMAGE: [notebook_1.jpg]
STYLE: Image-to-video animation

DESCRIPTION:
Starting frame is a real photograph of a ruled notebook page with 
pencil UI wireframe sketches. Animate the sketched elements:
- Rectangles slide smoothly into position
- Arrows draw themselves with pencil texture
- Labels fade in with handwritten appearance

MAINTAIN:
- Ruled notebook paper texture (do not lose the lines)
- Pencil graphite texture on all drawn elements
- Warm cream paper color (#F5F5DC)
- Soft natural lighting with subtle shadows
- Hand-drawn imperfection (not too perfect/digital)

MOTION:
- Slow, deliberate animation (nothing jarring)
- Elements animate sequentially, not all at once
- Slight paper texture movement (organic feel)

DURATION: 8 seconds
CAMERA: Slow push-in, centered on main wireframe
```

## Integration Points

### 1. CLI Input

```bash
# Provide assets via CLI
python -m studio produce \
  --concept "Making an app with Claude" \
  --budget 150 \
  --asset ./notebook_1.jpg:sketch:content_source:"Opening sketches" \
  --asset ./notebook_2.jpg:sketch:content_source:"Architecture diagram" \
  --asset-instructions "Maintain notebook aesthetic throughout"
```

### 2. API Input

```python
# POST /workflows/full_production/run
{
    "inputs": {
        "concept": "Making an app with Claude",
        "total_budget": 150.0,
        "seed_assets": [
            {
                "asset_id": "notebook_1",
                "asset_type": "sketch",
                "role": "content_source",
                "file_path": "/uploads/notebook_1.jpg",
                "description": "Opening sketches",
                "usage_instructions": "Animate into life"
            }
        ],
        "global_asset_instructions": "Maintain notebook aesthetic"
    }
}
```

### 3. Upload Handling

```python
# server/routes/assets.py

@router.post("/upload")
async def upload_asset(
    file: UploadFile,
    asset_type: SeedAssetType,
    role: AssetRole,
    description: str,
    usage_instructions: str = ""
) -> SeedAsset:
    """Upload a seed asset for production"""
    
    # Save file
    file_path = f"/artifacts/uploads/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Create asset record
    asset = SeedAsset(
        asset_id=str(uuid.uuid4())[:8],
        asset_type=asset_type,
        role=role,
        file_path=file_path,
        description=description,
        usage_instructions=usage_instructions
    )
    
    return asset
```

## Provider Requirements

For seed asset support, providers need:

| Capability | Providers |
|------------|-----------|
| Image-to-Video | Runway, Pika, Stability, Luma, Kling |
| Style Reference | Runway, Pika, Luma |
| Image Animation | Runway, Stability |
| Consistent Style | All (via prompt engineering) |

## Implementation Priority

1. **Phase 1**: SeedAsset data models
2. **Phase 2**: AssetAnalyzerAgent (uses Claude Vision)
3. **Phase 3**: Update ScriptWriterAgent to reference assets
4. **Phase 4**: Update VideoGeneratorAgent for image-to-video
5. **Phase 5**: Asset upload API endpoints

## Summary

This system allows users to provide:
- 📷 Reference images (style, content, texture)
- 📝 Sketches and storyboards
- 🎨 Brand guidelines and color palettes
- 🎬 Reference videos (style matching)
- 🎵 Audio references (voice, music style)

The agents then:
1. **Analyze** assets with Claude Vision
2. **Extract** themes, colors, style keywords
3. **Incorporate** into scene descriptions
4. **Generate** video using assets as inputs/references

This creates **authentic, personalized content** rather than generic AI video! 🎨
