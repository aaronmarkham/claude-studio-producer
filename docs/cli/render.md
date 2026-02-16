# render - EDL Rendering and Audio Mixing

The `render` command provides video rendering capabilities including EDL (Edit Decision List) rendering from production runs and video+audio mixing for testing workflows.

## Synopsis

```bash
claude-studio render COMMAND [OPTIONS]
```

## Description

The render command offers two primary functions:

1. **EDL Rendering**: Convert production EDLs into final videos with transitions and effects
2. **Audio Mixing**: Combine video files with TTS-generated or existing audio tracks

## Commands Overview

| Command | Purpose |
|---------|---------|
| `edl` | Render final video from production run EDLs |
| `mix` | Mix video with TTS audio or audio files |

---

## edl - Render Production EDLs

Render a final video from an existing production run's Edit Decision List.

### Synopsis

```bash
claude-studio render edl RUN_ID [OPTIONS]
```

### Arguments

#### `RUN_ID`
Run directory name from artifacts/runs/.

**Examples:**
- `20260107_224324` - Timestamp-based run ID
- `my_custom_run` - Custom run directory name

### Options

#### `--candidate, -c TEXT`
Specific edit candidate ID to render.

**Default:** Uses recommended candidate from EDL

#### `--output, -o PATH`
Output file path for rendered video.

**Default:** `<run_dir>/renders/final_video.mp4`

#### `--list-candidates, -l`
List available edit candidates and exit.

Displays all available edit candidates with their properties before rendering.

### Examples

#### Basic EDL Rendering

```bash
# Render recommended edit candidate
claude-studio render edl 20260107_224324

# Render to specific output file
claude-studio render edl 20260107_224324 -o my_final_video.mp4

# List available candidates first
claude-studio render edl 20260107_224324 --list-candidates
```

#### Candidate Selection

```bash
# Render specific edit candidate
claude-studio render edl 20260107_224324 -c creative_cut

# Compare different candidates
claude-studio render edl 20260107_224324 -c standard_cut -o standard.mp4
claude-studio render edl 20260107_224324 -c creative_cut -o creative.mp4
```

### EDL Structure

EDL rendering works with Edit Decision Lists created by the Editor Agent:

```json
{
  "edl_id": "edl_20260107_224324",
  "recommended_candidate_id": "standard_cut",
  "candidates": [
    {
      "candidate_id": "standard_cut",
      "name": "Standard Professional Cut",
      "style": "clean",
      "total_duration": 45.2,
      "estimated_quality": 85.5,
      "decisions": [
        {
          "scene_id": "scene_001",
          "video_url": "/path/to/scene_001_v0.mp4",
          "in_point": 0.0,
          "out_point": 8.5,
          "start_time": 0.0,
          "duration": 8.5,
          "transition_in": "cut",
          "transition_out": "dissolve",
          "text_overlay": "Welcome",
          "text_position": "center"
        }
      ]
    }
  ]
}
```

### Rendering Features

#### Video Processing
- **Concatenation**: Seamlessly joins video clips
- **Transitions**: Applies cuts, dissolves, and fades
- **Timing**: Precise start/end point trimming
- **Scaling**: Consistent resolution and aspect ratio

#### Text Overlays
- **Positioning**: Center, top, bottom placement options
- **Styling**: Title, subtitle, caption text styles  
- **Timing**: Precise overlay start and duration control
- **Effects**: Fade-in and fade-out animations

#### Audio Integration
- **Track Mixing**: Combines multiple audio sources
- **Volume Control**: Per-track volume adjustment
- **Synchronization**: Perfect audio-video sync
- **Format Support**: MP3, WAV, AAC input formats

### Sample Output

```bash
claude-studio render edl 20260107_224324 --list-candidates

┌─ Edit Candidates for 20260107_224324 ───────────────┐
│ ID            │ Name              │ Style  │ Duration │ Quality │ Recommended │
├───────────────┼───────────────────┼────────┼──────────┼─────────┼─────────────┤
│ standard_cut  │ Standard Cut      │ clean  │ 45.2s    │ 85      │ *           │
│ creative_cut  │ Creative Edit     │ dynamic│ 43.8s    │ 82      │             │
│ minimal_cut   │ Minimal Approach  │ simple │ 38.5s    │ 78      │             │
└───────────────┴───────────────────┴────────┴──────────┴─────────┴─────────────┘

Rendering candidate: standard_cut

Videos in edit:
  ✓ scene_001: /path/to/videos/scene_001_v0.mp4
  ✓ scene_002: /path/to/videos/scene_002_v0.mp4  
  ✓ scene_003: /path/to/videos/scene_003_v0.mp4

Rendering...

✓ Render complete!
  Output: artifacts/runs/20260107_224324/renders/final_video.mp4
  Duration: 45.2s
  Size: 32.1 MB
  Render time: 8.3s
```

---

## mix - Video and Audio Mixing

Mix a video file with TTS-generated audio or an existing audio file.

### Synopsis

```bash
claude-studio render mix VIDEO_FILE [OPTIONS]
```

### Arguments

#### `VIDEO_FILE`
Path to input video file.

**Supported formats:** MP4, AVI, MOV, MKV

### Options

#### Audio Source (choose one)

##### `--text, -t TEXT`
Text to convert to speech (TTS).

Generates audio using available TTS providers (ElevenLabs or OpenAI).

##### `--audio, -a PATH`
Existing audio file to mix with video.

**Supported formats:** MP3, WAV, AAC, M4A

#### TTS Options

##### `--voice, -v TEXT`
Voice ID for TTS generation.

**Default:** `Rachel`

**ElevenLabs Voices:**
- `Rachel` - Clear, professional female
- `Adam` - Deep, authoritative male
- `Lily` - Warm, engaging female

**OpenAI Voices:**
- `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`

#### Mixing Options

##### `--output, -o PATH`
Output file path.

**Default:** `<video_stem>_mixed.mp4`

##### `--volume FLOAT`
Audio volume adjustment in dB.

**Default:** `0.0` (no change)
**Range:** `-20.0` to `+20.0`

##### `--fit CHOICE`
How to handle video/audio length mismatch.

**Choices:**
- `shortest` - Trim output to shorter of video/audio (default)
- `longest` - Freeze last video frame to match longer audio
- `speed-match` - Adjust video playback speed to match audio

### Examples

#### TTS Generation and Mixing

```bash
# Generate TTS and mix with video
claude-studio render mix video.mp4 --text "Hello world, this is a test."

# Use specific voice
claude-studio render mix video.mp4 -t "Welcome to our demo" -v Adam

# Custom output file
claude-studio render mix video.mp4 -t "Product introduction" -o final.mp4
```

#### Audio File Mixing

```bash
# Mix with existing audio file
claude-studio render mix video.mp4 --audio narration.mp3

# Adjust audio volume
claude-studio render mix video.mp4 --audio narration.mp3 --volume -3.0

# Handle length mismatch
claude-studio render mix video.mp4 --audio long_narration.mp3 --fit longest
```

#### Advanced Mixing

```bash
# Speed-match video to audio duration
claude-studio render mix video.mp4 --audio narration.mp3 --fit speed-match

# Generate longer TTS with custom voice
claude-studio render mix video.mp4 \
  -t "This is a comprehensive explanation of our product features and benefits." \
  -v "21m00Tcm4TlvDq8ikWAM" \
  --fit longest \
  -o product_demo.mp4
```

### Fit Modes Explained

#### `shortest` (Default)
- Output duration = min(video_duration, audio_duration)
- Trims longer track to match shorter one
- **Use case**: Quick demos, matched content

#### `longest`  
- Output duration = max(video_duration, audio_duration)
- Freezes last video frame for longer audio
- Loops video for longer audio (future feature)
- **Use case**: Narration-driven content

#### `speed-match`
- Adjusts video playback speed to match audio duration
- Maintains audio quality and timing
- Video may appear slightly faster/slower
- **Use case**: Precise audio-video synchronization

### TTS Integration

#### Provider Selection

Mix command automatically selects TTS provider:

1. **ElevenLabs** (preferred if API key available)
   - Higher quality voice synthesis
   - More natural intonation
   - Voice ID support

2. **OpenAI TTS** (fallback)
   - HD quality (`tts-1-hd` model)
   - Reliable and fast
   - Standard voice options

#### Voice Configuration

```bash
# Set TTS provider preference
export TTS_PROVIDER=openai  # Force OpenAI TTS

# Configure API keys
claude-studio secrets set ELEVENLABS_API_KEY your_key
claude-studio secrets set OPENAI_API_KEY your_key
```

### Audio Processing

#### Volume Control

```bash
# Reduce audio volume by 6dB
claude-studio render mix video.mp4 --audio loud_audio.mp3 --volume -6.0

# Boost quiet audio by 3dB  
claude-studio render mix video.mp4 --audio quiet_audio.mp3 --volume +3.0
```

#### Format Handling

The mix command handles various audio formats:
- **Input**: MP3, WAV, AAC, M4A, FLAC
- **Output**: AAC in MP4 container (192kbps)
- **Sample Rate**: Preserves original or 44.1kHz
- **Channels**: Stereo or original channel configuration

### Integration with Production Pipeline

#### Testing Video Concepts

```bash
# Test video with different narration
claude-studio render mix concept_video.mp4 \
  -t "Version 1: Professional tone" \
  -v Rachel \
  -o test_v1.mp4

claude-studio render mix concept_video.mp4 \
  -t "Version 2: Conversational tone" \
  -v Adam \
  -o test_v2.mp4
```

#### Prototyping Audio-Video Combinations

```bash
# Test different fit modes
claude-studio render mix short_video.mp4 --audio long_narration.mp3 --fit longest -o extended.mp4
claude-studio render mix long_video.mp4 --audio short_narration.mp3 --fit shortest -o trimmed.mp4
```

#### Quick Video Enhancement

```bash
# Add narration to silent video
claude-studio render mix silent_demo.mp4 \
  -t "This demonstration shows our key features in action." \
  --fit longest \
  -o narrated_demo.mp4
```

## FFmpeg Requirements

Both render commands require FFmpeg installation:

### Installation

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### Verification

```bash
# Check FFmpeg installation
ffmpeg -version

# Check available codecs
ffmpeg -codecs | grep -E "(h264|aac)"
```

### Required Components

- **Video Codec**: libx264 for H.264 encoding
- **Audio Codec**: AAC for audio encoding
- **Formats**: MP4 container support
- **Filters**: Scale, concat, and overlay filters

## Performance and Quality

### Render Settings

#### Video Quality
- **Codec**: H.264 (libx264)
- **Preset**: `fast` (balanced speed/quality)
- **CRF**: 23 (high quality, reasonable size)
- **Pixel Format**: yuv420p (maximum compatibility)

#### Audio Quality
- **Codec**: AAC-LC
- **Bitrate**: 192kbps (high quality)
- **Sample Rate**: 44.1kHz or original
- **Channels**: Stereo

#### Optimization
- **Hardware Acceleration**: Uses system capabilities when available
- **Multi-threading**: Parallel processing for faster renders
- **Memory Management**: Efficient for large video files

### File Size Optimization

```bash
# High quality (larger file)
claude-studio render edl run_id -o hq_video.mp4

# For web streaming, use external tools:
ffmpeg -i hq_video.mp4 -crf 28 -preset slow web_optimized.mp4
```

## Troubleshooting

### Common Issues

#### FFmpeg Not Found
```bash
Error: FFmpeg not installed
```
**Solution:** Install FFmpeg using system package manager

#### Video Files Missing
```bash
Error: Video file not found: /path/to/scene_001.mp4
```
**Solution:** Verify production run completed successfully

#### Audio Generation Failed
```bash
Error: TTS generation failed - no audio data returned
```
**Solution:** Check API keys and TTS provider configuration

#### Format Compatibility
```bash
Error: Unsupported video format: .webm
```
**Solution:** Convert input video to MP4 format first

### Debug Information

#### EDL Rendering Debug
```bash
# Check EDL structure
cat artifacts/runs/<run_id>/edl/edit_candidates.json | jq .

# Verify video files exist
ls -la artifacts/runs/<run_id>/videos/

# Test individual video file
ffplay artifacts/runs/<run_id>/videos/scene_001_v0.mp4
```

#### Mix Command Debug
```bash
# Check input video properties
ffprobe -v quiet -print_format json -show_format video.mp4

# Test TTS generation separately
claude-studio test-provider elevenlabs -t "test" --live

# Verify audio file format
ffprobe -v quiet -print_format json -show_format audio.mp3
```

## Advanced Usage

### Batch Processing

```bash
# Render multiple EDL candidates
for candidate in standard_cut creative_cut minimal_cut; do
  claude-studio render edl 20260107_224324 -c "$candidate" -o "${candidate}.mp4"
done

# Mix multiple videos with same audio
for video in *.mp4; do
  claude-studio render mix "$video" --audio narration.mp3 -o "mixed_${video}"
done
```

### Custom Workflows

```bash
# Production to final video pipeline
#!/bin/bash
RUN_ID="$1"
OUTPUT_DIR="final_videos"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Render all candidates
claude-studio render edl "$RUN_ID" --list-candidates | \
  grep -E "^\│ [a-z_]+" | \
  awk '{print $2}' | \
  while read candidate; do
    claude-studio render edl "$RUN_ID" -c "$candidate" -o "${OUTPUT_DIR}/${candidate}.mp4"
  done

echo "All candidates rendered to $OUTPUT_DIR/"
```

### Quality Comparison

```bash
# Render with different quality settings using raw ffmpeg
claude-studio render edl run_id -o source.mp4

# High quality version
ffmpeg -i source.mp4 -crf 18 -preset slow high_quality.mp4

# Web optimized version  
ffmpeg -i source.mp4 -crf 28 -preset medium web_quality.mp4

# Mobile optimized version
ffmpeg -i source.mp4 -crf 30 -s 1280x720 mobile_quality.mp4
```

## Integration Examples

### Complete Production Workflow

```bash
#!/bin/bash
# Complete video production and rendering pipeline

# 1. Generate video
claude-studio produce -c "Product demonstration" -b 25 -d 45 --live -p luma

# 2. Resume if needed
claude-studio resume latest --live

# 3. Get run ID
RUN_ID=$(ls -t artifacts/runs/ | head -1)

# 4. Render final video
claude-studio render edl "$RUN_ID" -o final_product_demo.mp4

# 5. Create web-optimized version
ffmpeg -i final_product_demo.mp4 -crf 28 -s 1920x1080 web_demo.mp4

# 6. Upload to platforms
claude-studio upload youtube web_demo.mp4 -t "Product Demo" --privacy unlisted

echo "Production complete: web_demo.mp4"
```

### Audio-Video Testing Workflow  

```bash
#!/bin/bash  
# Test different audio options for video

VIDEO="concept_video.mp4"
BASE_NAME=$(basename "$VIDEO" .mp4)

# Generate TTS variations
claude-studio render mix "$VIDEO" -t "Professional presentation" -v Rachel -o "${BASE_NAME}_rachel.mp4"
claude-studio render mix "$VIDEO" -t "Professional presentation" -v Adam -o "${BASE_NAME}_adam.mp4"

# Test with existing audio
claude-studio render mix "$VIDEO" --audio background_music.mp3 --fit longest -o "${BASE_NAME}_music.mp4"

echo "Audio variations created:"
ls -la "${BASE_NAME}"_*.mp4
```

## Version History

- **0.6.0**: Enhanced audio mixing with multiple fit modes and TTS integration
- **0.5.x**: EDL rendering with transitions and text overlays
- **0.4.x**: Basic video concatenation and rendering