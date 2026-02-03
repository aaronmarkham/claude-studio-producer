---
name: video-production
description: >
  Video production pipeline patterns including rendering,
  encoding, and quality validation. Covers FFmpeg and tier specs.
context: fork
requires:
  tools: [Read, Bash, Glob, Grep]
---

# Video Production Skill

Apply video production patterns when rendering, encoding, or validating video output.

## When to Activate

- Running production pipeline (`produce` command)
- Combining scenes (`combine` command)
- Debugging rendering issues
- Optimizing output quality/size

## Core Instructions

1. Determine production tier from budget
2. Apply tier-specific quality settings
3. Use appropriate FFmpeg patterns
4. Validate output against tier specs

## Production Pipeline

```
Script → Generate Scenes → QA Verify → Combine → Encode → Validate
```

## Tier System

| Tier | Budget | Resolution | Duration | Audio |
|------|--------|------------|----------|-------|
| Micro | $1-5 | 720p | 15-30s | TTS |
| Standard | $5-20 | 1080p | 30-90s | TTS |
| Premium | $20-50 | 1080p | 90-180s | TTS + Music |
| Pro | $50+ | 4K | 180s+ | Full audio |

## Scene Combination

```python
scenes = [
    {"path": "scene_001.mp4", "start": 0, "end": 5},
    {"path": "scene_002.mp4", "start": 0, "end": 5},
]
# Apply crossfades, normalize audio, render to output
```

## Return Value

When analyzing production issues, return:
- `tier`: Detected/recommended tier
- `settings`: FFmpeg settings to apply
- `issues`: List of validation failures
- `fix`: Recommended resolution

## Reference Documents

- [tier-specs.md](tier-specs.md) - Detailed tier specifications
- [ffmpeg-patterns.md](ffmpeg-patterns.md) - FFmpeg command patterns
