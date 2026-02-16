# produce-video — Explainer Videos from Scripts

Generate explainer videos from podcast scripts or training output.

## Synopsis

```bash
cs produce-video [OPTIONS]
```

## Input Sources

Provide one of:

| Option | Description |
|--------|-------------|
| `-t`, `--from-training TRIAL_ID` | Use output from a training trial |
| `-s`, `--script PATH` | Path to a podcast script file |

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-o`, `--output` | path | `output.mp4` | Output video path |
| `--live/--mock` | flag | mock | Use real APIs (live) or mock generation |
| `--style` | choice | `technical` | Visual style: `technical`, `educational`, `documentary` |
| `--kb` | string | | Knowledge base project name (for figure access) |
| `-b`, `--budget` | choice | | Budget tier: `micro`, `low`, `medium`, `high`, `full` |
| `--show-tiers` | flag | | Show cost comparison for all budget tiers, then exit |
| `-l`, `--limit` | int | | Limit to N scenes (for incremental production) |
| `--start` | int | 0 | Start from scene index (0-based) |
| `--audio/--no-audio` | flag | audio | Generate TTS audio narration for each scene |
| `--voice` | string | `lily` | ElevenLabs voice name or voice_id |

## Examples

```bash
# Generate from training (mock mode)
cs produce-video --from-training latest

# Script-to-video with live providers
cs produce-video --script transcript.txt --live

# With KB figures and budget control
cs produce-video --script script.txt --live --kb my-research --budget medium

# Show cost estimates
cs produce-video --script script.txt --show-tiers

# Process only first 5 scenes
cs produce-video --script script.txt --live --limit 5

# Process scenes 10-19
cs produce-video --script script.txt --live --start 10 --limit 10

# Skip audio, documentary style
cs produce-video --script script.txt --live --no-audio --style documentary

# Custom voice
cs produce-video --script script.txt --live --voice adam
```

## TTS Provider Fallback

Audio generation tries ElevenLabs first, then falls back to OpenAI TTS (tts-1-hd, "onyx" voice). Set `TTS_PROVIDER=openai` to force OpenAI TTS (useful when ElevenLabs quota is exhausted — ~20x cheaper).

## Budget Tiers

Use `--show-tiers` to see a detailed cost breakdown for your script. Generally:

| Tier | Cost Range | Description |
|------|-----------|-------------|
| `micro` | $0–3 | Text overlays, minimal images |
| `low` | $3–8 | Basic DALL-E images, shared assets |
| `medium` | $8–20 | Full DALL-E + some animations |
| `high` | $20–50 | Premium generation with Luma animations |
| `full` | $50+ | Maximum quality, all animations |

## Integration

```bash
# 1. Generate assets
cs produce-video --script script.txt --live --kb my-kb --budget medium

# 2. Assemble rough cut
cs assemble <run_id>

# 3. Upload to YouTube
cs upload youtube output.mp4 --title "My Video"
```
