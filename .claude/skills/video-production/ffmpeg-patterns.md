# FFmpeg Command Patterns

Reference document for common FFmpeg operations in the production pipeline.

## Basic Encoding

### 1080p H.264 (Standard)
```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -preset medium -crf 23 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  output.mp4
```

### 4K H.265 (Pro)
```bash
ffmpeg -i input.mp4 \
  -c:v libx265 -preset slow -crf 20 \
  -c:a aac -b:a 320k \
  -movflags +faststart \
  output.mp4
```

## Scene Concatenation

### With Crossfade
```bash
ffmpeg -i scene1.mp4 -i scene2.mp4 \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=4.5[v]; \
                   [0:a][1:a]acrossfade=d=0.5[a]" \
  -map "[v]" -map "[a]" \
  output.mp4
```

### Simple Concat (No Transition)
```bash
# Create concat file
echo "file 'scene1.mp4'" > list.txt
echo "file 'scene2.mp4'" >> list.txt

ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
```

## Audio Operations

### Add Music Layer with Ducking
```bash
ffmpeg -i video.mp4 -i music.mp3 \
  -filter_complex "[1:a]volume=0.2[music]; \
                   [0:a][music]amix=inputs=2:duration=first[aout]" \
  -map 0:v -map "[aout]" \
  output.mp4
```

### Normalize Audio (EBU R128)
```bash
ffmpeg -i input.mp4 \
  -af loudnorm=I=-14:LRA=11:TP=-1 \
  -c:v copy \
  output.mp4
```

### Replace Audio Track
```bash
ffmpeg -i video.mp4 -i audio.mp3 \
  -c:v copy -c:a aac \
  -map 0:v:0 -map 1:a:0 \
  output.mp4
```

## Scaling and Aspect Ratio

### Scale to 1080p (Preserve Aspect)
```bash
ffmpeg -i input.mp4 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:-1:-1" \
  output.mp4
```

### 9:16 Vertical (TikTok/Reels)
```bash
ffmpeg -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" \
  output.mp4
```

## Frame Extraction (for QA)

### Extract Frames at Intervals
```bash
ffmpeg -i input.mp4 \
  -vf "fps=1" \
  frame_%04d.png
```

### Extract Specific Frame
```bash
ffmpeg -i input.mp4 \
  -ss 00:00:05 -frames:v 1 \
  frame.png
```

## Quality Analysis

### PSNR/SSIM Comparison
```bash
ffmpeg -i reference.mp4 -i distorted.mp4 \
  -lavfi "[0:v][1:v]psnr" -f null -
```

### Get Video Info
```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
```

## Common Pitfalls

1. **Audio sync issues**: Always use `-async 1` if audio drifts
2. **Variable framerate**: Normalize with `-vsync cfr` before processing
3. **Color space**: Preserve with `-colorspace bt709` for web delivery
4. **Faststart**: Always add `-movflags +faststart` for web playback

## Performance Tips

- Use `-threads 0` to auto-detect CPU cores
- For batch processing, use `-y` to overwrite without prompting
- Preview with `-t 10` to limit to first 10 seconds
- Use hardware encoding (`h264_nvenc`) if GPU available
