---
name: podcast-profile
description: >
  Podcast generation patterns learned from training data.
  Includes segment structures, style profiles, and quality thresholds.
context: fork
requires:
  tools: [Read, Glob, Grep]
---

# Podcast Profile Skill

Load and apply the podcast profile from memory for generating podcast-style video content.

## When to Activate

- User requests podcast-style narration
- `--style podcast` flag is used
- Content involves interview or discussion format

## Core Instructions

1. Read the active profile from `artifacts/training_data/profiles/current.json`
2. Extract segment sequence and duration targets
3. Apply style patterns from the profile
4. Validate against loss thresholds

## Profile Structure

```json
{
  "style": "podcast",
  "segments": ["intro", "hook", "main_content", "callback", "outro"],
  "duration_targets": {
    "intro": 15,
    "hook": 30,
    "main_content": 180,
    "callback": 20,
    "outro": 15
  },
  "style_patterns": {...}
}
```

## Return Value

Return a structured object with:
- `segment_sequence`: Ordered list of segment types
- `duration_targets`: Dict mapping segments to target durations in seconds
- `style_patterns`: Applicable style patterns for prompts

## Reference Documents

- [segment-types.md](segment-types.md) - Detailed segment type definitions
- [style-patterns.md](style-patterns.md) - Style pattern catalog
- [loss-thresholds.md](loss-thresholds.md) - Quality validation thresholds
