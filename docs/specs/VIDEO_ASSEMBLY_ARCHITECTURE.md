# Video Assembly Architecture

> Status: Draft
> Priority: High - blocks proper rough cut assembly
> Related: [ASSET_TRACKING_WORKFLOW.md](ASSET_TRACKING_WORKFLOW.md)

## Problem Statement

The current video assembly produces a rough cut with **incorrect timing**. Images are distributed evenly across the audio timeline instead of being synced to when they're actually discussed in the narration.

### Example of the Problem

The generated script says:
- Paragraph 23: "**Figure 6** shows the comparison results of error compensation..."
- Paragraph 27: "**Figure 9** addresses this directly by showing the comparison of runtime..."

But in the rough cut:
- Figure 6 (`fig_005.png`) appears at some arbitrary point (based on even distribution)
- Figure 9 (`fig_008.png`) appears at another arbitrary point
- Neither syncs with when the narrator is actually discussing them

## Root Cause Analysis

### Current Architecture

```
Training Pipeline:
├── Reference podcast (MP3) → Whisper → 162 segments with timing
├── Document (PDF) → Extract figures → 11 figures available
├── Claude → Generate script with figure context → 45 paragraphs
└── Output: _script.txt (mentions "Figure 6", "Figure 9", etc.)

Video Production:
├── Load aligned_segments from reference → 149 scenes (reference timing)
├── Keyword-match scenes to KB figures → assigns kb_figure_path
├── Generate audio from script paragraphs → 45 audio clips
├── Generate images (DALL-E + KB figures) → 27 images
└── Output: visual_plans.json, images/, audio/

Assembly (current):
├── 45 audio clips (from generated script)
├── 27 images (from reference scene structure)
└── Problem: No mapping between paragraphs and images
```

### The Gap

1. **Reference segments ≠ Generated paragraphs**
   - 162 reference segments (from Whisper transcription of reference podcast)
   - 45 generated paragraphs (from Claude's new script)
   - These are completely different content

2. **Figure assignment uses reference structure**
   - `kb_figure_path` is assigned to scenes (from reference)
   - But audio comes from paragraphs (from generated script)
   - No code parses generated script for "Figure N" mentions

3. **Missing paragraph→figure mapping**
   - Script generation knows about figures (passed in prompt)
   - Script output mentions figures explicitly ("Figure 6 shows...")
   - But this mention isn't captured for assembly timing

## Proposed Solution

### Phase 1: Script Paragraph Analysis

Add a post-processing step after script generation:

```python
def analyze_script_paragraphs(script_text: str, kb_figure_paths: dict) -> list:
    """
    Parse generated script to extract figure references per paragraph.

    Returns list of dicts:
    [
        {
            "paragraph_idx": 0,
            "text": "Welcome back to another deep dive...",
            "figure_refs": [],  # No figures mentioned
            "key_terms": ["UAV", "GPS", "positioning"]
        },
        {
            "paragraph_idx": 22,
            "text": "Figure 6 shows the comparison results...",
            "figure_refs": [6],  # Mentions Figure 6
            "key_terms": ["error compensation", "IMU"]
        },
        ...
    ]
    """
    import re

    paragraphs = [p.strip() for p in script_text.split('\n\n') if p.strip()]

    analyzed = []
    for idx, para in enumerate(paragraphs):
        # Find "Figure N" mentions
        figure_pattern = r'Figure\s+(\d+)'
        matches = re.findall(figure_pattern, para, re.IGNORECASE)
        figure_refs = [int(m) for m in matches]

        analyzed.append({
            "paragraph_idx": idx,
            "text": para,
            "figure_refs": figure_refs,
            "audio_file": f"audio_{idx:03d}.mp3"
        })

    return analyzed
```

### Phase 2: Figure-Timed Assembly Manifest

Create a proper assembly manifest that maps:

```json
{
  "assembly_manifest": {
    "total_paragraphs": 45,
    "total_images": 27,
    "figure_sync_points": [
      {
        "paragraph_idx": 22,
        "audio_file": "audio_022.mp3",
        "figure_ref": 6,
        "kb_figure_file": "fig_005.png",
        "display_mode": "figure_sync"
      },
      {
        "paragraph_idx": 26,
        "audio_file": "audio_026.mp3",
        "figure_ref": 9,
        "kb_figure_file": "fig_008.png",
        "display_mode": "figure_sync"
      }
    ],
    "paragraph_visuals": [
      {
        "paragraph_idx": 0,
        "audio_file": "audio_000.mp3",
        "image_file": "scene_000.png",
        "display_mode": "dall_e"
      },
      {
        "paragraph_idx": 1,
        "audio_file": "audio_001.mp3",
        "image_file": "scene_000.png",
        "display_mode": "carry_forward"
      },
      ...
    ]
  }
}
```

### Phase 3: Smart Image Distribution

For paragraphs without explicit figure mentions:

1. **Figure sync points**: When paragraph mentions "Figure N", show that KB figure
2. **DALL-E images**: Distribute across non-figure paragraphs based on content
3. **Carry forward**: Between images, show the previous image with Ken Burns

```
Timeline visualization:

Paragraph:  0   1   2   3   4   5  ... 22  23  24  25  26  27  ... 44
            ▼   ▼   ▼   ▼   ▼   ▼      ▼   ▼   ▼   ▼   ▼   ▼       ▼
Audio:      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Image:      [DALL-E 1  ][DALL-E 2 ][FIG6][-->][FIG9][-->][DALL-E N]
            └─carry fwd─┘          └sync─┘   └sync─┘
```

### Phase 4: Assembly Script Updates

Update `assemble_rough_cut.py` to use the manifest:

```python
def create_timed_assembly(manifest_path: Path, output_dir: Path):
    """
    Assemble video with proper figure timing.

    1. Load assembly manifest
    2. For each paragraph:
       - Get audio file and duration
       - Get assigned image (figure sync or DALL-E)
       - Create video segment
    3. Concatenate with proper transitions
    """
    manifest = json.loads(manifest_path.read_text())

    for para in manifest["paragraph_visuals"]:
        audio_path = audio_dir / para["audio_file"]
        image_path = images_dir / para["image_file"]
        duration = get_audio_duration(audio_path)

        # Figure sync points might want different treatment
        if para["display_mode"] == "figure_sync":
            # Maybe highlight/zoom the figure
            create_figure_segment(image_path, audio_path, duration, ...)
        else:
            # Standard Ken Burns
            create_ken_burns_segment(image_path, audio_path, duration, ...)
```

## Integration with Asset Tracking

This architecture naturally integrates with the asset tracking workflow:

```json
{
  "paragraph_001": {
    "audio": {
      "path": "audio/audio_001.mp3",
      "status": "approved",
      "duration_sec": 33.2
    },
    "visual": {
      "path": "images/scene_005.png",
      "status": "review",
      "source": "dalle",
      "display_mode": "carry_forward"
    },
    "sync_status": "pending"
  },
  "paragraph_022": {
    "audio": {
      "path": "audio/audio_022.mp3",
      "status": "approved",
      "duration_sec": 28.5
    },
    "visual": {
      "path": "figures/fig_005.png",
      "status": "approved",
      "source": "kb_figure",
      "display_mode": "figure_sync",
      "figure_ref": 6
    },
    "sync_status": "approved"
  }
}
```

## Files Involved

### Current State

| File | Purpose | Issue |
|------|---------|-------|
| `core/training/trainer.py` | Generates script with figure context | Script output not parsed for figure refs |
| `cli/produce_video.py` | Creates visual plans, generates audio | Uses reference segments, not script paragraphs |
| `core/video_production.py` | Scene creation, figure matching | Keyword matching on reference structure |
| `scripts/assemble_rough_cut.py` | FFmpeg assembly | Even distribution, no figure sync |

### Changes Needed

1. **`core/training/trainer.py`**
   - Add `analyze_script_paragraphs()` after script generation
   - Save paragraph analysis to trial output

2. **`cli/produce_video.py`**
   - Load paragraph analysis
   - Create assembly manifest with figure sync points
   - Generate audio with paragraph-aligned naming

3. **`scripts/assemble_rough_cut.py`** (or new `cli/assemble.py`)
   - Load assembly manifest
   - Respect figure sync points
   - Create proper transitions

## Example: Current vs Fixed

### Current Rough Cut (25 min)
```
0:00-0:55   scene_000.png (even distribution)
0:55-1:50   scene_005.png
1:50-2:45   scene_009.png
...
12:30-13:25 scene_073.png  ← Figure 6 discussed at 12:45 but not shown
...
15:00-15:55 scene_096.png  ← Figure 9 discussed at 15:20 but not shown
```

### Fixed Rough Cut (25 min)
```
0:00-0:33   scene_000.png (intro DALL-E)
0:33-1:05   scene_000.png (carry forward)
...
12:30-12:45 scene_068.png (DALL-E)
12:45-13:15 fig_005.png   ← SYNC: "Figure 6 shows..." audio plays
13:15-13:45 scene_070.png (DALL-E)
...
15:00-15:20 scene_096.png (DALL-E)
15:20-15:50 fig_008.png   ← SYNC: "Figure 9 addresses..." audio plays
```

## Implementation Order

1. **Script paragraph analysis** (trainer.py)
   - Parse "Figure N" mentions
   - Save to `{trial_id}_paragraph_analysis.json`

2. **Assembly manifest generation** (produce_video.py)
   - Load paragraph analysis
   - Create paragraph→visual mapping
   - Mark figure sync points

3. **Timed assembly** (assemble.py)
   - Load manifest
   - Create segments respecting sync points
   - FFmpeg concatenation

4. **Asset tracking integration** (assets.py)
   - Extend manifest with status tracking
   - CLI for review/approve/reject
   - Rebuild from approved assets only

## Notes

- The rough cut at `artifacts/video_production/rough_cut/rough_cut.mp4` demonstrates the timing problem
- 45 audio clips exist at `artifacts/video_production/20260207_101747/audio/`
- 27 images exist at `artifacts/video_production/20260207_104648/images/`
- 11 KB figures available at `artifacts/kb/kb_87a368725eca/sources/src_a5654cad96dc/figures/`
- Script mentions Figure 6 (paragraph ~23) and Figure 9 (paragraph ~27)
