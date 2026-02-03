# Video Production Tier Specifications

Reference document for production quality tiers.

## Tier Overview

### Micro Tier ($1-5)

**Use Case**: Quick tests, social clips, prototypes

**Video Specs**:
- Resolution: 1280x720 (720p)
- Frame Rate: 24fps
- Bitrate: 2-4 Mbps
- Codec: H.264 Main Profile

**Audio Specs**:
- Sample Rate: 44.1kHz
- Bitrate: 128kbps
- Codec: AAC

**Constraints**:
- Max scenes: 3
- Max duration: 30 seconds
- Single provider only
- No music layer

### Standard Tier ($5-20)

**Use Case**: Social media content, shorts

**Video Specs**:
- Resolution: 1920x1080 (1080p)
- Frame Rate: 30fps
- Bitrate: 6-10 Mbps
- Codec: H.264 High Profile

**Audio Specs**:
- Sample Rate: 48kHz
- Bitrate: 192kbps
- Codec: AAC

**Constraints**:
- Max scenes: 8
- Max duration: 90 seconds
- Multi-provider allowed
- Optional music layer

### Premium Tier ($20-50)

**Use Case**: YouTube videos, presentations

**Video Specs**:
- Resolution: 1920x1080 (1080p)
- Frame Rate: 30fps
- Bitrate: 12-16 Mbps
- Codec: H.264 High Profile or H.265

**Audio Specs**:
- Sample Rate: 48kHz
- Bitrate: 256kbps
- Codec: AAC

**Constraints**:
- Max scenes: 15
- Max duration: 180 seconds
- Multi-provider + fallbacks
- Music + sound effects

### Pro Tier ($50+)

**Use Case**: Professional content, ads

**Video Specs**:
- Resolution: 3840x2160 (4K)
- Frame Rate: 30/60fps
- Bitrate: 25-50 Mbps
- Codec: H.265 or ProRes

**Audio Specs**:
- Sample Rate: 48kHz
- Bitrate: 320kbps
- Codec: AAC or FLAC

**Constraints**:
- Unlimited scenes
- Unlimited duration
- Full provider selection
- Full audio production

## Tier Selection Logic

```python
def select_tier(budget: float) -> str:
    if budget < 5:
        return "micro"
    elif budget < 20:
        return "standard"
    elif budget < 50:
        return "premium"
    else:
        return "pro"
```

## Quality Validation by Tier

### Micro
- Video plays without errors
- Audio is audible
- Aspect ratio correct

### Standard
- All micro checks +
- No visible compression artifacts
- Audio levels normalized
- Smooth transitions

### Premium
- All standard checks +
- Color consistency across scenes
- Audio ducking for music
- End card present

### Pro
- All premium checks +
- 4K quality verification
- Advanced color grading
- Multi-track audio mix
