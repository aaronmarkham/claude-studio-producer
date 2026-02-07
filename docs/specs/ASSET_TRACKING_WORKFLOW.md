# Asset Tracking & Approval Workflow

> Status: Planned
> Priority: Next after rough cut completion

## Problem

Currently, video production generates all assets in one pass with no way to:
- Review and approve individual assets before final render
- Regenerate specific segments while keeping approved ones
- Track asset status across multiple production runs
- Build final video from only approved assets

## Proposed Solution

### Asset States

```
draft → review → approved → published
         ↓
      rejected → revised → review
```

### Asset Manifest v2

```json
{
  "run_id": "20260207_101747",
  "production_state": "review",
  "segments": {
    "segment_001": {
      "paragraph_text": "Welcome back to another deep dive...",
      "audio": {
        "path": "audio/audio_000.mp3",
        "status": "approved",
        "duration_sec": 12.5,
        "voice": "lily",
        "generated_at": "2026-02-07T10:18:00Z"
      },
      "image": {
        "path": "images/scene_000.png",
        "status": "review",
        "source": "dalle",
        "prompt": "Technical diagram of UAV positioning...",
        "generated_at": "2026-02-07T10:17:00Z"
      },
      "video": null,
      "sync_status": "pending",
      "notes": "Image style doesn't match - too cartoonish"
    }
  }
}
```

### CLI Commands

```bash
# List assets with status
claude-studio assets list <run_id>
claude-studio assets list <run_id> --status review
claude-studio assets list <run_id> --type audio

# Review individual assets (opens preview)
claude-studio assets review <run_id> --segment 5
claude-studio assets review <run_id> --audio 1-10

# Approve/reject assets
claude-studio assets approve <run_id> --audio all
claude-studio assets approve <run_id> --image 1,3,5
claude-studio assets reject <run_id> --image 2 --reason "wrong style"

# Regenerate specific assets
claude-studio assets regen <run_id> --image 2 --prompt "more technical, less cartoon"
claude-studio assets regen <run_id> --audio 5-10 --voice rachel

# Copy approved assets from another run
claude-studio assets copy <source_run> <target_run> --audio approved

# Build final from approved only
claude-studio assets build <run_id> --only approved
claude-studio assets build <run_id> --skip rejected
```

### Workflow Example

```bash
# 1. Generate full audio (already done - 45 clips)
claude-studio produce-video -t trial_000 --budget medium --live --no-audio
# Use existing audio from 20260207_101747

# 2. Review audio
claude-studio assets list 20260207_101747 --type audio
claude-studio assets approve 20260207_101747 --audio 1-45

# 3. Generate images incrementally
claude-studio produce-video -t trial_000 --budget medium --live --start 0 --limit 10
claude-studio assets review 20260207_XXXXXX --type image

# 4. Regenerate rejected images
claude-studio assets reject 20260207_XXXXXX --image 3,7
claude-studio assets regen 20260207_XXXXXX --image 3,7 --style "technical diagram"

# 5. Build final video from approved assets
claude-studio assets build 20260207_XXXXXX --only approved
```

### Integration with Existing Pipeline

1. **produce-video** gains `--resume <run_id>` to continue from existing run
2. **asset_manifest.json** upgraded to v2 format with status tracking
3. New `cli/assets.py` module for asset management commands
4. Optional: Web dashboard for visual review

### Benefits

- Iterative refinement without regenerating everything
- Cost control - only regenerate what's needed
- Quality gate before final render
- Reuse approved assets across runs
- Clear audit trail of what was approved/rejected

## Implementation Notes

- Backwards compatible: v1 manifests auto-upgrade on first `assets` command
- Status stored per-asset, not per-run
- Approved assets locked from accidental overwrite
- Export function for approved assets to share/archive
