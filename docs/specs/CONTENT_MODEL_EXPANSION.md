# Content Model Expansion

> Status: Ready for Implementation
> Priority: High — apply after UNIFIED_PRODUCTION_ARCHITECTURE Phase 1
> Depends on: UNIFIED_PRODUCTION_ARCHITECTURE.md (data models)
> Date: February 7, 2026

## Purpose

The initial StructuredScript model in UNIFIED_PRODUCTION_ARCHITECTURE.md was designed around a single content type: academic paper → podcast explainer. But Claude Studio Producer needs to support arbitrary source combinations:

- A news article + two scientific papers + a government dataset → video essay
- A news abstract → left (0.2) and right (0.8) bias variants → comparison video
- Multiple papers on a topic → adversarial debate → synthesis

This spec replaces the `SegmentIntent` enum and expands `ScriptSegment` to be content-type agnostic and multi-source aware. It's a drop-in replacement for the types defined in `core/models/structured_script.py`.

---

## SegmentIntent: What the Segment DOES

The old enum described what section of a paper the content came from (METHODOLOGY, KEY_FINDING). The new enum describes what the segment does *in the narrative*. This works regardless of whether the source is Nature, the AP wire, or a CSV from data.gov.

```python
# In core/models/structured_script.py — replace existing SegmentIntent

class SegmentIntent(Enum):
    """
    What this segment DOES in the narrative.
    Content-type agnostic — works for papers, news, datasets, mixed sources.
    """

    # === Structural ===
    # These control pacing and flow, not content.
    INTRO = "intro"                         # Opening hook, topic framing
    TRANSITION = "transition"               # Bridge between topics or segments
    RECAP = "recap"                         # Summary of what was covered
    OUTRO = "outro"                         # Closing, call to action, sign-off

    # === Exposition ===
    # Segments that teach, explain, or set the scene.
    CONTEXT = "context"                     # Background, history, setting the scene
    EXPLANATION = "explanation"             # Breaking down a concept or process
    DEFINITION = "definition"              # Defining terms, scope, or frameworks
    NARRATIVE = "narrative"                 # Storytelling, anecdote, timeline of events

    # === Evidence & Data ===
    # Segments that present facts, numbers, or artifacts.
    CLAIM = "claim"                         # Presenting an assertion or finding
    EVIDENCE = "evidence"                   # Supporting a claim with data/quotes/citations
    DATA_WALKTHROUGH = "data_walkthrough"   # Walking through numbers, charts, datasets
    FIGURE_REFERENCE = "figure_reference"   # Discussing a specific visual artifact

    # === Analysis & Perspective ===
    # Segments that interpret, compare, or challenge.
    ANALYSIS = "analysis"                   # Interpreting evidence, drawing conclusions
    COMPARISON = "comparison"               # Contrasting sources, methods, viewpoints
    COUNTERPOINT = "counterpoint"           # Presenting opposing view or challenge
    SYNTHESIS = "synthesis"                 # Combining multiple sources into new insight

    # === Editorial ===
    # Segments with a point of view.
    COMMENTARY = "commentary"               # Host/narrator opinion or editorial voice
    QUESTION = "question"                   # Posing a question to the audience
    SPECULATION = "speculation"             # Forward-looking, hypothetical, what-if
```

### How Intents Map to Content Types

The same intent vocabulary works across all production types:

| Content Type | Typical Intent Sequence |
|---|---|
| **Paper explainer** | INTRO → CONTEXT → EXPLANATION → FIGURE_REFERENCE → EVIDENCE → CLAIM → ANALYSIS → RECAP → OUTRO |
| **News bias analysis** | INTRO → NARRATIVE → CLAIM → EVIDENCE → COUNTERPOINT → COMPARISON → COMMENTARY → OUTRO |
| **Dataset exploration** | INTRO → CONTEXT → DATA_WALKTHROUGH → CLAIM → ANALYSIS → SPECULATION → OUTRO |
| **Multi-source synthesis** | INTRO → CONTEXT → CLAIM (source A) → EVIDENCE (source B) → COUNTERPOINT (source C) → SYNTHESIS → COMMENTARY → OUTRO |
| **Adversarial debate** | INTRO → CLAIM → EVIDENCE → COUNTERPOINT → EVIDENCE → COMPARISON → SYNTHESIS → OUTRO |

### How Intents Drive Visual Decisions

The DoP uses intent to decide what to show. This mapping is deterministic and doesn't depend on content type:

| Intent | Default Visual Strategy |
|---|---|
| INTRO | Title card or establishing DALL-E image |
| CONTEXT, EXPLANATION, DEFINITION | DALL-E or carry-forward |
| NARRATIVE | DALL-E scene illustration or B-roll |
| CLAIM | Text overlay with key assertion |
| EVIDENCE | Source document, quote overlay, or data viz |
| DATA_WALKTHROUGH | Chart, table, or figure from dataset |
| FIGURE_REFERENCE | KB figure (sync point — this is where figure timing happens) |
| ANALYSIS | Carry-forward or subtle visual shift |
| COMPARISON | Split screen or side-by-side |
| COUNTERPOINT | Visual contrast, different color treatment |
| SYNTHESIS | Combined/merged visual |
| COMMENTARY | Host avatar or carry-forward |
| QUESTION | Text overlay with the question |
| SPECULATION | Abstract/futuristic DALL-E |
| TRANSITION | Fade/dissolve on carry-forward |
| RECAP | Montage of previous visuals |
| OUTRO | End card or callback to intro visual |

---

## Source Attribution

Each segment should track where its content comes from. This replaces the simple `figure_refs: List[int]` with a richer model that supports multiple heterogeneous sources.

```python
# In core/models/structured_script.py — add these types

class SourceType(Enum):
    """What kind of source this is."""
    PAPER = "paper"
    NEWS = "news"
    DATASET = "dataset"
    GOVERNMENT = "government"
    TRANSCRIPT = "transcript"
    NOTE = "note"               # User's own observations
    ARTIFACT = "artifact"       # Previously generated content
    URL = "url"                 # Generic web content


@dataclass
class SourceAttribution:
    """Tracks which source(s) a segment draws from."""
    source_id: str                          # KB source ID
    source_type: SourceType
    atoms_used: List[str] = field(default_factory=list)  # Specific atom IDs
    confidence: float = 1.0                 # How directly this segment uses the source
    label: Optional[str] = None             # Display label, e.g. "Smith et al. 2024"
```

### Why This Matters

1. **The DoP needs it.** A DATA_WALKTHROUGH sourced from a government CSV should show a chart. The same intent sourced from a paper might show the paper's own figure. Source type informs visual treatment.

2. **Bias variants need it.** When generating left/right variants for news, the source attributions stay the same — only the `perspective` and `intent` framing changes. This lets you verify that both variants reference the same underlying facts.

3. **The Librarian needs it.** When searching for reusable assets, source context helps. An image generated for "GDP growth DATA_WALKTHROUGH from census data" is reusable when the same dataset appears in a different production.

4. **Citations.** For any production that should cite its sources (educational, news analysis), the attributions provide the data needed to generate citation overlays or end credits.

---

## Expanded ScriptSegment

The updated segment model with all changes:

```python
# In core/models/structured_script.py — replace existing ScriptSegment

@dataclass
class ScriptSegment:
    """A single segment of the structured script."""
    idx: int
    text: str                                       # Narration text
    intent: SegmentIntent                           # What this segment DOES

    # Source tracking (replaces simple figure_refs for multi-source support)
    source_attributions: List[SourceAttribution] = field(default_factory=list)
    figure_refs: List[int] = field(default_factory=list)   # Kept for convenience — "Figure N" mentions
    key_concepts: List[str] = field(default_factory=list)

    # Production variant support
    perspective: Optional[str] = None               # e.g., "neutral", "left_0.2", "right_0.8"
    content_type_hint: Optional[str] = None         # e.g., "news", "research", "policy", "mixed"

    # Visual direction (populated by DoP)
    visual_direction: str = ""                      # Free-text hint for DALL-E prompt
    display_mode: Optional[str] = None              # "figure_sync", "dall_e", "carry_forward", etc.
    importance_score: float = 0.5                   # For budget allocation

    # Audio (populated by Audio Producer)
    audio_file: Optional[str] = None
    estimated_duration_sec: Optional[float] = None
    actual_duration_sec: Optional[float] = None

    # Visual asset (populated by Visual Producer)
    visual_asset_id: Optional[str] = None
```

### Backward Compatibility

- `figure_refs` is still populated by parsing "Figure N" from text — same regex as before
- `source_attributions` defaults to empty list — old scripts that don't have it still work
- `perspective` defaults to None — standard single-perspective productions are unaffected
- `StructuredScript.from_script_text()` continues to work with no source attribution data

---

## StructuredScript Additions

Minor additions to the top-level script model for multi-source support:

```python
# In core/models/structured_script.py — add to StructuredScript

@dataclass
class StructuredScript:
    """The single source of truth for a production."""
    script_id: str
    trial_id: str
    version: int = 1

    segments: List[ScriptSegment] = field(default_factory=list)
    figure_inventory: Dict[int, FigureInventory] = field(default_factory=dict)

    # NEW: Multi-source metadata
    sources_used: List[str] = field(default_factory=list)       # Source IDs from KB
    content_type: str = "research"                               # Primary content type
    production_style: str = "explainer"                          # "explainer", "news_analysis", "debate", "narrative"

    # NEW: Variant support
    perspective: Optional[str] = None                            # Production-level perspective
    variant_of: Optional[str] = None                             # script_id of the base version (for bias variants)

    # Existing metadata
    total_segments: int = 0
    total_estimated_duration_sec: float = 0.0
    source_document: Optional[str] = None
    generation_prompt: Optional[str] = None

    # NEW: Convenience queries
    def get_segments_by_source(self, source_id: str) -> List[ScriptSegment]:
        """Return segments that draw from a specific source."""
        return [
            s for s in self.segments
            if any(a.source_id == source_id for a in s.source_attributions)
        ]

    def get_sources_summary(self) -> Dict[str, int]:
        """Return {source_id: segment_count} for all sources."""
        counts: Dict[str, int] = {}
        for seg in self.segments:
            for attr in seg.source_attributions:
                counts[attr.source_id] = counts.get(attr.source_id, 0) + 1
        return counts
```

---

## Bias Variant Generation

For the spiritwriter news site use case, bias variants are modeled as separate StructuredScripts that share the same source attributions but differ in perspective and editorial framing.

```
Base script (neutral):
  segments[3] = CLAIM, perspective=None, text="The policy change affects..."
  segments[4] = EVIDENCE, perspective=None, text="According to the data..."
  segments[5] = ANALYSIS, perspective=None, text="This suggests..."

Left variant (0.2):
  segments[3] = CLAIM, perspective="left_0.2", text="The policy change threatens..."
  segments[4] = EVIDENCE, perspective="left_0.2", text="The data reveals..."
  segments[5] = COMMENTARY, perspective="left_0.2", text="This confirms..."

Right variant (0.8):
  segments[3] = CLAIM, perspective="right_0.8", text="The policy change enables..."
  segments[4] = EVIDENCE, perspective="right_0.8", text="The data shows..."
  segments[5] = COMMENTARY, perspective="right_0.8", text="This demonstrates..."
```

The structure, sources, and figure references stay identical. The `intent` can shift (ANALYSIS → COMMENTARY when the variant editorializes), the `text` changes, and `perspective` tags each segment. This means:

- Audio must be regenerated per variant (different text)
- Visuals can potentially be REUSED across variants (same figures, same data)
- The Content Library enables this naturally — approved figure assets don't care about perspective

A future `generate_variant()` method on StructuredScript would take the base script and a target perspective, sending both to Claude to produce the reframed version.

---

## Implementation

### What to Change

This is a **patch** to Phase 1 of UNIFIED_PRODUCTION_ARCHITECTURE.md. Apply after the initial data models exist.

| File | Change |
|---|---|
| `core/models/structured_script.py` | Replace `SegmentIntent` enum, add `SourceType`, `SourceAttribution`, expand `ScriptSegment` and `StructuredScript` |
| `core/dop.py` | Update visual assignment logic to use new intent vocabulary and source_type for smarter decisions |
| `core/training/trainer.py` | Update script generation prompt to use new intent vocabulary |
| `tests/test_structured_script.py` | Add tests for new intents, source attribution, variant support |

### What NOT to Change

- `ContentLibrary` and `AssetRecord` — no changes needed, already content-type agnostic
- `ContentLibrarian` — no changes needed, queries by segment index not by intent
- `cli/produce_video.py` — no changes for this patch, reads segments generically
- `scripts/assemble_rough_cut.py` — no changes, reads assembly manifest not intents directly

### Migration

No migration needed. The expanded `SegmentIntent` is a superset — old intents like METHODOLOGY can be remapped:

| Old Intent | Maps To |
|---|---|
| METHODOLOGY | EXPLANATION |
| KEY_FINDING | CLAIM |
| FIGURE_WALKTHROUGH | FIGURE_REFERENCE |
| DATA_DISCUSSION | DATA_WALKTHROUGH |
| BACKGROUND | CONTEXT |

If any code checks for old intent values, add aliases:

```python
# Temporary compatibility aliases
SegmentIntent.METHODOLOGY = SegmentIntent.EXPLANATION
SegmentIntent.KEY_FINDING = SegmentIntent.CLAIM
SegmentIntent.FIGURE_WALKTHROUGH = SegmentIntent.FIGURE_REFERENCE
SegmentIntent.DATA_DISCUSSION = SegmentIntent.DATA_WALKTHROUGH
SegmentIntent.BACKGROUND = SegmentIntent.CONTEXT
```

These can be removed once all code uses the new vocabulary.
