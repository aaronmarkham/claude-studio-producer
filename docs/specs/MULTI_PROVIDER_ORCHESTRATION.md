# Multi-Provider Orchestration Enhancement

**Status:** ✅ Complete - Audio Pipeline Fully Integrated
**Created:** 2026-01-31
**Updated:** 2026-01-31
**Priority:** High (Completed)

## Current State (Actual Implementation)

### ✅ What's Already Working

**1. Full KB/Document Pipeline:**
- `kb create` / `kb add --paper` - Multi-source knowledge projects
- PDF ingestion with PyMuPDF → DocumentGraph extraction
- Atom classification (abstracts, figures, quotes, sections, etc.)
- Knowledge graph with cross-source entity/topic linking
- `kb produce` - Builds rich concept from knowledge graph

**2. Narrative Styles:**
- ScriptWriter has `NarrativeStyle` enum (VISUAL_STORYBOARD, PODCAST_NARRATIVE, EDUCATIONAL_LECTURE, DOCUMENTARY)
- `--style podcast` generates rich `voiceover_text` in scenes
- Scene duration auto-calculated per style (podcast = 15-20s segments)
- Scenes saved with voiceover_text field populated

**3. Audio Generation Pipeline:**
- AudioGeneratorAgent fully implemented and wired into pipeline (cli/produce.py:1095)
- Runs when `audio_tier != AudioTier.NONE`
- Generates TTS voiceover from scene.voiceover_text
- Saves audio files to run_dir/audio/
- Cost tracking integrated

**4. Provider System:**
- Individual providers working: Luma, Runway, DALL-E, ElevenLabs, OpenAI TTS, Google TTS
- Provider knowledge/learning system (memory-based prompt improvements)
- Execution graph for parallel/sequential scene generation
- Seed asset support (image → video chaining via seed_asset_lookup)

**5. Resume Capability:**
- Checkpointed pipeline (QA, Critic, EDL saved incrementally)
- `claude-studio resume <run_id>` recovers from failures
- Budget tracking from timeline (handles stale fields)

### ✅ Recently Completed (January 2026)

**1. Audio URLs in EDL:**
- ✅ `scene_audio` map passed to EditorAgent
- ✅ EditDecision.audio_url populated from scene audio files
- ✅ EDL saves with proper audio_url references

**2. Automatic Audio-Video Mixing:**
- ✅ Final mixing step added to production pipeline
- ✅ Individual scenes mixed (video + audio)
- ✅ Concatenated into `final_output.mp4`
- ✅ Production mode support (audio-led vs video-led)

**3. Production Mode System:**
- ✅ `--mode` CLI flag (video-led/audio-led)
- ✅ Auto-detection based on narrative style
- ✅ Smart duration handling (audio-led updates scene durations)

### 🔮 Future Enhancements

**Multi-Provider CLI Flags:**
- Only `--provider` (video provider) - no `--audio-provider`, `--image-provider`
- Works but not as granular as originally proposed
- Priority: Low (current system works well)

## Complete Pipeline

When a user runs:
```bash
claude-studio produce -c "Coffee on table" --budget 10 --live --provider luma --style podcast
```

**Pipeline behavior:**
- ✅ ScriptWriter generates scenes with voiceover_text
- ✅ AudioGenerator creates audio files from voiceover_text
- ✅ VideoGenerator creates video files
- ✅ Editor creates EDL with audio_url populated
- ✅ Final mixed output (video + audio combined into final_output.mp4)

## Implementation Details

### ✅ Completed Implementation

**What was implemented:**

1. **ProductionMode enum** - Audio-led vs video-led timing control
2. **Audio files passed to Editor** - Scene audio map wired through pipeline
3. **Audio URLs populated in EDL** - EditDecision objects have audio_url field
4. **Final mixing step** - Automatic video+audio mixing and concatenation

### Implementation Code

**Step 1: Map audio files to scenes**
```python
# cli/produce.py after audio generation (line ~1100)
scene_audio_map = {}  # scene_id -> audio file path
for audio_track in scene_audio:
    scene_audio_map[audio_track.scene_id] = audio_track.audio_path
```

**Step 2: Pass to Editor**
```python
# cli/produce.py line ~1309
edl = await editor.run(
    scenes=scenes,
    video_candidates=video_candidates,
    qa_results=qa_results,
    scene_audio=scene_audio_map,  # NEW
    original_request=concept,
    num_candidates=3
)
```

**Step 3: Editor populates audio_url**
```python
# agents/editor.py - in create_edl()
for decision in candidate.decisions:
    # Get audio file if available
    audio_file = scene_audio.get(decision.scene_id)
    if audio_file:
        decision.audio_url = str(audio_file)
```

**Step 4: Final mix step**
```python
# cli/produce.py after EDL save (~line 1360)
if candidate and audio_tier != AudioTier.NONE:
    console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]Renderer[/{t.agent_name}]")

    mixed_scenes = []
    for decision in candidate.decisions:
        if decision.audio_url:
            # Mix video + audio
            output_path = run_dir / "renders" / f"{decision.scene_id}_mixed.mp4"
            await render_with_audio(
                video_path=decision.video_url,
                audio_path=decision.audio_url,
                output_path=output_path,
                fit_mode="speed-match"  # or from style
            )
            mixed_scenes.append(output_path)

    # Concatenate all mixed scenes
    final_output = run_dir / "final_output.mp4"
    await concatenate_videos(mixed_scenes, final_output)
```

## Future Enhancements (Not Blocking)

### 1. Granular Provider Flags
```bash
claude-studio produce -c "concept" \
  --video-provider luma \
  --audio-provider elevenlabs \
  --image-provider dalle
```

### 2. Producer Intelligence
- Auto-select providers based on budget/style/concept
- DALL-E seed images for static subjects
- Provider selection from memory/learnings

### 3. Scene-Level Provider Specs
- ScriptWriter specifies providers per scene
- Mixed provider strategies within single production

## Implementation Plan

### ✅ Complete Implementation (January 2026)
- Phase 1: ProductionMode enum added ✅
- Phase 2: Audio-video mixer module created ✅
- Phase 3: ScriptWriter generates `voiceover_text` ✅
- Phase 4: CLI updated with --mode flag and audio wiring ✅
- Phase 5: AudioGenerator fully integrated ✅
- Phase 6: EditorAgent accepts and uses scene_audio ✅
- Phase 7: Final mixing pipeline implemented ✅
- Phase 8: Resume command supports audio mixing ✅
- Phase 9: Comprehensive test coverage added ✅
- Image → Video chaining via seed assets ✅
- KB/Document pipeline ✅
- Narrative styles ✅

### 📁 Files Modified

**New Files:**
1. `core/rendering/mixer.py` - Audio-video mixing utilities
2. `core/rendering/__init__.py` - Package exports
3. `tests/unit/test_audio_video_mixer.py` - Comprehensive tests

**Modified Files:**
1. `agents/script_writer.py` - ProductionMode enum
2. `cli/produce.py` - Audio wiring, mixing pipeline, --mode flag
3. `agents/editor.py` - scene_audio parameter support
4. `cli/resume.py` - Audio loading and mixing support

**Total Changes:** ~632 lines across 7 files

### Future Phases (Not Blocking)

**Phase 1: Granular CLI Flags**
- Add `--video-provider`, `--audio-provider`, `--image-provider`
- Maintain `--provider` backward compatibility
- Priority: Low (current system works)

**Phase 2: Producer Intelligence**
- Auto-select providers based on concept/budget
- Provider decision logic in ProducerAgent
- Priority: Medium (nice-to-have optimization)

**Phase 6: Advanced Rendering**
- Transition effects between scenes
- Music bed support
- Multi-track audio mixing
- Priority: Low (basic mixing works)

## Answers to Open Questions

1. **Default fit mode:** `speed-match` - inferred from style (podcast/educational → speed-match, visual → longest)
2. **Voice selection:** Not yet implemented - could add `--voice <name>` flag
3. **Parallel vs Sequential:** ✅ Already implemented via ExecutionGraph - auto-detects continuity groups
4. **Cost estimation:** ✅ Already working - Producer estimates per-pilot costs before generation
5. **Fallback logic:** Not implemented - providers fail with clear errors (resume handles recovery)

## Success Criteria

### Current State
User runs:
```bash
claude-studio kb produce myproject -p "Explain key findings" --budget 10 --live --style podcast
```

And gets:
1. ✅ Knowledge graph queried for relevant content
2. ✅ ScriptWriter generates scenes with voiceover_text
3. ✅ VideoGenerator creates videos (Luma)
4. ✅ AudioGenerator creates narration (ElevenLabs/OpenAI)
5. ❌ Videos and audio exist but not mixed
6. ✅ EDL created with video references (audio_url = null)

### Current State (Fully Implemented)
Command produces:
1. ✅ Knowledge graph queried for relevant content
2. ✅ ScriptWriter generates scenes with voiceover_text
3. ✅ VideoGenerator creates videos (Luma)
4. ✅ AudioGenerator creates narration (ElevenLabs/OpenAI)
5. ✅ Videos and audio mixed automatically
6. ✅ EDL created with audio_url populated
7. ✅ Final output with video + audio synced
8. ✅ Saved to `run_dir/final_output.mp4`

## Next Steps

1. ✅ Document actual implementation state (this spec)
2. ✅ Implement audio → EDL → mixing connection
3. ✅ Add comprehensive test coverage
4. Test with real production runs
5. Future: Granular provider flags (low priority)

---

**Related Docs:**
- [Architecture](ARCHITECTURE.md)
- [Producer Agent](AGENT_PRODUCER.md)
- [Multi-Provider Pipeline](../examples.md#coffee-cup---complete-multi-provider-pipeline)
