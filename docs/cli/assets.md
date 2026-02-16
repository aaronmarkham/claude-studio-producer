# assets - Asset Tracking and Approval  

The `assets` command provides comprehensive asset tracking and approval workflow for production assets. This is Phase 6 of the Unified Production Architecture, enabling fine-grained control over which assets are used in final video builds.

## Synopsis

```bash
claude-studio assets COMMAND [OPTIONS]
```

## Description

The assets command manages the complete lifecycle of production assets:

- Review generated images, audio, and video clips
- Approve high-quality assets for final builds  
- Reject problematic assets for regeneration
- Import approved assets between production runs
- Build final videos using only approved content

## Commands Overview

| Command | Purpose |
|---------|---------|
| `list` | List assets with filtering options |
| `approve` | Mark assets as approved for final build |
| `reject` | Mark assets as rejected (need regeneration) |
| `build` | Build final video from approved assets |
| `import` | Import assets from another production run |
| `summary` | Show asset status summary |

## Workflow

The typical asset management workflow:

```bash
# 1. Generate assets
claude-studio produce-video --script script.txt --live --kb-project research

# 2. Review generated assets
claude-studio assets list <run_dir>

# 3. Approve good assets
claude-studio assets approve <run_dir> --audio all --image 1,3,5,7

# 4. Reject problematic assets
claude-studio assets reject <run_dir> --image 2,6 --reason "wrong style"

# 5. Build final video from approved assets
claude-studio assets build <run_dir>
```

---

## list - List Assets

List assets in a production run with optional filtering.

### Synopsis

```bash
claude-studio assets list RUN_DIR [OPTIONS]
```

### Options

#### `--status, -s CHOICE`
Filter by asset status.

**Choices:**
- `all` - Show all assets (default)
- `draft` - Assets in draft status
- `review` - Assets pending review
- `approved` - Assets approved for final build
- `rejected` - Assets marked for regeneration

#### `--type, -t CHOICE`
Filter by asset type.

**Choices:**
- `all` - All asset types (default)
- `audio` - Audio files only
- `image` - Image files only  
- `figure` - KB figures only
- `video` - Video clips only

#### `--segment, -g TEXT`
Filter by segment range.

**Format:** 
- `1-10` - Range of segments
- `5,6,7` - Specific segments
- `all` - All segments

### Examples

```bash
# List all assets
claude-studio assets list ./my_run

# Show only rejected images
claude-studio assets list ./my_run --status rejected --type image

# Show assets for segments 1-10
claude-studio assets list ./my_run --segment 1-10

# Show approved audio assets
claude-studio assets list ./my_run --status approved --type audio
```

### Sample Output

```
┌─ IMAGE Assets (8) ─────────────────────────────────┐
│ ID                  │ Segment │ Status    │ Path            │
├─────────────────────┼─────────┼───────────┼─────────────────┤
│ img_0001            │ 1       │ approved  │ scene_001.png   │
│ img_0002            │ 2       │ rejected  │ scene_002.png   │
│ img_0003            │ 3       │ draft     │ scene_003.png   │
└─────────────────────┴─────────┴───────────┴─────────────────┘

Status breakdown: approved: 5, rejected: 2, draft: 1
```

---

## approve - Approve Assets

Mark assets as approved for final build.

### Synopsis

```bash
claude-studio assets approve RUN_DIR [OPTIONS]
```

### Options

#### `--audio, -a TEXT`
Audio segments to approve.

**Format:**
- `all` - Approve all audio assets
- `1-10` - Approve segments 1 through 10
- `1,3,5` - Approve specific segments

#### `--image, -i TEXT`  
Image segments to approve.

**Format:** Same as `--audio`

#### `--segment, -g TEXT`
Approve all asset types for specified segments.

**Format:** Same as `--audio`

### Examples

```bash
# Approve all audio assets
claude-studio assets approve ./my_run --audio all

# Approve specific image segments
claude-studio assets approve ./my_run --image 1,3,5,7,9

# Approve all assets for segments 1-10
claude-studio assets approve ./my_run --segment 1-10

# Approve different types separately
claude-studio assets approve ./my_run --audio 1-5 --image 1,2,4
```

---

## reject - Reject Assets

Mark assets as rejected, indicating they need regeneration.

### Synopsis

```bash
claude-studio assets reject RUN_DIR [OPTIONS]
```

### Options

#### `--audio, -a TEXT`
Audio segments to reject.

**Format:** Same as approve command

#### `--image, -i TEXT`
Image segments to reject.

**Format:** Same as approve command

#### `--reason, -r TEXT`
Reason for rejection (stored in asset metadata).

### Examples

```bash
# Reject specific images with reason
claude-studio assets reject ./my_run --image 2,6 --reason "wrong style"

# Reject audio segments
claude-studio assets reject ./my_run --audio 5-10 --reason "voice too fast"

# Reject without specific reason
claude-studio assets reject ./my_run --image 3
```

---

## build - Build Final Video

Build final video using approved assets only.

### Synopsis

```bash
claude-studio assets build RUN_DIR [OPTIONS]
```

### Options

#### `--output, -o PATH`
Output video path.

**Default:** `<run_dir>/final/output.mp4`

#### `--only CHOICE`
Asset selection strategy.

**Choices:**
- `approved` - Use only approved assets (default)
- `all` - Use all available assets

#### `--skip-rejected / --include-rejected`
Whether to skip rejected assets (default: skip).

### Examples

```bash
# Build from approved assets only
claude-studio assets build ./my_run

# Build from all assets except rejected
claude-studio assets build ./my_run --only all --skip-rejected

# Custom output location
claude-studio assets build ./my_run --output final_video.mp4
```

---

## import - Import Assets

Import approved assets from another production run.

### Synopsis

```bash
claude-studio assets import SOURCE_RUN TARGET_RUN [OPTIONS]
```

### Options

#### `--status, -s CHOICE`
Import asset status filter.

**Choices:**
- `approved` - Import only approved assets (default)
- `all` - Import all assets

#### `--type, -t CHOICE`
Import asset type filter.

**Choices:**
- `all` - Import all asset types (default)
- `audio` - Import audio assets only
- `image` - Import image assets only

### Examples

```bash
# Import all approved assets
claude-studio assets import ./old_run ./new_run

# Import only approved audio (reuse voiceovers)
claude-studio assets import ./old_run ./new_run --type audio

# Import all assets regardless of status
claude-studio assets import ./old_run ./new_run --status all
```

### Use Cases

**Reusing Approved Audio:**
When regenerating images but keeping good voiceover:

```bash
# Generate new images with different style
claude-studio produce-video --script script.txt --budget high --live

# Import approved audio from previous run  
claude-studio assets import ./previous_run ./new_run --type audio

# Build with mixed assets
claude-studio assets build ./new_run
```

**Template Reuse:**
Reusing assets across similar content:

```bash
# Import approved brand assets
claude-studio assets import ./brand_template ./new_project --type image

# Add project-specific content
claude-studio produce-video --script new_script.txt --live
```

---

## summary - Asset Summary

Show comprehensive asset status summary.

### Synopsis

```bash
claude-studio assets summary RUN_DIR
```

### Examples

```bash
# Show complete asset breakdown
claude-studio assets summary ./my_run
```

### Sample Output

```
┌─ Asset Summary: my_run ────────────────────────────┐

Asset Type    │ Count
──────────────┼──────
audio         │ 12
image         │ 15  
figure        │ 3
video         │ 8
Total         │ 38

Status        │ Count  
──────────────┼──────
approved      │ 22
draft         │ 10
rejected      │ 4
review        │ 2
```

---

## Asset Status Lifecycle

Assets progress through defined status states:

### `draft`
- Initial status after generation
- Asset available but not reviewed
- **Color:** Yellow

### `review`  
- Manually set for assets pending review
- Intermediate state for workflow
- **Color:** Cyan

### `approved`
- Asset approved for final builds
- High quality, ready for use
- **Color:** Green

### `rejected`
- Asset marked for regeneration
- Quality issues or wrong content
- **Color:** Red

### `revised`
- Asset regenerated after rejection
- Updated version available
- **Color:** Magenta

## Asset Types

The system tracks multiple asset types:

### `audio`
- Generated voiceover files
- TTS output from ElevenLabs/OpenAI
- Background music tracks

### `image`
- DALL-E generated images
- Web-sourced images from Wikimedia
- Static visual content

### `figure`
- KB extracted figures from PDFs
- Technical diagrams and charts
- Academic/research visuals

### `video`
- Luma AI generated video clips
- Runway ML animations
- Dynamic visual content

## Content Library Integration

Assets are managed through the Content Library system:

### Registration
Every generated asset is automatically registered:

```json
{
  "asset_id": "img_0001",
  "asset_type": "image",
  "source": "dalle",
  "status": "draft",
  "segment_idx": 1,
  "path": "images/scene_001.png",
  "metadata": {
    "prompt": "A rocket launching into space",
    "cost": 0.08,
    "generation_time": "2026-02-07T14:30:22Z"
  }
}
```

### Tracking
- Generation costs and timing
- Source provider information
- Quality metrics and scores
- Approval workflow history

### Persistence
Asset status persists across:
- Assembly operations
- Build processes  
- Import/export between runs
- Long-term project management

## Quality Control Workflow

### Automated Quality Gates

Some quality checks are automatic:
- **Technical Validation**: File format, resolution, duration
- **Content Filtering**: Basic content appropriateness
- **Cost Tracking**: Budget compliance monitoring

### Manual Review Process

```bash
# 1. Generate assets
claude-studio produce-video --script script.txt --live

# 2. Review all assets systematically
claude-studio assets list <run_dir> --status draft

# 3. Spot-check generated content
open <run_dir>/images/  # Review images
open <run_dir>/audio/   # Listen to audio

# 4. Approve high-quality assets
claude-studio assets approve <run_dir> --audio all
claude-studio assets approve <run_dir> --image 1,3,5,7,9,11

# 5. Reject problematic assets with reasons
claude-studio assets reject <run_dir> --image 2,4 --reason "off-brand colors"
claude-studio assets reject <run_dir> --image 6 --reason "unclear diagram"

# 6. Build final video with approved assets only
claude-studio assets build <run_dir>
```

### Batch Approval Strategies

**Conservative Approach** (High Quality):
```bash
# Review everything individually, approve selectively
claude-studio assets list <run_dir>
# ... manual review ...
claude-studio assets approve <run_dir> --image 1,3,7  # Only best images
claude-studio assets approve <run_dir> --audio 1-5    # Good audio range
```

**Aggressive Approach** (Fast Turnaround):
```bash
# Approve most, reject only obvious problems
claude-studio assets approve <run_dir> --audio all
claude-studio assets approve <run_dir> --image all
claude-studio assets reject <run_dir> --image 4,7 --reason "technical issues"
```

**Mixed Approach** (Balanced):
```bash
# Approve safe assets, review risky ones
claude-studio assets approve <run_dir> --audio all  # Audio usually good
claude-studio assets list <run_dir> --type image    # Review images individually
claude-studio assets approve <run_dir> --image 1,2,3,5,6,8,9
claude-studio assets reject <run_dir> --image 4,7 --reason "style mismatch"
```

## Integration with Other Commands

### Assembly Integration

The `assemble` command respects asset approval:

```bash
# Assembly uses approved assets automatically
claude-studio assemble <run_dir>
```

If assets are rejected, assembly handles gracefully:
- **Rejected images** → Falls back to text overlay
- **Rejected audio** → Creates silent segments  
- **Missing assets** → Uses previous segment's visual

### Production Pipeline Integration

Assets integrate with the full production pipeline:

```bash
# 1. Generate with quality focus
claude-studio produce-video --script script.txt --live --budget high

# 2. Review and curate assets
claude-studio assets list <run_dir>
claude-studio assets approve <run_dir> --audio all --image 1,3,5,7

# 3. Regenerate rejected assets (manual process)
# Edit script or regenerate individual segments as needed

# 4. Build final video
claude-studio assets build <run_dir>

# 5. Upload approved content
claude-studio upload youtube <run_dir>/final/output.mp4
```

## Storage and Organization

### File Structure

```
<run_dir>/
├── content_library.json    # Asset registry
├── images/                 # Generated images
│   ├── scene_001.png      # Status tracked in library
│   ├── scene_002.png      
│   └── ...
├── audio/                  # Generated audio
│   ├── audio_001.mp3      # Status tracked in library
│   └── ...
└── final/                  # Final build outputs
    └── output.mp4
```

### Metadata Storage

Asset metadata is stored in `content_library.json`:

```json
{
  "project_id": "video_production_20260207_143022",
  "created_at": "2026-02-07T14:30:22Z",
  "assets": {
    "img_0001": {
      "asset_id": "img_0001",
      "asset_type": "image", 
      "status": "approved",
      "segment_idx": 1,
      "path": "images/scene_001.png",
      "source": "dalle",
      "created_at": "2026-02-07T14:32:15Z",
      "approved_at": "2026-02-07T14:45:30Z",
      "metadata": {
        "prompt": "Professional office workspace with laptop",
        "cost": 0.08,
        "width": 1792,
        "height": 1024
      }
    }
  }
}
```

## Performance and Scalability

### Large Production Runs

For productions with many assets:

```bash
# Use filtering to manage large asset sets
claude-studio assets list <run_dir> --segment 1-10 --status draft
claude-studio assets approve <run_dir> --segment 1-10 --audio all

# Batch process by type
claude-studio assets list <run_dir> --type audio --status draft
claude-studio assets approve <run_dir> --audio all
```

### Cross-Project Asset Management

```bash
# Standardize approved assets across projects
claude-studio assets import ./template_run ./project1 --type image --status approved
claude-studio assets import ./template_run ./project2 --type image --status approved

# Share high-quality voiceovers
claude-studio assets import ./master_audio ./new_project --type audio
```

## Version History

- **0.6.0**: Unified Production Architecture with content library
- **0.5.x**: Asset approval workflow and status tracking
- **0.4.x**: Basic asset listing and management