# Audio-Video Orchestration Patch

## Summary

Complete the 5% gap in the pipeline: wire audio files into EDL and add final mixing step. Also add support for audio-led vs video-led production modes.

## Current State

✅ ScriptWriter generates `voiceover_text` in scenes (when `--style podcast`)
✅ AudioGenerator creates audio files from `voiceover_text`
✅ VideoGenerator creates video files
✅ Editor creates EDL
❌ EDL has `audio_url = null` (audio files not passed to Editor)
❌ No final mixing step (video + audio remain separate files)

## Files to Modify

1. `core/models/scene.py` - Add ProductionMode enum
2. `cli/produce.py` - Wire audio to editor, add mix step
3. `agents/editor.py` - Accept and use scene_audio parameter

---

## Change 1: Add ProductionMode (core/models/scene.py)

Add this enum near the other enums:

```python
class ProductionMode(Enum):
    """Which asset drives the timeline"""
    VIDEO_LED = "video_led"      # Video determines duration, audio fits to video
    AUDIO_LED = "audio_led"      # Audio determines duration, video fits to audio
```

---

## Change 2: Modify cli/produce.py

### 2a. Add import at top

```python
from core.models.scene import ProductionMode
```

### 2b. Add CLI flag (in the produce command options, around line 150)

Find the `@click.option` decorators for the produce command and add:

```python
@click.option('--mode', type=click.Choice(['video-led', 'audio-led']), default='video-led',
              help='Production mode: video-led (video determines timing) or audio-led (audio determines timing)')
```

And add `mode` to the function signature.

### 2c. Determine production mode (after style parsing, around line 400)

```python
# Determine production mode from flags and style
if mode == 'audio-led' or style in ['podcast', 'educational', 'documentary']:
    production_mode = ProductionMode.AUDIO_LED
else:
    production_mode = ProductionMode.VIDEO_LED
```

### 2d. Build scene_audio_map after audio generation (around line 1100)

Find where `scene_audio` is populated after AudioGenerator runs. Add immediately after:

```python
# Build scene_audio_map for editor
scene_audio_map: Dict[str, str] = {}
if scene_audio:
    for audio_track in scene_audio:
        if audio_track.audio_path and Path(audio_track.audio_path).exists():
            scene_audio_map[audio_track.scene_id] = str(audio_track.audio_path)
    
    # For audio-led mode: update scene durations from actual audio
    if production_mode == ProductionMode.AUDIO_LED:
        for audio_track in scene_audio:
            for scene in scenes:
                if scene.scene_id == audio_track.scene_id:
                    scene.duration = audio_track.duration
                    break
```

### 2e. Pass scene_audio_map to editor (around line 1309)

Find the `editor.run()` call and modify:

```python
edl = await editor.run(
    scenes=scenes,
    video_candidates=video_candidates,
    qa_results=qa_results,
    scene_audio=scene_audio_map,  # ADD THIS PARAMETER
    original_request=concept,
    num_candidates=3
)
```

### 2f. Add final mixing step (after EDL save, around line 1360)

Find where the EDL is saved and add this block after:

```python
# === FINAL MIX STEP ===
if candidate and scene_audio_map:
    console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]Mixing video + audio[/{t.agent_name}]")
    
    mixed_dir = run_dir / "mixed"
    mixed_dir.mkdir(exist_ok=True)
    
    mixed_paths = []
    
    for decision in candidate.decisions:
        video_path = decision.video_url
        audio_path = scene_audio_map.get(decision.scene_id)
        
        if video_path and audio_path and Path(video_path).exists() and Path(audio_path).exists():
            output_path = mixed_dir / f"{decision.scene_id}_mixed.mp4"
            
            # Determine fit mode based on production mode
            if production_mode == ProductionMode.AUDIO_LED:
                # Audio is master - stretch video to fit audio duration
                fit_mode = "stretch"
            else:
                # Video is master - audio fits to video
                fit_mode = "truncate"
            
            try:
                await mix_single_scene(
                    video_path=str(video_path),
                    audio_path=str(audio_path),
                    output_path=str(output_path),
                    fit_mode=fit_mode,
                )
                mixed_paths.append(output_path)
                console.print(f"│       ✓ Mixed {decision.scene_id}")
            except Exception as e:
                console.print(f"│       ✗ Failed to mix {decision.scene_id}: {e}")
                # Fall back to video-only
                mixed_paths.append(Path(video_path))
        elif video_path and Path(video_path).exists():
            # No audio, use video as-is
            mixed_paths.append(Path(video_path))
    
    # Concatenate all mixed scenes into final output
    if mixed_paths:
        final_output = run_dir / "final_output.mp4"
        try:
            await concatenate_videos(mixed_paths, final_output)
            console.print(f"│   [{t.success}]✓[/{t.success}] Final output: {final_output}")
        except Exception as e:
            console.print(f"│   [{t.error}]✗[/{t.error}] Failed to concatenate: {e}")
```

### 2g. Add helper functions (at bottom of file or in a new core/rendering/mixer.py)

```python
async def mix_single_scene(
    video_path: str,
    audio_path: str, 
    output_path: str,
    fit_mode: str = "stretch",
) -> None:
    """Mix a single video with audio.
    
    fit_mode:
        - "stretch": Stretch/compress video to match audio duration
        - "truncate": Truncate longer asset to match shorter
        - "loop": Loop shorter asset to match longer
    """
    import subprocess
    
    # Get durations
    video_duration = await get_media_duration(video_path)
    audio_duration = await get_media_duration(audio_path)
    
    if fit_mode == "stretch" and video_duration != audio_duration:
        # Calculate speed factor to make video match audio
        speed_factor = video_duration / audio_duration
        
        # Use setpts filter to adjust video speed
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter:v", f"setpts={1/speed_factor}*PTS",
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
    else:
        # Simple merge with -shortest
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_path
        ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg mix failed: {stderr.decode()}")


async def get_media_duration(path: str) -> float:
    """Get duration of a media file in seconds."""
    import subprocess
    
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    
    return float(stdout.decode().strip())


async def concatenate_videos(video_paths: List[Path], output_path: Path) -> None:
    """Concatenate multiple videos into one."""
    import tempfile
    
    # Create concat file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for path in video_paths:
            f.write(f"file '{path}'\n")
        concat_file = f.name
    
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {stderr.decode()}")
    finally:
        Path(concat_file).unlink(missing_ok=True)
```

---

## Change 3: Modify agents/editor.py

### 3a. Update EditorAgent.run() signature

Find the `run` method and add `scene_audio` parameter:

```python
async def run(
    self,
    scenes: List[Scene],
    video_candidates: Dict[str, List[GeneratedVideo]],
    qa_results: Dict[str, QAResult],
    scene_audio: Optional[Dict[str, str]] = None,  # ADD THIS
    original_request: Optional[str] = None,
    num_candidates: int = 3,
) -> Optional[EDLCandidate]:
```

### 3b. Pass scene_audio to create_edl

Find where `create_edl` or similar is called, and pass the audio:

```python
candidate = await self._create_edl_candidate(
    scenes=scenes,
    video_candidates=video_candidates,
    qa_results=qa_results,
    scene_audio=scene_audio,  # ADD THIS
    ...
)
```

### 3c. Populate audio_url in EditDecision

Find where EditDecision objects are created and add:

```python
# When creating EditDecision for each scene
decision = EditDecision(
    scene_id=scene.scene_id,
    video_url=selected_video.video_url,
    # ... other fields ...
)

# Populate audio URL if available
if scene_audio and scene.scene_id in scene_audio:
    decision.audio_url = scene_audio[scene.scene_id]
```

---

## Testing

After implementing, test with:

```bash
# Test audio-led (podcast) mode
claude-studio produce -c "Explain how coffee is made" \
  --budget 5 \
  --live \
  --provider luma \
  --style podcast \
  --mode audio-led

# Verify:
# 1. Audio files generated in run_dir/audio/
# 2. EDL contains audio_url for each scene
# 3. Mixed files in run_dir/mixed/
# 4. Final output at run_dir/final_output.mp4
```

```bash
# Test video-led mode (should work as before)
claude-studio produce -c "Coffee cup on table" \
  --budget 5 \
  --live \
  --provider luma \
  --style visual

# Verify same outputs
```

---

## Summary of Changes

| File | Change | Lines (approx) |
|------|--------|----------------|
| core/models/scene.py | Add ProductionMode enum | +5 |
| cli/produce.py | Add --mode flag | +3 |
| cli/produce.py | Determine production mode | +5 |
| cli/produce.py | Build scene_audio_map | +12 |
| cli/produce.py | Pass to editor | +1 |
| cli/produce.py | Final mix step | +50 |
| cli/produce.py | Helper functions | +80 |
| agents/editor.py | Accept scene_audio param | +5 |
| agents/editor.py | Populate audio_url | +3 |

**Total: ~165 lines of changes across 3 files**

---

## Notes for CC

1. The existing `claude-studio render mix` command already does video+audio mixing - you can look at that implementation for reference
2. The `EditDecision` model already has an `audio_url` field - it just needs to be populated
3. The `AudioGeneratorAgent` already returns audio tracks with `scene_id` and `audio_path`
4. FFmpeg is already available and used throughout the project
5. Don't try to refactor the entire pipeline - just wire up the missing connections
