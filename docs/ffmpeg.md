---
layout: default
title: FFmpeg Integration
---

# FFmpeg Integration

Claude Studio Producer uses FFmpeg for professional video and audio processing. This page covers installation, features, and common operations.

## Installation

### macOS
```bash
brew install ffmpeg
```

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Windows
Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use Chocolatey:
```powershell
choco install ffmpeg
```

### Verify Installation
```bash
ffmpeg -version
```

## Features

### Video + Audio Mixing

The `render mix` command combines video and audio using FFmpeg with three fit modes for handling length mismatches.

#### Speed-Match Mode (Recommended for Motion Content)

Adjusts video playback speed to match audio duration. Keeps animation flowing smoothly throughout.

```bash
claude-studio render mix video.mp4 --audio narration.mp3 -o output.mp4 --fit speed-match
```

**Use when:**
- You want continuous motion/animation throughout
- The video has dynamic content (steam, movement, transitions)
- Creating a meditative or cinematic feel

**Example:** Steam animation that continues smoothly throughout narration

#### Longest Mode (Freeze-Frame)

Extends video by freezing the last frame to match longer audio duration.

```bash
claude-studio render mix video.mp4 --audio narration.mp3 -o output.mp4 --fit longest
```

**Use when:**
- The last frame works well as a static backdrop
- You want the full audio without speed changes
- The video ends on a good "hold" moment

**Example:** Tutorial ending on a completed diagram while explanation continues

#### Shortest Mode (Truncate)

Trims both video and audio to match the shorter duration.

```bash
claude-studio render mix video.mp4 --audio narration.mp3 -o output.mp4 --fit shortest
```

**Use when:**
- Precise timing is critical
- You prefer cutting content over speed changes
- Creating social media clips with tight timing

**Example:** 5-second Instagram story that must end exactly at 5 seconds

### Volume Control

Adjust audio volume during mixing (in decibels):

```bash
# Increase volume by 6dB
claude-studio render mix video.mp4 --audio narration.mp3 --volume 6

# Decrease volume by 3dB
claude-studio render mix video.mp4 --audio narration.mp3 --volume -3
```

### EDL Rendering

Render Edit Decision Lists from production runs:

```bash
# Render a production run's EDL
claude-studio render edl 20260107_224324
```

This combines multiple video clips based on the editor agent's decisions.

## Advanced FFmpeg Operations

### Manual Video Processing

For advanced users who want direct FFmpeg access:

#### Extract Audio from Video
```bash
ffmpeg -i video.mp4 -vn -acodec copy audio.aac
```

#### Change Video Speed
```bash
# 2x speed
ffmpeg -i input.mp4 -filter:v "setpts=0.5*PTS" -an output.mp4

# 0.5x speed (slow motion)
ffmpeg -i input.mp4 -filter:v "setpts=2.0*PTS" -an output.mp4
```

#### Concatenate Videos
```bash
# Create file list
echo "file 'video1.mp4'" > list.txt
echo "file 'video2.mp4'" >> list.txt

# Concatenate
ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
```

#### Add Watermark
```bash
ffmpeg -i video.mp4 -i logo.png -filter_complex "overlay=10:10" output.mp4
```

#### Convert Format
```bash
# MP4 to WebM
ffmpeg -i input.mp4 -c:v libvpx-vp9 -c:a libopus output.webm

# MP4 to GIF
ffmpeg -i input.mp4 -vf "fps=10,scale=320:-1:flags=lanczos" output.gif
```

## FFmpeg in the Pipeline

### Render Module

The `core.renderer` module provides a Python interface to FFmpeg:

```python
from core.renderer import FFmpegRenderer

renderer = FFmpegRenderer()

# Mix video and audio
await renderer.mix_video_audio(
    video_path="input.mp4",
    audio_path="narration.mp3",
    output_path="output.mp4",
    fit_mode="speed-match"
)
```

### Fit Mode Implementation

Speed matching uses FFmpeg's `setpts` filter:

```bash
# Internal command for 2.5x slower playback
ffmpeg -i input.mp4 -filter:v "setpts=2.5*PTS" -i audio.mp3 -c:v libx264 -c:a aac output.mp4
```

### Frame Extraction (Future)

Planned for QA verification with Claude Vision:

```python
# Extract frame at 2.5 seconds
await renderer.extract_frame(
    video_path="video.mp4",
    timestamp=2.5,
    output_path="frame.jpg"
)
```

## Troubleshooting

### FFmpeg Not Found

**Error:** `ffmpeg: command not found`

**Solution:** Install FFmpeg using one of the installation methods above, then verify with `ffmpeg -version`.

### Codec Issues

**Error:** `Unknown encoder 'libx264'`

**Solution:** Your FFmpeg build may not include H.264 support. Install a full build:

```bash
# macOS
brew reinstall ffmpeg --with-x264

# Ubuntu
sudo apt install ffmpeg libavcodec-extra
```

### Audio/Video Out of Sync

**Issue:** Audio and video don't align properly

**Solution:** Use speed-match mode or check if your source files have variable frame rates (VFR). Convert to constant frame rate (CFR):

```bash
ffmpeg -i input_vfr.mp4 -vsync cfr -r 30 output_cfr.mp4
```

### Large File Sizes

**Issue:** Output files are too large

**Solution:** Adjust quality settings:

```bash
# Lower quality, smaller file
ffmpeg -i input.mp4 -c:v libx264 -crf 28 -preset fast output.mp4

# Higher quality, larger file
ffmpeg -i input.mp4 -c:v libx264 -crf 18 -preset slow output.mp4
```

CRF values: 0 (lossless) to 51 (worst quality). Recommended: 18-28.

## Performance Tips

1. **Use hardware acceleration** (if available):
   ```bash
   ffmpeg -hwaccel auto -i input.mp4 ...
   ```

2. **Choose faster presets** for testing:
   ```bash
   -preset ultrafast  # Fastest, larger files
   -preset fast       # Good balance
   -preset slow       # Better quality, slower
   ```

3. **Limit resolution** for social media:
   ```bash
   # 1080p
   ffmpeg -i input.mp4 -vf scale=1920:1080 output.mp4

   # 720p
   ffmpeg -i input.mp4 -vf scale=1280:720 output.mp4
   ```

## Reference

- [FFmpeg Official Documentation](https://ffmpeg.org/documentation.html)
- [FFmpeg Wiki](https://trac.ffmpeg.org/wiki)
- [FFmpeg Filters](https://ffmpeg.org/ffmpeg-filters.html)

---

[← Back to Home](index.html) | [View Examples →](examples.html)
