# Unified Production Architecture

> Status: Ready for Implementation
> Priority: Critical — blocks all further video production work
> Depends on: TRANSCRIPT_LED_VIDEO_PRODUCTION.md, ASSET_TRACKING_WORKFLOW.md, VIDEO_ASSEMBLY_ARCHITECTURE.md
> Date: February 7, 2026

## Executive Summary

We have two pipelines that need to merge:

- **Pipeline A (original):** Video-forward — Producer → ScriptWriter → VideoGenerator → QA → Critic → Editor. Thinks in Scenes, EDLs, and competitive pilots.
- **Pipeline B (current):** Audio-first, transcript-led — PDF → KB → DocumentGraph → Training → Script → Audio → Images → Rough Cut. Thinks in paragraphs, visual_plans, and asset_manifests.

Neither pipeline has a shared intermediate representation. The script is flat text. Assets are generated per-run with no registry. Figure timing is broken. This spec defines three new components that unify everything:

1. **Structured Script** — the single source of truth both pipelines read from
2. **Content Library** — persistent registry of all approved assets with metadata
3. **Agent Role Clarification** — who reads/writes what, with contracts CC can implement independently

## Problem Statement

### What's Broken Right Now

1. **Script is flat text.** `_script.txt` has 45 paragraphs but no structured metadata — no figure refs, no visual intent, no segment classification. Everything downstream has to guess.

2. **Reference segments ≠ generated paragraphs.** The training pipeline produces 162 Whisper segments from the reference podcast. The script generator produces 45 new paragraphs. `produce-video` loads `aligned_segments` (162 reference scenes) but generates audio from the 45 script paragraphs. There's no mapping between them.

3. **Figure assignment uses the wrong structure.** `kb_figure_path` is assigned to scenes derived from reference segments via keyword matching. But the generated script mentions figures explicitly ("Figure 6 shows..."). Nobody parses those mentions for assembly.

4. **No asset reuse across runs.** Each `produce-video` run generates everything from scratch. The 45 approved audio clips from run `20260207_101747` can't be formally carried into a new run that regenerates only images.

5. **Two incompatible data models.** The original pipeline uses `Scene`, `EDL`, `GeneratedVideo`, `QAResult`. The transcript-led pipeline uses `visual_plans.json`, `asset_manifest.json`, paragraphs. They don't share types.

6. **CC context collapse.** The system is too large for CC to hold in context. It needs modular contracts — each component defined by what it reads and writes, not by understanding the whole pipeline.

---

## Architecture Overview

```
                    ┌─────────────────────────────┐
                    │       KNOWLEDGE BASE         │
                    │  DocumentGraph, figures,      │
                    │  atoms, topics, entities      │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │     STRUCTURED SCRIPT         │
                    │  (Single Source of Truth)      │
                    │                               │
                    │  segments[] with:             │
                    │   - text (narration)          │
                    │   - intent (intro/figure/etc) │
                    │   - figure_refs               │
                    │   - visual_direction          │
                    │   - key_concepts              │
                    └──────┬───────────┬───────────┘
                           │           │
                    ┌──────▼──┐  ┌─────▼──────────┐
                    │  AUDIO  │  │  VISUAL         │
                    │PRODUCER │  │  PRODUCER       │
                    │         │  │  (DoP + gen)    │
                    └────┬────┘  └────┬────────────┘
                         │            │
                         ▼            ▼
                    ┌──────────────────────────────┐
                    │      CONTENT LIBRARY          │
                    │  (Librarian manages)          │
                    │                               │
                    │  Registered assets with:      │
                    │   - metadata & provenance     │
                    │   - approval status           │
                    │   - segment associations      │
                    │   - reuse across runs         │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │       ASSEMBLY MANIFEST       │
                    │  paragraph → audio + visual   │
                    │  with figure sync points      │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │     EDITOR / RENDERER         │
                    │  FFmpeg assembly from manifest │
                    └──────────────────────────────┘
```

---

## Component 1: Structured Script

### What It Is

A JSON document that replaces `_script.txt` as the primary output of script generation. Both audio production and visual production read from it. It preserves the full intent of each segment so downstream agents don't have to guess.

### Schema

```python
# File: core/models/structured_script.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class SegmentIntent(Enum):
    """What this segment IS — drives visual and pacing decisions."""
    INTRO = "intro"
    BACKGROUND = "background"
    METHODOLOGY = "methodology"
    KEY_FINDING = "key_finding"
    FIGURE_WALKTHROUGH = "figure_walkthrough"
    DATA_DISCUSSION = "data_discussion"
    COMPARISON = "comparison"
    TRANSITION = "transition"
    RECAP = "recap"
    OUTRO = "outro"


@dataclass
class ScriptSegment:
    """A single segment of the structured script."""
    idx: int
    text: str                                   # Narration text
    intent: SegmentIntent                       # What this segment does
    figure_refs: List[int] = field(default_factory=list)  # "Figure N" mentions
    key_concepts: List[str] = field(default_factory=list)
    visual_direction: str = ""                  # DoP annotation
    estimated_duration_sec: Optional[float] = None  # After TTS
    importance_score: float = 0.5               # For budget allocation

    # Populated after audio generation
    audio_file: Optional[str] = None
    actual_duration_sec: Optional[float] = None

    # Populated after visual assignment
    visual_asset_id: Optional[str] = None
    display_mode: Optional[str] = None          # "figure_sync", "dall_e", "carry_forward"


@dataclass
class FigureInventory:
    """Figures available from the KB for this script."""
    figure_number: int                          # The "Figure N" number
    kb_path: str                                # Path to extracted figure image
    caption: str
    description: str                            # LLM-generated description
    discussed_in_segments: List[int] = field(default_factory=list)


@dataclass
class StructuredScript:
    """The single source of truth for a production."""
    script_id: str                              # e.g., "trial_000_v1"
    trial_id: str
    version: int = 1

    segments: List[ScriptSegment] = field(default_factory=list)
    figure_inventory: Dict[int, FigureInventory] = field(default_factory=dict)

    # Metadata
    total_segments: int = 0
    total_estimated_duration_sec: float = 0.0
    source_document: Optional[str] = None       # KB source
    generation_prompt: Optional[str] = None      # What Claude was asked

    def get_figure_segments(self) -> List[ScriptSegment]:
        """Return segments that reference figures."""
        return [s for s in self.segments if s.figure_refs]

    def get_segments_by_intent(self, intent: SegmentIntent) -> List[ScriptSegment]:
        return [s for s in self.segments if s.intent == intent]

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        ...

    @classmethod
    def from_dict(cls, data: dict) -> 'StructuredScript':
        """Deserialize from JSON."""
        ...

    @classmethod
    def from_script_text(cls, script_text: str, trial_id: str,
                         kb_figures: Optional[Dict] = None) -> 'StructuredScript':
        """
        Parse a flat _script.txt into a StructuredScript.
        This is the migration path from the current pipeline.

        1. Split into paragraphs
        2. Regex for "Figure N" mentions
        3. Classify intent via heuristics or LLM call
        4. Map figure refs to kb_figure_paths
        """
        ...
```

### File Output

```
artifacts/training_output/{trial_id}/
├── {trial_id}_script.txt              # Existing flat text (kept for compat)
├── {trial_id}_structured_script.json  # NEW: structured script
└── ...
```

### How It Gets Created

**Option A (preferred): Script generation produces it directly.**
Modify `core/training/trainer.py` so Claude outputs structured JSON instead of flat text. The prompt already includes figure context — we just need to ask for structured output.

**Option B (migration): Post-process existing `_script.txt`.**
Use `StructuredScript.from_script_text()` to parse flat text into the structured format. This is the backwards-compatible path for existing trials.

### Integration Points

| Consumer | What It Reads | Why |
|----------|--------------|-----|
| Audio Producer | `segments[].text` | Generate TTS per segment |
| Visual Producer (DoP) | `segments[].intent`, `figure_refs`, `visual_direction` | Decide what image/video to show |
| Assembly Manifest Builder | `segments[]` with audio + visual assignments | Build timed assembly |
| Asset Tracking | `segments[]` with asset IDs | Track approval per segment |
| Budget Allocator | `segments[].importance_score`, `intent` | Decide which segments get DALL-E images |

---

## Component 2: Content Library

### What It Is

A persistent registry of all generated and extracted assets. The Librarian (agent or module) manages registration, deduplication, metadata, and approval status. Any agent can query the library to check what exists before generating something new.

### Directory Structure

```
artifacts/content_library/
├── library.json                    # Master index
├── audio/                          # Audio clips (TTS outputs)
│   ├── aud_001.mp3
│   └── ...
├── images/                         # Generated images (DALL-E, etc.)
│   ├── img_001.png
│   └── ...
├── figures/                        # KB-extracted figures (symlinks or copies)
│   ├── fig_001.png
│   └── ...
├── videos/                         # Generated video clips (Luma, Runway, etc.)
│   ├── vid_001.mp4
│   └── ...
└── metadata/                       # Per-asset metadata JSONs
    ├── aud_001.json
    ├── img_001.json
    └── ...
```

### Asset Record Schema

```python
# File: core/models/content_library.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
from datetime import datetime


class AssetType(Enum):
    AUDIO = "audio"
    IMAGE = "image"
    FIGURE = "figure"           # KB-extracted, not generated
    VIDEO = "video"


class AssetStatus(Enum):
    DRAFT = "draft"             # Just generated, not reviewed
    REVIEW = "review"           # Flagged for human review
    APPROVED = "approved"       # Good to use
    REJECTED = "rejected"       # Not usable (with reason)
    REVISED = "revised"         # Regenerated after rejection


class AssetSource(Enum):
    DALLE = "dalle"
    ELEVENLABS = "elevenlabs"
    OPENAI_TTS = "openai_tts"
    GOOGLE_TTS = "google_tts"
    LUMA = "luma"
    RUNWAY = "runway"
    KB_EXTRACTION = "kb_extraction"
    FFMPEG = "ffmpeg"           # Processed/composited
    MANUAL = "manual"           # User-provided


@dataclass
class AssetRecord:
    """A registered asset in the content library."""
    asset_id: str                               # e.g., "aud_001", "img_fig6_v2"
    asset_type: AssetType
    source: AssetSource
    status: AssetStatus = AssetStatus.DRAFT

    # File info
    path: str = ""                              # Relative to content_library/
    file_size_bytes: int = 0
    format: str = ""                            # "mp3", "png", "mp4"

    # Content description
    describes: str = ""                         # What this asset shows/says
    tags: List[str] = field(default_factory=list)

    # For audio
    text_content: Optional[str] = None          # The narration text
    voice: Optional[str] = None                 # Voice name/ID
    duration_sec: Optional[float] = None

    # For images/figures
    prompt: Optional[str] = None                # DALL-E prompt used
    figure_number: Optional[int] = None         # If KB figure
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    # Segment associations
    used_in_segments: List[int] = field(default_factory=list)
    script_id: Optional[str] = None

    # Provenance
    origin_run_id: Optional[str] = None
    generated_at: Optional[str] = None
    generated_by: Optional[str] = None          # Agent that created it
    generation_cost: float = 0.0

    # Review
    approved_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    revision_of: Optional[str] = None           # asset_id this revises
    notes: str = ""


@dataclass
class ContentLibrary:
    """The master content library for a project."""
    project_id: str
    assets: Dict[str, AssetRecord] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def register(self, record: AssetRecord) -> str:
        """Register a new asset. Returns asset_id."""
        ...

    def get(self, asset_id: str) -> Optional[AssetRecord]:
        ...

    def query(self,
              asset_type: Optional[AssetType] = None,
              status: Optional[AssetStatus] = None,
              segment_idx: Optional[int] = None,
              figure_number: Optional[int] = None,
              tags: Optional[List[str]] = None) -> List[AssetRecord]:
        """Query assets by criteria."""
        ...

    def approve(self, asset_id: str) -> None:
        ...

    def reject(self, asset_id: str, reason: str) -> None:
        ...

    def has_approved_asset_for(self, segment_idx: int,
                                asset_type: AssetType) -> bool:
        """Check if we already have an approved asset for a segment."""
        ...

    def get_approved_for_segment(self, segment_idx: int,
                                  asset_type: AssetType) -> Optional[AssetRecord]:
        """Get the approved asset for a segment, if one exists."""
        ...

    def save(self, path: str = "artifacts/content_library/library.json") -> None:
        ...

    @classmethod
    def load(cls, path: str = "artifacts/content_library/library.json") -> 'ContentLibrary':
        ...

    @classmethod
    def from_asset_manifest_v1(cls, manifest_path: str) -> 'ContentLibrary':
        """
        Migrate from existing asset_manifest.json format.
        This is the backwards-compatible upgrade path.
        """
        ...
```

### Librarian Module

The Librarian is NOT a full agent (no LLM calls needed). It's a utility module that other agents call.

```python
# File: core/content_librarian.py

class ContentLibrarian:
    """Manages the content library. Called by other agents, not an LLM agent itself."""

    def __init__(self, library: ContentLibrary):
        self.library = library

    def register_audio_from_run(self, run_dir: str, script: StructuredScript) -> List[str]:
        """
        Scan a run's audio/ directory, register all clips.
        Associates each clip with its script segment.
        Returns list of asset_ids.
        """
        ...

    def register_images_from_run(self, run_dir: str, script: StructuredScript) -> List[str]:
        """
        Scan a run's images/ directory, register all images.
        Returns list of asset_ids.
        """
        ...

    def register_kb_figures(self, kb_path: str, script: StructuredScript) -> List[str]:
        """
        Register KB figures referenced in the script.
        Copies/symlinks them into the library.
        Returns list of asset_ids.
        """
        ...

    def import_approved_from_run(self, source_run_id: str,
                                  asset_type: Optional[AssetType] = None) -> List[str]:
        """
        Import approved assets from a previous run into the library.
        This enables reuse across runs.
        """
        ...

    def get_generation_plan(self, script: StructuredScript,
                            asset_type: AssetType) -> List[int]:
        """
        Given a script, return which segment indices NEED new assets generated.
        Excludes segments that already have approved assets in the library.
        This is how we avoid regenerating approved content.
        """
        segments_needing_assets = []
        for seg in script.segments:
            if not self.library.has_approved_asset_for(seg.idx, asset_type):
                segments_needing_assets.append(seg.idx)
        return segments_needing_assets

    def build_assembly_manifest(self, script: StructuredScript) -> dict:
        """
        Build the assembly manifest from the script + library.
        Maps each segment to its audio and visual assets.
        Marks figure sync points.
        """
        ...
```

---

## Component 3: Agent Roles & Contracts

Each role is defined by what it **reads** and **writes**. CC can implement each one independently by following its contract.

### Script Writer (Audio Side)

```
READS:  KB DocumentGraph, figure inventory, training style profile
WRITES: StructuredScript (segments with text, intent, figure_refs, key_concepts)
FILE:   core/training/trainer.py (modify generate_script step)
```

**Change required:** Instead of writing `_script.txt`, produce `_structured_script.json`. The flat text file can still be generated from the structured script for backward compatibility.

### Director of Photography (DoP)

```
READS:  StructuredScript, ContentLibrary (what assets exist), budget tier
WRITES: StructuredScript.segments[].visual_direction, display_mode, visual_asset_id
FILE:   NEW — core/dop.py (or integrate into produce_video.py)
```

**What it does:**
1. Reads each segment's intent, figure_refs, and key_concepts
2. Checks the content library for existing approved visuals
3. Assigns `display_mode` per segment: `figure_sync`, `dall_e`, `carry_forward`, `text_only`
4. Writes `visual_direction` hints for DALL-E prompt generation
5. Links existing approved assets via `visual_asset_id` (reuse without regeneration)
6. Respects budget tier ratios (medium = 27% get DALL-E images)

This can start as a deterministic function (no LLM needed) and graduate to an agent later.

### Audio Producer

```
READS:  StructuredScript.segments[].text
WRITES: Audio files, registers in ContentLibrary, segments[].actual_duration_sec, segments[].audio_file
FILE:   cli/produce_video.py (generate_scene_audio function)
```

**Implementation:** When `structured_script` is provided, iterates over `segments[].text` (not flat text split by `\n\n`). Registers each audio asset immediately in ContentLibrary and writes `actual_duration_sec` back to the segment. Uses `mutagen` to get actual MP3 duration.

### Visual Producer

```
READS:  StructuredScript (with DoP annotations), ContentLibrary
WRITES: Image/video files + registers them in ContentLibrary
FILE:   cli/produce_video.py (existing image generation logic)
```

**Change required:** Before generating, call `librarian.get_generation_plan()` to skip segments with approved assets. After generating, register new assets.

### Editor / Assembler

```
READS:  StructuredScript (with audio + visual assignments), ContentLibrary
WRITES: Assembly manifest, rough_cut.mp4
FILE:   scripts/assemble_rough_cut.py (or new cli/assemble.py)
```

**Change required:** Use `librarian.build_assembly_manifest()` instead of even-distributing images. Respect figure sync points.

### Summary Table

| Role | Reads | Writes | Existing File | Change Type |
|------|-------|--------|---------------|-------------|
| Script Writer | KB, figures, style | StructuredScript | `core/training/trainer.py` | Modify output format |
| DoP | StructuredScript, Library, budget | Visual assignments | NEW `core/dop.py` | New module |
| Audio Producer | StructuredScript segments | Audio files, Library entries | `cli/produce_video.py` | Add library registration |
| Visual Producer | StructuredScript + DoP, Library | Image files, Library entries | `cli/produce_video.py` | Add library check + registration |
| Librarian | All outputs | ContentLibrary | NEW `core/content_librarian.py` | New module |
| Editor | StructuredScript, Library | Assembly manifest, video | `scripts/assemble_rough_cut.py` | Rewrite assembly logic |

---

## Implementation Plan

### Phase 1: Data Models (no pipeline changes)

**Goal:** Define the new types. Nothing breaks.

1. Create `core/models/structured_script.py` with `StructuredScript`, `ScriptSegment`, `SegmentIntent`, `FigureInventory`
2. Create `core/models/content_library.py` with `ContentLibrary`, `AssetRecord`, enums
3. Add `StructuredScript.from_script_text()` — parser for existing `_script.txt` files
4. Add `ContentLibrary.from_asset_manifest_v1()` — migration from existing manifests
5. Tests: roundtrip serialization, parser correctness on actual trial output

**Files to create:**
- `core/models/structured_script.py`
- `core/models/content_library.py`
- `tests/test_structured_script.py`
- `tests/test_content_library.py`

**CC task prompt:** "Read the StructuredScript and ContentLibrary schemas from docs/specs/UNIFIED_PRODUCTION_ARCHITECTURE.md (Component 1 and Component 2). Implement the data models with full serialization. Test with the existing trial data in artifacts/training_output/."

### Phase 2: Content Librarian module

**Goal:** Asset registration and querying works.

1. Create `core/content_librarian.py`
2. Implement `register_audio_from_run()`, `register_images_from_run()`, `register_kb_figures()`
3. Implement `get_generation_plan()` and `build_assembly_manifest()`
4. Tests: register assets from existing run directories, verify query results

**Files to create:**
- `core/content_librarian.py`
- `tests/test_content_librarian.py`

**CC task prompt:** "Read the ContentLibrarian class spec from docs/specs/UNIFIED_PRODUCTION_ARCHITECTURE.md. Implement it using the ContentLibrary model from Phase 1. Test against existing run data at artifacts/video_production/20260207_101747/."

### Phase 3: Script generation produces StructuredScript

**Goal:** Training pipeline outputs structured script instead of flat text.

1. Modify `core/training/trainer.py` — change script generation prompt to request structured output
2. Parse Claude's response into `StructuredScript`
3. Save as `{trial_id}_structured_script.json`
4. Keep `_script.txt` for backward compatibility (generated from structured script)

**Files to modify:**
- `core/training/trainer.py`

**CC task prompt:** "In core/training/trainer.py, modify the script generation step. The prompt already includes figure context. Change it to ask Claude to output JSON matching the StructuredScript schema. Parse the response and save as {trial_id}_structured_script.json. Also save the flat text version for backward compat."

### Phase 4: DoP + produce-video integration

**Goal:** Visual assignment uses structured script. Library integration.

1. Create `core/dop.py` with `assign_visuals()` function
2. Modify `cli/produce_video.py`:
   - Load `StructuredScript` (or create from `_script.txt` via migration)
   - Call DoP for visual assignment
   - Call `librarian.get_generation_plan()` before generating
   - Register generated assets with librarian
3. Modify audio generation to write back `actual_duration_sec` to script

**Files to create/modify:**
- `core/dop.py` (new)
- `cli/produce_video.py` (modify)

**CC task prompt:** "Read the DoP and integration specs from docs/specs/UNIFIED_PRODUCTION_ARCHITECTURE.md Phase 4. Create core/dop.py. Then modify cli/produce_video.py to: 1) load StructuredScript, 2) call DoP for visual assignment, 3) use librarian to check for existing assets before generating, 4) register new assets after generation."

### Phase 5: Timed assembly

**Goal:** Rough cut respects figure sync points.

1. Modify `scripts/assemble_rough_cut.py` (or create `cli/assemble.py`)
2. Load assembly manifest from librarian
3. For each segment: get audio + visual from library
4. Figure sync segments: show KB figure when narration mentions it
5. DALL-E segments: Ken Burns effect
6. Carry-forward segments: hold previous image

**Files to create/modify:**
- `scripts/assemble_rough_cut.py` or new `cli/assemble.py`

**CC task prompt:** "Read the assembly spec from docs/specs/UNIFIED_PRODUCTION_ARCHITECTURE.md Phase 5 and VIDEO_ASSEMBLY_ARCHITECTURE.md. Rewrite the rough cut assembly to use the assembly manifest from ContentLibrarian.build_assembly_manifest(). Key requirement: Figure N segments must show the KB figure exactly when the narration discusses it."

### Phase 6: Asset tracking CLI

**Goal:** CLI for reviewing, approving, rejecting assets.

1. Create `cli/assets.py` with Click commands
2. Wire into `cli/__main__.py`
3. Implement: `assets list`, `assets approve`, `assets reject`, `assets regen`, `assets build`

**Files to create/modify:**
- `cli/assets.py` (new)
- `cli/__main__.py` (add asset commands)

**CC task prompt:** "Read ASSET_TRACKING_WORKFLOW.md and the ContentLibrary model from docs/specs/UNIFIED_PRODUCTION_ARCHITECTURE.md. Implement the CLI commands in cli/assets.py using Click + Rich (matching the existing CLI style). Wire into cli/__main__.py."

---

## Migration Strategy

### Existing Data

| Artifact | Location | Migration |
|----------|----------|-----------|
| Flat script | `{trial}_script.txt` | `StructuredScript.from_script_text()` — auto-parse |
| Audio clips | `20260207_101747/audio/` | `librarian.register_audio_from_run()` |
| Images | `20260207_104648/images/` | `librarian.register_images_from_run()` |
| KB figures | `kb_87a368725eca/sources/.../figures/` | `librarian.register_kb_figures()` |
| Asset manifest v1 | `asset_manifest.json` | `ContentLibrary.from_asset_manifest_v1()` |

### Backward Compatibility

- `produce-video` continues to work without a structured script — it auto-migrates `_script.txt` if no `_structured_script.json` exists
- Existing `asset_manifest.json` files are auto-upgraded on first `assets` command
- `_script.txt` continues to be generated alongside the structured script
- Old runs can be imported into the library retroactively

---

## How This Connects to the Original Agent Pipeline

The original `produce` command (Pipeline A) uses the agent chain: Producer → ScriptWriter → VideoGenerator → QA → Critic → Editor. This architecture doesn't replace that — it provides the data layer both pipelines share.

```
Original Pipeline (claude-studio produce):
  ScriptWriter  → could output StructuredScript instead of Scene list
  VideoGenerator → registers assets in ContentLibrary
  QA/Critic     → updates asset status (approve/reject)
  Editor        → reads ContentLibrary to build EDL

Transcript Pipeline (claude-studio produce-video):
  Trainer       → outputs StructuredScript
  DoP           → annotates visual assignments
  produce-video → generates assets, registers in library
  Assembler     → builds rough cut from library

SHARED: StructuredScript schema, ContentLibrary, ContentLibrarian
```

Future work can have the original agents read/write these same types, fully unifying the pipelines. But that's Phase 7+, not a blocker.

---

## CC Working Instructions

### Before Starting Any Phase

1. Read THIS spec (the relevant phase section only)
2. Check what exists: `grep -r "class.*Script\|class.*Asset\|class.*Library" core/models/`
3. Run existing tests: `pytest tests/ -x`

### After Completing Any Phase

1. `python -m py_compile <file>` for every file you touched
2. `pytest tests/ -x`
3. Update `CLAUDE.md` "Current State" section with what you built
4. Add a brief entry to `docs/dev_notes.md`

### Context Management

Each phase is designed to be implementable with ONLY:
- This spec (the relevant phase section)
- The files listed in that phase
- The data model files from Phase 1

You do NOT need to read the entire codebase. Use `grep` and `codebase-scout` to find specific integration points.

---

## Appendix: Current File Map

For CC orientation — which files matter for this work:

```
core/
├── models/
│   ├── structured_script.py     # NEW Phase 1
│   ├── content_library.py       # NEW Phase 1
│   ├── video_production.py      # Existing — has Scene, VisualPlan types
│   └── knowledge.py             # Existing — has DocumentAtom, KnowledgeGraph
├── training/
│   └── trainer.py               # MODIFY Phase 3 — script generation
├── content_librarian.py         # NEW Phase 2
├── dop.py                       # NEW Phase 4
├── video_production.py          # Existing — figure matching logic
└── providers/                   # No changes needed

cli/
├── produce_video.py             # MODIFY Phase 4 — main pipeline
├── assets.py                    # NEW Phase 6
└── __main__.py                  # MODIFY Phase 6 — add commands

scripts/
└── assemble_rough_cut.py        # MODIFY Phase 5 — timed assembly

artifacts/
├── training_output/             # Trial outputs with scripts
├── video_production/            # Run outputs with audio/images
├── content_library/             # NEW — persistent asset registry
└── kb/                          # Knowledge base with figures
```
