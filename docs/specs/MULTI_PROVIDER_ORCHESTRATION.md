# Multi-Provider Orchestration Enhancement

**Status:** Planning Phase
**Created:** 2026-01-31
**Priority:** High

## Current State

### What Works
- Individual providers tested and working:
  - **Image:** DALL-E
  - **Video:** Luma, Runway (image-to-video)
  - **Audio:** ElevenLabs, OpenAI TTS, Google TTS
  - **Rendering:** FFmpeg (speed-match, longest, shortest modes)
- Manual multi-provider pipeline demonstrated: DALL-E → Luma → ElevenLabs → FFmpeg

### Current Limitations
- `--provider` flag is monolithic (only constrains video provider)
- No automatic chaining of providers (image → video → audio → render)
- `--style podcast` creates verbose narration text but may not invoke AudioGenerator
- No clear path for Producer to orchestrate full multi-provider workflows

## The Problem

When a user runs:
```bash
claude-studio produce -c "Coffee on table" --budget 10 --live --provider luma --style podcast
```

**Expected behavior (unclear):**
- Should it use DALL-E to generate seed image first?
- Should it generate audio narration for podcast style?
- Should it automatically mix video + audio at the end?

**Current behavior (likely):**
- Only uses Luma for text-to-video
- Possibly generates verbose scene descriptions that don't get narrated
- No automatic audio/mixing

## Proposed Solution

### 1. Separate Provider Flags

Replace monolithic `--provider` with granular flags:

```bash
claude-studio produce -c "concept" \
  --video-provider luma \
  --audio-provider elevenlabs \
  --image-provider dalle \
  --budget 10 \
  --live \
  --style podcast
```

**Behavior:**
- When `--image-provider` specified → Generate seed image, pass to video provider
- When `--audio-provider` specified → Generate narration, mix with video using FFmpeg
- When `--video-provider` specified → Use for video generation (with or without seed image)

### 2. Producer Intelligence (When Flags Omitted)

When user doesn't specify provider types, Producer decides based on:
- **Budget constraints** - Choose cost-effective providers
- **Concept analysis** - "static object" → might benefit from DALL-E seed
- **Style** - `podcast/educational/documentary` → enable audio
- **Memory/learnings** - What worked well in the past

**Example - Minimal command:**
```bash
claude-studio produce -c "Coffee on table" --budget 10 --live --style podcast
```

Producer might decide:
1. "Coffee on table" → static subject → use DALL-E for seed image ($0.040)
2. Use Luma with seed image for animation (~$0.50)
3. Style is podcast → generate audio narration with cheapest TTS
4. Auto-mix with FFmpeg

### 3. Scene-Level Specifications

ScriptWriter needs to specify provider requirements per scene:

```json
{
  "scene_number": 1,
  "description": "Coffee cup with steam rising",
  "video_prompt": "Steam rises from coffee, morning light...",
  "narration_text": "A perfect morning begins...",
  "providers": {
    "image": "dalle",  // or null
    "video": "luma",
    "audio": "elevenlabs"  // or null for silent
  },
  "duration": 5.0
}
```

### 4. Editor/Renderer Integration

Editor agent needs to:
- Recognize when scenes have both video and audio
- Specify FFmpeg fit mode in EDL
- Pass to Renderer for final assembly

## Implementation Plan

### Phase 1: CLI Flag Enhancement
1. Add new flags: `--video-provider`, `--audio-provider`, `--image-provider`
2. Maintain backward compatibility with `--provider` (maps to `--video-provider`)
3. Update help text and examples

**Files to modify:**
- `cli/produce.py` - Add new options
- `cli/config.py` - Update config model

### Phase 2: Producer Agent Enhancement
1. Update ProducerAgent to receive provider preferences
2. Add logic to decide when to use image seeds
3. Add logic to decide when to generate audio (based on style)
4. Budget allocation across provider types

**Files to modify:**
- `agents/producer.py` - Provider selection logic
- `core/models/production.py` - Add provider specs to scenes

### Phase 3: ScriptWriter Enhancement
1. Generate `narration_text` field when audio is requested
2. Include provider specs in scene objects
3. Use provider-specific prompt learnings

**Files to modify:**
- `agents/script_writer.py` - Add narration generation
- `core/models/scene.py` - Add provider fields

### Phase 4: VideoGenerator Enhancement
1. Check if scene requires image seed
2. If yes, call image provider first
3. Pass generated image URL to video provider

**Files to modify:**
- `agents/video_generator.py` - Image → Video chaining

### Phase 5: AudioGenerator Integration
1. Create AudioGeneratorAgent (might already exist as stub)
2. Generate speech from `narration_text` per scene
3. Save audio files alongside video files

**Files to modify:**
- `agents/audio_generator.py` - Implement if needed
- `core/orchestrator.py` - Invoke AudioGenerator

### Phase 6: Editor/Renderer Enhancement
1. Editor creates EDL with video+audio references
2. Renderer uses FFmpeg to mix each scene
3. Concatenate mixed scenes into final output

**Files to modify:**
- `agents/editor.py` - EDL with audio
- `core/renderer.py` - Scene-by-scene mixing + concatenation

## Open Questions

1. **Default fit mode:** When mixing video+audio, what's the default? (Probably `speed-match`)
2. **Voice selection:** How does user specify voice for TTS? New flag `--voice lily`?
3. **Parallel vs Sequential:** Should scenes be generated in parallel or sequentially (for keyframe passing)?
4. **Cost estimation:** How does Producer estimate multi-provider costs before generation?
5. **Fallback logic:** What if preferred provider fails? Fallback to alternatives?

## Success Criteria

User should be able to run:
```bash
claude-studio produce -c "Coffee on table" --budget 10 --live --style podcast
```

And get:
1. DALL-E seed image
2. Luma video animation
3. ElevenLabs narration
4. FFmpeg-mixed final video with audio
5. All orchestrated automatically by Producer based on budget and style

## Next Steps

1. Review this spec
2. Decide on open questions
3. Start with Phase 1 (CLI flags)
4. Implement phases sequentially with testing

---

**Related Docs:**
- [Architecture](ARCHITECTURE.md)
- [Producer Agent](AGENT_PRODUCER.md)
- [Multi-Provider Pipeline](../examples.md#coffee-cup---complete-multi-provider-pipeline)
