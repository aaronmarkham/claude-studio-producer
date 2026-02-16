# assemble - Rough Cut Video Assembly  

The `assemble` command creates rough cut videos from production assets with precise timing synchronization. This is Phase 5 of the Unified Production Architecture, handling timed assembly with figure sync points and Ken Burns effects.

## Synopsis

```bash
claude-studio assemble RUN_DIR [OPTIONS]
```

## Description

The assemble command takes production assets and creates a cohesive video with:

- Synchronized audio-visual timing
- Ken Burns effects on DALL-E generated images
- Figure synchronization to narration discussion points
- Text overlays for content without visuals
- Smooth transitions between segments

## Required Arguments

### `RUN_DIR`
Path to a video production run directory.

This should be the output directory from a `produce-video` or `produce` command containing the necessary assets and metadata.

**Examples:**
- `artifacts/video_production/20260207_143022`
- `./my_video_project`
- `../completed_runs/tutorial_video`

## Options

### `--output, -o PATH`
Output video path.

**Default:** `<run_dir>/assembly/rough_cut.mp4`

**Examples:**
- `--output final_video.mp4`
- `--output ./outputs/my_video.mp4`

### `--skip-existing / --no-skip-existing`
Skip re-rendering existing segments (default: True).

When enabled, segments that already exist will not be re-rendered, speeding up subsequent runs. Disable to force complete re-rendering.

## Examples

### Basic Usage

```bash
# Assemble from production run directory
claude-studio assemble artifacts/video_production/20260207_143022

# Custom output location
claude-studio assemble ./my_run --output final.mp4

# Force complete re-rendering
claude-studio assemble ./my_run --no-skip-existing
```

### Typical Workflow

```bash
# 1. Generate assets
claude-studio produce-video --script script.txt --live --kb-project my-kb

# 2. Assemble rough cut  
claude-studio assemble <output_directory>

# 3. Review result
open <output_directory>/assembly/rough_cut.mp4
```

## Assembly Process

### Phase 1: Asset Loading

1. **Production Artifacts Discovery**
   - Loads structured script (if available)
   - Reads content library with asset registry
   - Falls back to legacy asset manifest if needed

2. **Audio Analysis**
   - Discovers audio files by segment
   - Measures actual audio durations using ffprobe
   - Builds timing map for video synchronization

3. **Visual Asset Mapping**
   - Maps images to segments based on content library
   - Identifies KB figures, DALL-E images, and web images
   - Plans carry-forward for segments without visuals

### Phase 2: Assembly Manifest Creation

The assembly manifest specifies exactly how each segment should be rendered:

```json
{
  "segments": [
    {
      "segment_idx": 1,
      "display_mode": "dall_e",
      "visual": {"path": "images/scene_001.png"},
      "audio": {"path": "audio/audio_001.mp3", "duration_sec": 12.5},
      "text_preview": "Welcome to our explanation..."
    },
    {
      "segment_idx": 2, 
      "display_mode": "figure_sync",
      "visual": {"path": "images/kb_figure_002.png"},
      "audio": {"path": "audio/audio_002.mp3", "duration_sec": 8.3}
    }
  ]
}
```

### Phase 3: Segment Rendering

Each segment is rendered based on its display mode:

#### `dall_e` Mode
- DALL-E generated images get Ken Burns effects
- Smooth zoom from 1.0x to 1.08x scale over duration
- Ease-in-out motion for professional feel

#### `figure_sync` Mode  
- KB figures rendered as static holds
- No zoom effects to preserve figure clarity
- Perfect for technical diagrams and charts

#### `web_image` Mode
- Wikimedia/web images as static holds
- Maintains aspect ratio and centers content
- No effects to respect source material

#### `carry_forward` Mode
- Reuses the previous segment's image
- Maintains visual continuity
- Static display with new audio

#### `transcript` Mode
- Karaoke-style text overlay on dark background
- Word-by-word highlighting as narration progresses
- Used when no visual assets are available

### Phase 4: Final Assembly

1. **Audio Concatenation**
   - Combines all segment audio files
   - Maintains perfect timing synchronization
   - Creates single master audio track

2. **Video Concatenation**
   - Joins all rendered video segments
   - Adds master audio track overlay
   - Outputs final MP4 with AAC audio

## Display Modes Explained

### Ken Burns Effects (`dall_e`)

Applied to AI-generated images for engaging visual movement:

```
Initial: 1920x1080 centered image, scale=1.0
Final:   1920x1080 centered image, scale=1.08
Motion:  Smooth ease-in-out zoom over segment duration
```

Benefits:
- Adds professional visual interest
- Prevents static appearance
- Subtle enough not to distract from content

### Static Hold (all others)

Used for:
- **KB Figures**: Preserves technical accuracy
- **Web Images**: Respects source licensing  
- **Carry Forward**: Maintains visual continuity

No zoom or pan effects to ensure:
- Text in figures remains readable
- Charts and diagrams stay clear
- Attribution requirements are met

### Karaoke Text (`transcript`)

Progressive word highlighting:
- **White**: Current word being spoken
- **Grey**: Already spoken words  
- **Dark grey**: Upcoming words
- **Black shadow**: Text outline for readability

Font: OpenDyslexic with fallback to system fonts

## Timing Synchronization

### Audio-Led Timing

Assembly uses actual audio durations to drive video timing:

1. **Audio Measurement**: Each audio file probed for exact duration
2. **Video Matching**: Video segments stretched/cropped to match audio
3. **Perfect Sync**: No drift between audio and visual content

### Figure Sync Points

When KB figures are used:
- Figures appear when narration discusses them
- Timing based on content analysis from structured script
- Visual-audio alignment for maximum comprehension

## Output Structure

Assembly creates organized output:

```
<run_dir>/assembly/
├── segments/                   # Individual video segments
│   ├── segment_001.mp4
│   ├── segment_002.mp4
│   └── ...
├── audio_combined.mp3         # Master audio track
├── rough_cut.mp4              # Final assembled video
└── assembly_manifest.json     # Assembly instructions
```

### Assembly Manifest

The manifest documents the assembly process:

```json
{
  "assembly_id": "asm_20260207_143022",
  "created_at": "2026-02-07T14:30:22Z",
  "total_segments": 15,
  "total_duration_sec": 180.5,
  "segments": [
    {
      "segment_idx": 1,
      "display_mode": "dall_e",
      "start_time": 0.0,
      "end_time": 12.5,
      "visual": {
        "path": "images/scene_001.png",
        "source": "dalle",
        "status": "approved"
      },
      "audio": {
        "path": "audio/audio_001.mp3", 
        "duration_sec": 12.5,
        "source": "elevenlabs"
      }
    }
  ]
}
```

## Quality Control

### Pre-Assembly Checks

The assembler performs validation:

1. **Asset Availability**: Verifies all required files exist
2. **Duration Matching**: Ensures audio and visual alignment
3. **Format Compatibility**: Checks file formats are supported
4. **Resolution Consistency**: Validates video dimensions

### Error Recovery

- **Missing Images**: Falls back to transcript overlay mode
- **Missing Audio**: Creates silent segments with visual-only
- **Corrupt Files**: Skips problematic segments with warnings
- **Duration Mismatches**: Adjusts timing to prevent sync issues

## Integration with Asset Management

Assembly respects asset approval status:

```bash
# Review assets before assembly
claude-studio assets list <run_dir>

# Approve specific assets
claude-studio assets approve <run_dir> --image 1,3,5 --audio all

# Assemble with approved assets only
claude-studio assemble <run_dir>
```

Assets with `rejected` status are handled gracefully:
- Rejected images fall back to text overlay
- Rejected audio creates silent segments
- Assembly continues with available assets

## Performance Optimization

### Segment Caching

The `--skip-existing` option (default: True) provides:
- **Fast Iteration**: Only render changed segments
- **Resumable Assembly**: Continue after interruptions
- **Selective Updates**: Update specific segments only

### FFmpeg Optimization

Assembly uses optimized FFmpeg settings:
- **Fast Preset**: Balanced quality and speed
- **CRF 23**: High quality with reasonable file size
- **AAC Audio**: Universal compatibility at 192kbps
- **YUV420P**: Maximum player compatibility

## System Requirements

### FFmpeg Required

Assembly requires FFmpeg installation:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian  
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/
```

### File System

- **Disk Space**: ~2x final video size for temporary files
- **Permissions**: Write access to run directory
- **Format Support**: PNG, JPG, MP3, MP4 file handling

## Troubleshooting

### Common Issues

#### FFmpeg Not Found
```bash
Error: FFmpeg not installed
```
**Solution:** Install FFmpeg using system package manager

#### Missing Assets
```bash
Warning: Image not found: images/scene_005.png
```
**Solution:** Check asset generation completed successfully

#### Audio Sync Issues
```bash
Warning: Audio duration mismatch: expected 10s, got 8s  
```
**Solution:** Regenerate audio or use `--no-skip-existing`

#### Permission Errors
```bash
Error: Permission denied writing to assembly/rough_cut.mp4
```
**Solution:** Check directory permissions and disk space

### Debug Mode

For detailed troubleshooting:

```bash
# Enable verbose output
claude-studio assemble <run_dir> --output debug.mp4 2>&1 | tee assembly.log

# Check assembly manifest
cat <run_dir>/assembly/assembly_manifest.json | jq .

# Verify individual segments
ls -la <run_dir>/assembly/segments/
```

## Advanced Usage

### Custom Processing

For specialized assembly requirements:

```bash
# Force complete re-render
claude-studio assemble <run_dir> --no-skip-existing

# Assembly with custom timing
# (Modify assembly manifest then assemble)
vim <run_dir>/assembly/assembly_manifest.json
claude-studio assemble <run_dir> --no-skip-existing
```

### Batch Processing

```bash
# Assemble multiple runs
for run_dir in artifacts/video_production/*/; do
  claude-studio assemble "$run_dir" --output "final_$(basename "$run_dir").mp4"
done
```

### Pipeline Integration

```bash
#!/bin/bash
# Complete video production pipeline

# Generate assets
claude-studio produce-video --script "$1" --live --kb-project research

# Get output directory
OUTPUT_DIR=$(ls -t artifacts/video_production/ | head -1)

# Assemble video
claude-studio assemble "artifacts/video_production/$OUTPUT_DIR"

# Upload result
claude-studio upload youtube \
  "artifacts/video_production/$OUTPUT_DIR/assembly/rough_cut.mp4" \
  --title "$(basename "$1" .txt)" \
  --privacy unlisted
```

## Quality Settings

Assembly provides high-quality output optimized for:

### Video Quality
- **Resolution**: 1920x1080 (Full HD)
- **Codec**: H.264 with CRF 23
- **Frame Rate**: 30fps for smooth playback
- **Color Space**: YUV420P for compatibility

### Audio Quality  
- **Codec**: AAC-LC
- **Bitrate**: 192kbps (high quality)
- **Sample Rate**: 44.1kHz or original
- **Channels**: Stereo or original

### File Optimization
- **Container**: MP4 for universal compatibility
- **Seeking**: Optimized for web streaming
- **Metadata**: Includes creation timestamp and source info

## Version History

- **0.6.0**: Unified Production Architecture with content library
- **0.5.x**: Ken Burns effects and figure synchronization
- **0.4.x**: Basic segment concatenation