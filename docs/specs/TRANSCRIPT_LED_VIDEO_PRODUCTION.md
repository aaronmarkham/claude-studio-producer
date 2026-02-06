# Transcript-Led Video Production Specification

## Overview

This spec integrates the podcast training pipeline (which generates scripts from scientific papers) with a visual production pipeline that creates explainer videos. The key innovation: **use the user's own generated podcast script as the primary transcript, then produce synchronized concept visuals.**

```
PIPELINE FLOW

Paper (PDF)                          User Voice Recording
    │                                       │
    ▼                                       ▼
┌─────────────────────┐            ┌─────────────────────┐
│ Podcast Training    │            │ Alternative Input   │
│ Pipeline            │            │ (voice memo, live   │
│ - Knowledge Graph   │            │  narration)         │
│ - Segment Analysis  │            └─────────┬───────────┘
│ - Style Profile     │                      │
│ - Script Generation │                      │
└─────────┬───────────┘                      │
          ▼                                  │
    Generated Script ◄───────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────┐
│         VISUAL PRODUCTION PIPELINE          │
├─────────────────────────────────────────────┤
│ Stage 1: Transcript Cleanup (minimal)       │
│ Stage 2: Scene Segmentation (from training) │
│ Stage 3: Visual Planning (DALL-E + Luma)    │
│ Stage 4: Asset Generation                   │
│ Stage 5: Render & Composition               │
└─────────────────────────────────────────────┘
          │
          ▼
    Final Video (.mp4)
```

---

## Part 1: Bridge from Podcast Training to Video Production

### 1.1 Reusing Training Pipeline Artifacts

The podcast training pipeline already produces rich artifacts that map directly to video production needs:

| Training Artifact | Video Production Use |
|-------------------|---------------------|
| `AlignedSegment.segment_type` | Maps to scene type (determines visual style) |
| `AlignedSegment.key_concepts` | Drives DALL-E prompt content |
| `AlignedSegment.technical_terms` | Determines terminology to visualize |
| `AlignedSegment.referenced_figures` | Links to paper figures for recreation |
| `AlignedSegment.words_per_minute` | Informs scene duration estimation |
| `StyleProfile.vocabulary_complexity` | Determines visual abstraction level |
| `StructureProfile.segment_durations` | Provides timing templates |
| `KnowledgeGraph` atoms | Source material for concept figures |

### 1.2 Segment Type to Visual Style Mapping

```python
SEGMENT_VISUAL_MAPPING = {
    # Segment Type → (DALL-E Style, Animation Candidate, Visual Complexity)

    "INTRO": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,  # Usually static title card
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Opening visual with topic representation"
    },

    "BACKGROUND": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": False,
        "visual_complexity": "medium",
        "ken_burns": True,
        "template": "Prior work or foundational concept diagram"
    },

    "PROBLEM_STATEMENT": {
        "dalle_style": "technical diagram",
        "animation_candidate": True,  # Show problem emerging
        "visual_complexity": "medium",
        "ken_burns": False,
        "template": "Visual showing the gap or challenge"
    },

    "METHODOLOGY": {
        "dalle_style": "architectural diagram",
        "animation_candidate": True,  # Process flow
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "System architecture or process flow"
    },

    "KEY_FINDING": {
        "dalle_style": "data visualization",
        "animation_candidate": True,  # Data revealing itself
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "Chart, graph, or result visualization"
    },

    "FIGURE_DISCUSSION": {
        "dalle_style": "technical diagram",
        "animation_candidate": True,  # Annotate figure
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "Recreation of paper figure with annotations"
    },

    "IMPLICATION": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": True,  # Ripple effects
        "visual_complexity": "medium",
        "ken_burns": True,
        "template": "Real-world application or impact"
    },

    "LIMITATION": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Visual metaphor for constraint"
    },

    "CONCLUSION": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Summary visual or callback to intro"
    },

    "TANGENT": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Related concept visualization"
    },

    "TRANSITION": {
        "dalle_style": None,  # No new visual, use transition effect
        "animation_candidate": False,
        "visual_complexity": "none",
        "ken_burns": False,
        "template": None
    }
}
```

### 1.3 Knowledge Graph to DALL-E Prompt

When a segment references paper atoms (figures, equations, concepts), we can generate precise DALL-E prompts:

```python
def generate_dalle_prompt_from_atoms(
    segment: AlignedSegment,
    knowledge_graph: DocumentGraph,
    visual_mapping: dict
) -> str:
    """
    Generate a DALL-E prompt from segment content and linked atoms.
    """
    base_style = visual_mapping[segment.segment_type]["dalle_style"]

    # Get the key concepts to visualize
    concepts = segment.key_concepts[:3]  # Top 3 concepts

    # Check for referenced figures in the paper
    figure_context = ""
    if segment.referenced_figures:
        for fig_id in segment.referenced_figures:
            atom = knowledge_graph.get_atom(fig_id)
            if atom and atom.atom_type == "figure":
                figure_context = f"Based on scientific figure: {atom.caption}. "
                break

    # Build the prompt
    prompt_parts = [
        f"Create a {base_style} illustration.",
        figure_context,
        f"Main concepts: {', '.join(concepts)}.",
        f"Technical terms to represent: {', '.join(segment.technical_terms[:3])}.",
        "Style: clean, dark background, vibrant accent colors.",
        "Composition: centered with negative space for text overlay.",
        "Aesthetic: modern technical illustration, not photorealistic."
    ]

    return " ".join(filter(None, prompt_parts))
```

---

## Part 2: Extended Pipeline Stages

### 2.1 Stage 0: Script Generation (from Training Pipeline)

Before the visual production stages, we generate the script using the trained podcast system:

```python
@dataclass
class ScriptGenerationInput:
    """Input for generating a podcast script from a paper."""
    paper_path: str                    # Path to PDF
    target_depth: PodcastDepth         # OVERVIEW, STANDARD, DEEP_DIVE
    style_profile: Optional[str]       # Which trained style to use
    voice_preference: str = "user"     # "user" (record yourself) or "tts"


@dataclass
class ScriptGenerationOutput:
    """Output of script generation, ready for visual production."""
    script_text: str
    aligned_segments: List[AlignedSegment]
    knowledge_graph: DocumentGraph
    estimated_duration: float
    key_figures: List[FigureAtom]

    # For audio production
    tts_audio_path: Optional[str]      # If voice_preference == "tts"
    recording_script: Optional[str]    # If voice_preference == "user"
```

**User Recording Workflow:**

If `voice_preference == "user"`:
1. Generate a **recording script** with clear sentence boundaries
2. Provide timing suggestions (words per minute from style profile)
3. User records their narration
4. System aligns recording to script segments using forced alignment

### 2.2 Stage 1: Transcript Cleanup (Minimal Edits)

**Principle:** The user's voice is sacred. Edits are surgical.

```python
@dataclass
class CleanupDecision:
    """A single cleanup decision for transparency."""
    location: str           # Timestamp or segment ID
    original_text: str
    action: str             # "remove_filler", "remove_restatement", "bridge_needed"
    result_text: str
    rationale: str
    elevenlabs_patch: Optional[str] = None


async def cleanup_transcript(
    transcript: TranscriptionResult,
    aligned_segments: List[AlignedSegment],
    max_changes_per_segment: int = 2
) -> Tuple[str, List[CleanupDecision]]:
    """
    Light cleanup of user recording.

    ALLOWED:
    - Remove filler words (um, uh, like-as-filler)
    - Remove false starts ("What I mean— what I'm saying is")
    - Remove long pauses (>2s)

    FORBIDDEN:
    - Changing word choices
    - Restructuring sentences
    - Adding transitions
    """
    decisions = []

    # Analyze with Claude for filler detection
    for segment in aligned_segments:
        analysis = await claude_analyze_segment(segment.transcript_segment.text)

        for issue in analysis.issues[:max_changes_per_segment]:
            if issue.type in ["filler_word", "false_start", "long_pause"]:
                decisions.append(CleanupDecision(
                    location=segment.segment_id,
                    original_text=issue.span,
                    action=issue.type,
                    result_text=issue.replacement or "",
                    rationale=issue.explanation
                ))

    return apply_decisions(transcript, decisions), decisions
```

**ElevenLabs Patching (Surgical Only):**

```python
PATCH_RULES = {
    "max_patch_duration": 2.0,           # Seconds
    "max_patch_words": 5,
    "allowed_phrases": [
        "and so", "moving on", "next", "now", "also",
        "as we'll see", "building on this"
    ],
    "voice_config": {
        "voice_id": "<male_voice_for_patching>",
        "model": "eleven_multilingual_v2",
        "stability": 0.7,
        "similarity_boost": 0.5,
        "style": 0.0  # Neutral, no drama
    }
}
```

### 2.3 Stage 2: Scene Segmentation

Leverage the training pipeline's segment analysis:

```python
@dataclass
class VideoScene:
    """A scene for video production, derived from podcast segment."""
    scene_id: str
    title: str                          # From segment key_concepts
    concept: str                        # One-sentence summary
    transcript_segment: str             # Verbatim cleaned transcript
    start_time: float
    end_time: float

    # From training pipeline
    segment_type: SegmentType
    key_concepts: List[str]
    technical_terms: List[str]
    referenced_figures: List[str]

    # Computed for visuals
    visual_complexity: str              # low, medium, high
    animation_candidate: bool
    ken_burns_enabled: bool


def segments_to_scenes(
    aligned_segments: List[AlignedSegment],
    visual_mapping: dict = SEGMENT_VISUAL_MAPPING
) -> List[VideoScene]:
    """
    Convert podcast segments to video scenes.

    Grouping rules:
    - TRANSITION segments don't create new scenes (just transition effects)
    - Adjacent segments of same type may be merged if <15s apart
    - Each scene targets 15-60 seconds
    """
    scenes = []

    for seg in aligned_segments:
        if seg.segment_type == "TRANSITION":
            continue  # Handle as transition effect

        mapping = visual_mapping.get(seg.segment_type, visual_mapping["BACKGROUND"])

        scenes.append(VideoScene(
            scene_id=f"scene_{len(scenes):03d}",
            title=seg.key_concepts[0] if seg.key_concepts else "Untitled",
            concept=summarize_segment(seg),
            transcript_segment=seg.transcript_segment.text,
            start_time=seg.transcript_segment.start_time,
            end_time=seg.transcript_segment.end_time,
            segment_type=seg.segment_type,
            key_concepts=seg.key_concepts,
            technical_terms=seg.technical_terms,
            referenced_figures=seg.referenced_figures,
            visual_complexity=mapping["visual_complexity"],
            animation_candidate=mapping["animation_candidate"],
            ken_burns_enabled=mapping["ken_burns"]
        ))

    return merge_short_scenes(scenes, min_duration=15.0)
```

### 2.4 Stage 3: Visual Planning

```python
@dataclass
class VisualPlan:
    """Complete visual plan for a scene."""
    scene_id: str

    # DALL-E configuration
    dalle_prompt: str
    dalle_style: str
    dalle_settings: Dict[str, Any]

    # Luma animation (if applicable)
    animate_with_luma: bool
    luma_prompt: Optional[str]
    luma_settings: Optional[Dict[str, Any]]

    # On-screen elements
    on_screen_text: Optional[str]
    text_position: str                  # "bottom-left", "bottom-center", etc.

    # Transitions
    transition_in: str                  # fade, cut, slide_left, zoom_in
    transition_out: str

    # Ken Burns for static images
    ken_burns: Optional[Dict[str, Any]]


async def create_visual_plan(
    scene: VideoScene,
    knowledge_graph: DocumentGraph,
    style_consistency: Dict[str, Any]   # Established in scene 0
) -> VisualPlan:
    """
    Create visual plan using scene metadata and knowledge graph.
    """

    # Generate DALL-E prompt from atoms
    dalle_prompt = generate_dalle_prompt_from_atoms(
        segment=scene,
        knowledge_graph=knowledge_graph,
        visual_mapping=SEGMENT_VISUAL_MAPPING
    )

    # Add style consistency markers
    dalle_prompt += f" {style_consistency['style_suffix']}"

    # Determine Luma animation need
    animate = (
        scene.animation_candidate and
        scene.visual_complexity in ["medium", "high"] and
        scene_benefits_from_motion(scene)
    )

    luma_prompt = None
    if animate:
        luma_prompt = generate_luma_prompt(scene)

    return VisualPlan(
        scene_id=scene.scene_id,
        dalle_prompt=dalle_prompt,
        dalle_style=SEGMENT_VISUAL_MAPPING[scene.segment_type]["dalle_style"],
        dalle_settings={
            "model": "dall-e-3",
            "size": "1792x1024",
            "quality": "hd",
            "style": style_consistency.get("dalle_style", "natural")
        },
        animate_with_luma=animate,
        luma_prompt=luma_prompt,
        luma_settings={
            "aspect_ratio": "16:9",
            "loop": False
        } if animate else None,
        on_screen_text=scene.key_concepts[0] if len(scene.key_concepts) > 0 else None,
        text_position="bottom-left",
        transition_in=select_transition(scene, "in"),
        transition_out=select_transition(scene, "out"),
        ken_burns={
            "enabled": scene.ken_burns_enabled and not animate,
            "direction": "slow_zoom_in",
            "duration_match": "scene_duration"
        }
    )


def scene_benefits_from_motion(scene: VideoScene) -> bool:
    """
    Determine if a scene's concept benefits from animation.

    True for: processes, flows, transformations, comparisons, data reveals
    False for: static concepts, definitions, simple diagrams
    """
    motion_keywords = [
        "flow", "process", "transform", "evolve", "change", "compare",
        "integrate", "combine", "adapt", "dynamic", "transition",
        "propagate", "converge", "iterate", "optimize", "adjust"
    ]

    text = " ".join(scene.key_concepts + scene.technical_terms).lower()
    return any(kw in text for kw in motion_keywords)
```

### 2.5 Stage 4: Asset Generation

```python
@dataclass
class AssetManifest:
    """Complete manifest of generated assets."""
    scenes: List[SceneAssets]
    audio_patches: List[AudioPatch]
    total_duration: float
    render_settings: Dict[str, Any]


@dataclass
class SceneAssets:
    """Assets for a single scene."""
    scene_id: str
    image_path: str                     # DALL-E output
    video_path: Optional[str]           # Luma output if animated
    display_start: float
    display_end: float
    visual_plan: VisualPlan


async def generate_assets(
    visual_plans: List[VisualPlan],
    knowledge_graph: DocumentGraph,
    output_dir: Path
) -> AssetManifest:
    """
    Generate all visual assets.

    Order:
    1. All DALL-E images (can be parallel)
    2. Luma animations using DALL-E images as seeds (sequential for keyframe chaining)
    3. Any audio patches needed
    """
    scene_assets = []

    # Phase 1: DALL-E images (parallel)
    dalle_tasks = []
    for plan in visual_plans:
        dalle_tasks.append(generate_dalle_image(plan, output_dir))

    dalle_results = await asyncio.gather(*dalle_tasks)

    # Phase 2: Luma animations (with keyframe chaining for consistency)
    previous_frame = None
    for i, plan in enumerate(visual_plans):
        if plan.animate_with_luma:
            video_path = await generate_luma_video(
                plan=plan,
                seed_image=dalle_results[i],
                previous_keyframe=previous_frame,
                output_dir=output_dir
            )
            previous_frame = extract_last_frame(video_path)
        else:
            video_path = None

        scene_assets.append(SceneAssets(
            scene_id=plan.scene_id,
            image_path=dalle_results[i],
            video_path=video_path,
            display_start=plan.display_start,
            display_end=plan.display_end,
            visual_plan=plan
        ))

    return AssetManifest(
        scenes=scene_assets,
        audio_patches=[],  # Filled from cleanup stage
        total_duration=sum(s.display_end - s.display_start for s in scene_assets),
        render_settings=DEFAULT_RENDER_SETTINGS
    )
```

### 2.6 Stage 5: Render & Composition

```python
RENDER_SETTINGS = {
    "resolution": (1920, 1080),
    "fps": 30,
    "codec": "libx264",
    "crf": 18,
    "audio_codec": "aac",
    "audio_bitrate": "192k",
    "output_format": "mp4"
}


async def render_final_video(
    user_audio: Path,
    asset_manifest: AssetManifest,
    cleanup_decisions: List[CleanupDecision],
    output_path: Path
) -> Path:
    """
    FFmpeg-based composition.

    Pipeline:
    1. Audio track: User audio + patches + crossfades
    2. Video track: Scene assets with transitions + Ken Burns
    3. Overlay: On-screen text, captions
    4. Final encode
    """

    # Step 1: Prepare audio
    patched_audio = apply_audio_patches(user_audio, cleanup_decisions)

    # Step 2: Build filter graph
    filter_graph = build_ffmpeg_filter_graph(
        scenes=asset_manifest.scenes,
        transitions=extract_transitions(asset_manifest),
        ken_burns=extract_ken_burns(asset_manifest),
        text_overlays=extract_text_overlays(asset_manifest)
    )

    # Step 3: Execute FFmpeg
    cmd = [
        "ffmpeg",
        "-i", str(patched_audio),
        *build_input_args(asset_manifest.scenes),
        "-filter_complex", filter_graph,
        "-map", "[vout]",
        "-map", "0:a",
        "-c:v", RENDER_SETTINGS["codec"],
        "-crf", str(RENDER_SETTINGS["crf"]),
        "-c:a", RENDER_SETTINGS["audio_codec"],
        "-b:a", RENDER_SETTINGS["audio_bitrate"],
        str(output_path)
    ]

    await run_ffmpeg(cmd)
    return output_path
```

---

## Part 3: CLI Integration

### 3.1 New Command: `produce-video`

```bash
# Full pipeline from paper
claude-studio produce-video paper.pdf --depth standard --record

# From existing podcast script
claude-studio produce-video --script podcast_script.txt --audio recording.wav

# Using training output directly
claude-studio produce-video --from-training trial_000_20260201_192220
```

### 3.2 Implementation

```python
@click.command("produce-video")
@click.argument("paper", type=click.Path(exists=True), required=False)
@click.option("--depth", type=click.Choice(["overview", "standard", "deep_dive"]), default="standard")
@click.option("--record/--tts", default=True, help="Record yourself or use TTS")
@click.option("--script", type=click.Path(exists=True), help="Use existing script")
@click.option("--audio", type=click.Path(exists=True), help="Use existing audio recording")
@click.option("--from-training", type=str, help="Use training trial output")
@click.option("--style", type=str, default="default", help="Visual style preset")
@click.option("--output", "-o", type=click.Path(), default="output.mp4")
@click.option("--live/--mock", default=False, help="Use real APIs vs mock")
def produce_video(paper, depth, record, script, audio, from_training, style, output, live):
    """
    Produce an explainer video from a scientific paper.

    Three input modes:
    1. Paper path: Full pipeline (script generation → visual production)
    2. --script + --audio: Visual production only
    3. --from-training: Use existing training trial output
    """
    asyncio.run(_produce_video_async(
        paper=paper,
        depth=depth,
        record=record,
        script_path=script,
        audio_path=audio,
        training_trial=from_training,
        style=style,
        output_path=output,
        live=live
    ))
```

---

## Part 4: Testing with Existing Training Output

### 4.1 Available Test Case

We have a complete training trial ready for testing:

```
artifacts/training_output/trial_000_20260201_192220/
├── aerial-vehicle-positioning-full_script.txt   # Generated script (~3000 words)
└── results.json                                  # Loss metrics

artifacts/training_output/checkpoints/
├── aerial-vehicle-positioning-full_analysis.json    # 162 aligned segments
├── aerial-vehicle-positioning-full_transcription.json
└── aerial-vehicle-positioning-full_knowledge_graph.json
```

### 4.2 Test Execution

```bash
# Mock mode test (no API costs)
claude-studio produce-video --from-training trial_000_20260201_192220 --mock -o test_video.mp4

# With TTS audio generation
claude-studio produce-video --from-training trial_000_20260201_192220 --tts -o test_video.mp4

# Live mode with all providers
claude-studio produce-video --from-training trial_000_20260201_192220 --live -o test_video.mp4
```

### 4.3 Expected Output Scenes

Based on the analysis checkpoint (162 segments), the test video would have approximately:

| Segment Type | Count (est.) | Animation | Visual Style |
|--------------|--------------|-----------|--------------|
| INTRO | 5-8 | No | Abstract, title card |
| BACKGROUND | 15-20 | No | Conceptual illustration |
| PROBLEM_STATEMENT | 8-12 | Yes | Technical diagram |
| METHODOLOGY | 25-35 | Yes | Architectural diagram |
| KEY_FINDING | 20-25 | Yes | Data visualization |
| IMPLICATION | 10-15 | Yes | Real-world application |
| CONCLUSION | 3-5 | No | Summary visual |

After merging short segments: ~30-40 distinct scenes, ~10-15 with Luma animation.

### 4.4 Validation Metrics

```python
@dataclass
class VideoQualityMetrics:
    """Metrics for evaluating produced video."""

    # Timing alignment
    audio_visual_sync_error: float      # Mean deviation in seconds
    scene_coverage: float               # % of audio covered by visuals

    # Visual quality (Claude Vision analysis)
    visual_relevance_score: float       # 0-100, concept match
    style_consistency_score: float      # 0-100, visual coherence
    animation_appropriateness: float    # 0-100, motion adds value

    # Production quality
    transition_smoothness: float        # 0-100, no jarring cuts
    text_readability: float             # 0-100, overlays legible

    # Overall
    total_score: float                  # Weighted average
```

---

## Part 5: Implementation Phases

### Phase 1: Core Pipeline (Week 1)
- [ ] `VideoScene` dataclass and segment-to-scene conversion
- [ ] DALL-E prompt generation from segments
- [ ] Basic visual plan creation
- [ ] Mock asset generation

### Phase 2: Asset Generation (Week 2)
- [ ] DALL-E integration (reuse existing provider)
- [ ] Luma integration with keyframe chaining
- [ ] Ken Burns effect implementation
- [ ] Transition effect library

### Phase 3: Composition (Week 3)
- [ ] FFmpeg filter graph builder
- [ ] Audio patch integration
- [ ] Text overlay system
- [ ] Final render pipeline

### Phase 4: CLI & Testing (Week 4)
- [ ] `produce-video` command
- [ ] `--from-training` mode
- [ ] Quality metrics evaluation
- [ ] Integration with training loop

---

## Part 6: Integration with Training Loop

### 6.1 Video Quality as Training Signal

Add video production quality to the training loss:

```python
EXTENDED_LOSS_WEIGHTS = {
    "duration": 0.20,
    "coverage": 0.20,
    "structure": 0.00,
    "quality": 0.20,
    "rouge": 0.10,
    "video_relevance": 0.15,     # NEW: Visual-concept alignment
    "video_consistency": 0.15,   # NEW: Style coherence
}
```

### 6.2 Feedback Loop

```
Training Loop Extended:

1. Generate script from paper
2. Produce video from script (mock visuals)
3. Evaluate video quality metrics
4. Combine with existing loss metrics
5. Refine prompts based on which segments produced weak visuals
6. Repeat
```

This creates a virtuous cycle: scripts improve not just for audio quality but for visual producibility.

---

## Appendix A: Style Presets

```python
STYLE_PRESETS = {
    "technical": {
        "dalle_style": "natural",
        "background": "dark (#1a1a2e)",
        "accent_colors": ["#00d4ff", "#ff6b6b", "#4ecdc4"],
        "typography": "IBM Plex Mono",
        "animation_intensity": "subtle"
    },
    "educational": {
        "dalle_style": "vivid",
        "background": "warm white (#f8f9fa)",
        "accent_colors": ["#667eea", "#764ba2", "#f093fb"],
        "typography": "Nunito",
        "animation_intensity": "moderate"
    },
    "documentary": {
        "dalle_style": "natural",
        "background": "cinematic dark (#0d0d0d)",
        "accent_colors": ["#ffd700", "#c0c0c0", "#ffffff"],
        "typography": "Crimson Pro",
        "animation_intensity": "dramatic"
    }
}
```

---

## Appendix B: FFmpeg Examples

### Ken Burns Effect

```bash
ffmpeg -loop 1 -i scene.png -t 10 \
  -vf "scale=8000:-1,zoompan=z='min(zoom+0.0005,1.2)':d=300:s=1920x1080:fps=30" \
  -c:v libx264 -pix_fmt yuv420p scene_kb.mp4
```

### Crossfade Transition

```bash
ffmpeg -i scene1.mp4 -i scene2.mp4 \
  -filter_complex "
    [0:v]fade=t=out:st=9:d=1[v0];
    [1:v]fade=t=in:st=0:d=1[v1];
    [v0][v1]concat=n=2:v=1:a=0[v]
  " \
  -map "[v]" combined.mp4
```

### Text Overlay

```bash
ffmpeg -i scene.mp4 \
  -vf "drawtext=text='Key Concept':fontfile=font.ttf:fontsize=48:fontcolor=white:x=100:y=h-100" \
  scene_text.mp4
```
