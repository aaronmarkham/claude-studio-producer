---
layout: default
title: Document-to-Video Pipeline Specification
---
# Document-to-Video Pipeline Specification

## Overview

A multi-stage pipeline that transforms documents (PDFs, papers, articles) into video content through iterative refinement. Each pass adds fidelity, enabling cheap quick drafts that can be progressively enhanced.

```
CORE PHILOSOPHY: "Album Art to Music Video"

v1: Audio + static image (album art)           ← $0.50, 2 min
v2: Audio + text overlays (lyrics/quotes)      ← $1.00, 5 min  
v3: Audio + animated graphics                  ← $2.00, 10 min
v4: Audio + AI video (B-roll)                  ← $5.00, 15 min
v5: Audio + avatar presenter                   ← $15.00, 20 min
v6: Full production (all of above)             ← $30.00, 30 min
```

## Pipeline Stages

### Stage 0: Document Ingestion & Atomization

**Input:** Document (PDF, DOCX, URL, etc.)

**Output:** Knowledge atoms stored in project memory

```python
@dataclass
class DocumentAtom:
    """Smallest unit of extracted knowledge"""
    atom_id: str
    atom_type: AtomType  # TEXT, FIGURE, TABLE, EQUATION, QUOTE, CITATION
    
    # Content
    content: str                    # Text content or description
    raw_data: Optional[bytes]       # For figures/tables: the actual image
    
    # Location in source
    source_page: Optional[int]
    source_location: Optional[Rect]  # Bounding box
    
    # Semantic metadata
    topics: List[str]               # Extracted topics/keywords
    entities: List[str]             # Named entities
    relationships: List[str]        # Relations to other atoms
    importance_score: float         # How central to the document
    
    # For figures/tables
    caption: Optional[str]
    figure_number: Optional[str]    # "Figure 3", "Table 2"
    data_summary: Optional[str]     # LLM-generated description of what it shows


class AtomType(Enum):
    # Text atoms
    TITLE = "title"
    ABSTRACT = "abstract"
    SECTION_HEADER = "section_header"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    CITATION = "citation"
    
    # Visual atoms
    FIGURE = "figure"
    CHART = "chart"
    TABLE = "table"
    EQUATION = "equation"
    DIAGRAM = "diagram"
    
    # Meta atoms
    AUTHOR = "author"
    DATE = "date"
    KEYWORD = "keyword"


@dataclass
class DocumentGraph:
    """Knowledge graph of document atoms"""
    document_id: str
    source_path: str
    
    atoms: Dict[str, DocumentAtom]
    
    # Graph structure
    hierarchy: Dict[str, List[str]]     # Parent -> children (sections -> paragraphs)
    references: Dict[str, List[str]]    # Atom -> atoms it references
    flow: List[str]                     # Reading order
    
    # Summaries at different levels
    one_sentence: str
    one_paragraph: str
    full_summary: str
    
    # Extracted for easy access
    figures: List[str]      # atom_ids of figures
    tables: List[str]       # atom_ids of tables
    key_quotes: List[str]   # atom_ids of important quotes
    
    def get_atom(self, atom_id: str) -> DocumentAtom: ...
    def get_figures(self) -> List[DocumentAtom]: ...
    def get_section(self, section_name: str) -> List[DocumentAtom]: ...
    def search(self, query: str) -> List[DocumentAtom]: ...  # Semantic search
```

**Implementation Options:**

```yaml
# Tier 1: Simple (pandoc + LLM)
extractor: "pandoc"
- Convert PDF to markdown via pandoc
- LLM extracts structure and metadata
- pdfimages extracts figures
- Good enough for most papers

# Tier 2: Structured (marker/nougat)  
extractor: "marker"  # or "nougat"
- ML-based PDF parsing
- Better figure/table extraction
- Preserves more structure
- https://github.com/VikParuchuri/marker

# Tier 3: Full KG (future)
extractor: "document_kg"
- Full knowledge graph extraction
- Entity linking
- Cross-document references
- Could use: LlamaIndex, Unstructured.io, Docling
```

---

### Stage 1: Script Generation

**Input:** DocumentGraph + target format + constraints

**Output:** Structured script with asset references

```python
@dataclass
class VideoScript:
    """Complete script for video production"""
    script_id: str
    project_id: str
    version: int
    
    # Target
    target_duration: float
    target_format: str          # "podcast", "explainer", "summary", "trailer"
    target_tier: ProductionTier
    
    # Content
    segments: List[ScriptSegment]
    
    # Asset manifest (what we need to generate)
    required_assets: List[AssetRequirement]
    
    # Source references
    document_id: str
    atoms_used: List[str]       # Which atoms this script draws from


class ProductionTier(Enum):
    """Progressive quality tiers"""
    STATIC = "static"           # v1: Audio + single image
    TEXT_OVERLAY = "text"       # v2: Audio + text graphics
    ANIMATED = "animated"       # v3: Audio + motion graphics
    BROLL = "broll"             # v4: Audio + AI video
    AVATAR = "avatar"           # v5: Audio + virtual presenter
    FULL = "full"               # v6: All of the above


@dataclass
class ScriptSegment:
    """A segment of the script"""
    segment_id: str
    segment_type: SegmentType
    
    # Timing
    start_time: Optional[float]     # Set after TTS generation
    duration: Optional[float]       # Set after TTS or explicit
    
    # Dialogue/Narration
    dialogue: Optional[str]
    speaker: Optional[str]          # "narrator", "host", "expert"
    
    # Visual specification (tier-dependent)
    visual: VisualSpec
    
    # Source reference
    source_atoms: List[str]         # Which document atoms this draws from
    
    # For iterative refinement
    locked: bool = False            # Don't regenerate this segment
    notes: Optional[str] = None     # Human notes for refinement


class SegmentType(Enum):
    INTRO = "intro"
    SECTION_HEADER = "section_header"
    EXPLANATION = "explanation"
    FIGURE_CALLOUT = "figure_callout"
    QUOTE = "quote"
    TRANSITION = "transition"
    RECAP = "recap"
    OUTRO = "outro"


@dataclass
class VisualSpec:
    """What should be shown - tier-aware"""
    
    # Tier 1: Static
    static_image: Optional[str] = None      # Atom ID or generated image
    
    # Tier 2: Text overlay
    text_overlay: Optional[TextOverlay] = None
    
    # Tier 3: Animation
    animation: Optional[AnimationSpec] = None
    
    # Tier 4: B-roll
    broll: Optional[BrollSpec] = None
    
    # Tier 5: Avatar
    avatar: Optional[AvatarSpec] = None
    
    # Compositing
    layout: str = "full"                    # "full", "pip", "split", "lower_third"
    
    def get_for_tier(self, tier: ProductionTier) -> 'VisualSpec':
        """Return visual spec appropriate for given tier"""
        ...


@dataclass
class TextOverlay:
    """Text graphics specification"""
    text: str
    style: str              # "quote", "title", "bullet", "lyric"
    position: str           # "center", "lower_third", "full"
    animation: str          # "fade", "typewriter", "slide"


@dataclass
class AnimationSpec:
    """Motion graphics specification"""
    animation_type: str     # "ken_burns", "parallax", "morph", "particles"
    source_image: str       # Atom ID
    motion_params: Dict     # Type-specific parameters


@dataclass
class BrollSpec:
    """AI video specification"""
    prompt: str
    seed_image: Optional[str]       # Atom ID to seed from
    style: str                      # "realistic", "abstract", "microscopic"
    continuity_group: Optional[str]
    duration: float


@dataclass
class AvatarSpec:
    """Virtual presenter specification"""
    avatar_id: str
    emotion: str            # "neutral", "excited", "thoughtful"
    gesture: Optional[str]  # "pointing", "nodding"
    position: str           # "center", "left", "right"
```

---

### Stage 2: Asset Generation

**Parallel generation based on tier:**

```python
@dataclass
class AssetRequirement:
    """What needs to be generated"""
    asset_id: str
    asset_type: AssetType
    
    # Generation params
    params: Dict[str, Any]
    
    # Dependencies
    depends_on: List[str]           # Other asset IDs
    
    # Provider preference
    preferred_provider: Optional[str]
    
    # For iterative refinement
    existing_asset_id: Optional[str]    # Reuse from previous version
    regenerate: bool = False


class AssetType(Enum):
    # Audio
    TTS = "tts"                     # Text-to-speech
    MUSIC = "music"                 # Background music
    SFX = "sfx"                     # Sound effects
    
    # Video
    LUMA_VIDEO = "luma_video"       # AI-generated video
    AVATAR_VIDEO = "avatar_video"   # Virtual presenter
    
    # Image
    FIGURE = "figure"               # Extracted figure
    GENERATED_IMAGE = "gen_image"   # AI-generated image
    TITLE_CARD = "title_card"       # Text graphic
    
    # Processed
    KEN_BURNS = "ken_burns"         # Image with motion
    TEXT_ANIMATION = "text_anim"    # Animated text
    
    # Composite
    COMPOSITE = "composite"         # Multiple layers combined
```

**Generation by Tier:**

```yaml
Tier STATIC:
  - TTS for all dialogue
  - Extract/select cover image
  - Stretch image to match audio duration
  
Tier TEXT_OVERLAY:
  - Everything from STATIC
  - Generate text overlays for quotes/key points
  - Simple fade transitions
  
Tier ANIMATED:
  - Everything from TEXT_OVERLAY
  - Ken Burns on figures
  - Animated text (typewriter, etc.)
  - Motion graphics transitions
  
Tier BROLL:
  - Everything from ANIMATED
  - Luma B-roll for explanation segments
  - Seed from figures where appropriate
  - Continuity chaining for related segments
  
Tier AVATAR:
  - Everything from BROLL
  - Virtual presenter for intro/outro
  - Picture-in-picture during explanations
  
Tier FULL:
  - All of the above
  - Multiple avatar angles
  - Advanced compositing
  - Color grading
```

---

### Stage 3: Assembly & Rendering

```python
@dataclass 
class Timeline:
    """Multi-track timeline for final assembly"""
    tracks: Dict[str, Track]
    duration: float
    
    def add_clip(self, track: str, clip: TimelineClip): ...
    def render(self, output_path: str): ...


@dataclass
class Track:
    """Single track in timeline"""
    track_id: str
    track_type: str         # "video_main", "video_overlay", "audio_dialogue", "audio_music"
    clips: List[TimelineClip]


@dataclass
class TimelineClip:
    """A clip placed on the timeline"""
    asset_id: str
    start_time: float
    duration: float
    
    # Transformations
    speed: float = 1.0          # For stretching video to match audio
    opacity: float = 1.0
    position: Optional[Rect] = None  # For PIP
    
    # Transitions
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None


# Assembly handles:
# - Stretching video to match audio duration
# - Layer compositing (PIP, overlays)
# - Transitions between segments
# - Audio mixing (dialogue + music)
```

---

## Project Memory & Iterative Refinement

**Key Concept:** Projects persist and can be resumed/refined

```python
@dataclass
class Project:
    """Persistent project state"""
    project_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    
    # Source
    document_graph: DocumentGraph
    
    # Versions
    versions: List[ProjectVersion]
    current_version: int
    
    # Generated assets (reusable across versions)
    asset_library: Dict[str, GeneratedAsset]
    
    # Memory namespace
    memory_namespace: str   # For learnings, preferences


@dataclass
class ProjectVersion:
    """A specific version/iteration of the project"""
    version: int
    tier: ProductionTier
    
    script: VideoScript
    timeline: Timeline
    
    # What was generated vs reused
    generated_assets: List[str]
    reused_assets: List[str]
    
    # Output
    output_path: Optional[str]
    
    # Cost tracking
    generation_cost: float
    render_time: float


# Refinement workflow:
project = load_project("science_paper_123")

# Upgrade from STATIC to BROLL
new_version = project.upgrade_tier(
    target_tier=ProductionTier.BROLL,
    
    # Preserve what works
    keep_tts=True,              # Don't regenerate audio
    keep_segments=[1, 2, 5],    # Lock these segments
    
    # Regenerate specific things
    regenerate_segments=[3, 4], # Redo these with B-roll
    
    # Add new content
    add_segments=[              # Insert new segments
        ScriptSegment(...)
    ],
)
```

---

## CLI Interface

```bash
# === PROJECT CREATION ===

# Create project from PDF
claude-studio project create \
  --source paper.pdf \
  --name "CRISPR Explainer" \
  --format podcast \
  --duration 120

# Create from URL
claude-studio project create \
  --source "https://arxiv.org/pdf/..." \
  --name "AI Safety Paper"


# === TIER-BASED PRODUCTION ===

# Quick draft (static image + TTS)
claude-studio project produce <project_id> --tier static

# Add text overlays
claude-studio project produce <project_id> --tier text

# Add animations
claude-studio project produce <project_id> --tier animated

# Add AI B-roll
claude-studio project produce <project_id> --tier broll --live -p luma

# Add avatar (future)
claude-studio project produce <project_id> --tier avatar --live -p heygen


# === ITERATIVE REFINEMENT ===

# Resume and upgrade
claude-studio project upgrade <project_id> \
  --from-version 2 \
  --to-tier broll \
  --keep-audio \
  --regenerate-segments 3,4,5

# Preview specific segment
claude-studio project preview <project_id> --segment 3

# Lock segments that are good
claude-studio project lock <project_id> --segments 1,2,6

# Regenerate specific segment with different provider
claude-studio project regen <project_id> \
  --segment 4 \
  --provider runway \
  --prompt "override prompt here"


# === INSPECTION ===

# Show project structure
claude-studio project show <project_id>

# Show extracted atoms
claude-studio project atoms <project_id> --type figures

# Show script
claude-studio project script <project_id> --version latest

# Show asset library
claude-studio project assets <project_id>

# Show cost breakdown
claude-studio project cost <project_id>


# === MIXING (existing) ===

# Mix audio with video (stretch to fit)
claude-studio mix \
  --video scene.mp4 \
  --audio narration.mp3 \
  --output mixed.mp4 \
  --mode stretch  # or loop, trim, pad
```

---

## Provider Integration

```python
class ProviderCapability(Enum):
    """What a provider can do"""
    TTS = "tts"
    VOICE_CLONE = "voice_clone"
    VIDEO_GEN = "video_gen"
    VIDEO_EXTEND = "video_extend"       # Luma's chaining
    IMAGE_TO_VIDEO = "image_to_video"
    AVATAR = "avatar"
    IMAGE_GEN = "image_gen"
    MUSIC_GEN = "music_gen"


# Provider registry
PROVIDERS = {
    "luma": {
        "capabilities": [VIDEO_GEN, VIDEO_EXTEND, IMAGE_TO_VIDEO],
        "chaining": "extends",      # Returns extended video
        "max_duration": 9,          # Per generation
        "cost_model": "per_second",
    },
    "runway": {
        "capabilities": [VIDEO_GEN, IMAGE_TO_VIDEO],
        "chaining": "none",         # No native chaining
        "max_duration": 16,
        "cost_model": "per_second",
    },
    "elevenlabs": {
        "capabilities": [TTS, VOICE_CLONE],
        "cost_model": "per_character",
    },
    "inworld": {
        "capabilities": [TTS, VOICE_CLONE],
        "cost_model": "per_character",
    },
    "heygen": {  # Future
        "capabilities": [AVATAR],
        "cost_model": "per_minute",
    },
    "flux": {  # Future
        "capabilities": [IMAGE_GEN],
        "cost_model": "per_image",
    },
}
```

---

## Execution Model

```python
# For a BROLL tier production:

execution_plan = ExecutionPlan(
    phases=[
        # Phase 0: Extraction (if not cached)
        Phase(
            phase_id="extract",
            groups=[
                TaskGroup(
                    tasks=["extract_text", "extract_figures"],
                    mode=PARALLEL,
                    provider="pdf_extractor",
                ),
            ],
            skip_if=lambda project: project.document_graph is not None,
        ),
        
        # Phase 1: Script (if not cached/locked)
        Phase(
            phase_id="script",
            groups=[
                TaskGroup(
                    tasks=["generate_script"],
                    mode=SEQUENTIAL,
                    provider="llm",
                ),
            ],
            depends_on=["extract"],
        ),
        
        # Phase 2: Audio (parallel)
        Phase(
            phase_id="audio",
            groups=[
                TaskGroup(
                    tasks=["tts_segment_1", "tts_segment_2", ...],
                    mode=PARALLEL,
                    provider="elevenlabs",
                ),
                TaskGroup(
                    tasks=["music_bed"],
                    mode=PARALLEL,
                    provider="suno",  # or whatever
                ),
            ],
            depends_on=["script"],
        ),
        
        # Phase 3: Video (mixed parallel/sequential)
        Phase(
            phase_id="video",
            groups=[
                # Ken Burns on figures (parallel)
                TaskGroup(
                    tasks=["ken_burns_fig1", "ken_burns_fig2"],
                    mode=PARALLEL,
                    provider="ffmpeg",
                ),
                # Luma B-roll chain A
                TaskGroup(
                    group_id="broll_chain_a",
                    tasks=["broll_1", "broll_3"],  # Scene order within chain
                    mode=SEQUENTIAL,              # Chained
                    provider="luma",
                ),
                # Luma B-roll chain B
                TaskGroup(
                    group_id="broll_chain_b", 
                    tasks=["broll_2", "broll_4"],
                    mode=SEQUENTIAL,
                    provider="luma",
                ),
                # Independent clips
                TaskGroup(
                    tasks=["broll_5"],
                    mode=PARALLEL,
                    provider="luma",
                ),
            ],
            depends_on=["script"],  # Needs prompts from script
        ),
        
        # Phase 4: Assembly
        Phase(
            phase_id="assembly",
            groups=[
                TaskGroup(
                    tasks=["build_timeline", "render"],
                    mode=SEQUENTIAL,
                    provider="ffmpeg",
                ),
            ],
            depends_on=["audio", "video"],
        ),
    ]
)
```

---

## Memory Integration

```python
# Project memory namespace
/org/{org}/projects/{project_id}/
    ├── document/           # Extracted atoms
    ├── scripts/            # Script versions
    ├── assets/             # Generated assets
    └── learnings/          # What worked/didn't

# Cross-project learnings flow up
/org/{org}/learnings/provider/{provider}/     # Provider tips
/org/{org}/learnings/format/{format}/         # Format-specific tips (podcast, explainer)
```

---

## Future Extensions

### Avatar Integration (v5+)
```python
@dataclass
class AvatarSpec:
    avatar_id: str              # "science_host", custom clone
    provider: str               # "heygen", "d-id", "synthesia"
    
    # Appearance
    outfit: Optional[str]
    background: Optional[str]
    
    # Performance
    emotion: str
    energy_level: float         # 0-1
    gesture_frequency: float    # How often to gesture
    
    # Audio sync
    audio_asset_id: str         # TTS to lip sync to
```

### Multi-Speaker Support
```python
# Script with multiple speakers
segments = [
    ScriptSegment(
        dialogue="Welcome to Science Explained!",
        speaker="host",
        visual=VisualSpec(avatar=AvatarSpec(avatar_id="main_host")),
    ),
    ScriptSegment(
        dialogue="Today we're joined by Dr. Smith...",
        speaker="host",
    ),
    ScriptSegment(
        dialogue="Thanks for having me!",
        speaker="guest",
        visual=VisualSpec(avatar=AvatarSpec(avatar_id="guest_avatar")),
    ),
]
```

### Interactive Refinement
```python
# Human-in-the-loop refinement
claude-studio project refine <project_id> --interactive

# Opens TUI/web interface:
# - Preview each segment
# - Accept / Regenerate / Edit prompt
# - Adjust timing
# - Reorder segments
# - Add/remove segments
```

---

## Summary

This spec enables:

1. **Document → Video** in one command at any quality tier
2. **Iterative refinement** - start cheap, add fidelity
3. **Asset reuse** - TTS doesn't regenerate when adding B-roll
4. **Provider flexibility** - swap providers per asset type
5. **Memory & learning** - learnings persist across projects
6. **Future-proof** - avatar support designed in but not required

The key insight is treating video production like software releases:
- v1 is MVP (audio + image)
- Each version adds features (overlays, animation, B-roll, avatar)
- Assets are cached and reused
- Only regenerate what changes
