---
layout: default
title: Audio System Specification
---
# Audio System Specification

## Overview

The audio system handles all sound elements in video production: voiceovers, music, sound effects, and their synchronization with video. Audio type significantly impacts budget, production complexity, and final quality.

## Audio Production Tiers

### Tier 1: No Audio
- Silent video or music-only background
- Lowest cost, simplest production
- Use case: Social media clips, GIFs, demos

### Tier 2: Background Music Only
- Licensed music track underneath video
- No voice synchronization required
- Use case: Montages, mood pieces, b-roll

### Tier 3: Simple Audio Overlay
- Single voiceover track recorded separately
- Loose sync - audio plays over video
- Minor timing adjustments in post
- Use case: Explainers, tutorials, documentaries

### Tier 4: Time-Synced Voiceover
- Voiceover tightly synced to visual cues
- Script must match scene timing
- May require video retiming
- Use case: Product demos, presentations

### Tier 5: Full Audio Production
- Multiple tracks: VO, music, SFX
- Precise sync points throughout
- Sound design and mixing
- Use case: Commercials, professional content

## Data Models

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class AudioTier(Enum):
    NONE = "none"
    MUSIC_ONLY = "music_only"
    SIMPLE_OVERLAY = "simple_overlay"
    TIME_SYNCED = "time_synced"
    FULL_PRODUCTION = "full_production"

class VoiceStyle(Enum):
    PROFESSIONAL = "professional"      # Warm, authoritative
    CONVERSATIONAL = "conversational"  # Casual, friendly
    ENERGETIC = "energetic"            # Upbeat, excited
    CALM = "calm"                      # Soothing, measured
    DRAMATIC = "dramatic"              # Intense, storytelling

class MusicMood(Enum):
    UPBEAT = "upbeat"
    CORPORATE = "corporate"
    EMOTIONAL = "emotional"
    TENSE = "tense"
    AMBIENT = "ambient"
    NONE = "none"

@dataclass
class VoiceoverSpec:
    text: str                          # The script to speak
    voice_style: VoiceStyle
    target_duration: float             # Seconds
    sync_points: List['SyncPoint']     # When to hit specific words
    emphasis_words: List[str]          # Words to emphasize
    pace: str                          # "slow", "normal", "fast"

@dataclass
class SyncPoint:
    """A point where audio must align with video"""
    timestamp: float                   # Seconds into the scene
    word_or_phrase: str               # What should be said at this point
    visual_cue: str                   # What's happening visually
    tolerance: float = 0.5            # Acceptable timing variance (seconds)

@dataclass
class MusicSpec:
    mood: MusicMood
    tempo: str                        # "slow", "medium", "fast"
    duration: float                   # Total length needed
    fade_in: float                    # Seconds to fade in
    fade_out: float                   # Seconds to fade out
    duck_under_vo: bool               # Lower volume during voiceover
    duck_amount_db: float = -12       # How much to duck (dB)

@dataclass
class SoundEffectSpec:
    effect_type: str                  # "whoosh", "click", "ambient", etc.
    timestamp: float                  # When to play
    duration: float                   # How long
    volume_db: float                  # Relative volume

@dataclass
class SceneAudio:
    """Complete audio spec for a single scene"""
    scene_id: str
    audio_tier: AudioTier
    voiceover: Optional[VoiceoverSpec]
    music: Optional[MusicSpec]
    sound_effects: List[SoundEffectSpec]
    
    # Mixing notes
    vo_volume_db: float = 0           # Voiceover level
    music_volume_db: float = -18      # Music level (under VO)
    master_volume_db: float = 0       # Overall level

@dataclass
class ProjectAudio:
    """Audio spec for entire project"""
    audio_tier: AudioTier
    scenes: List[SceneAudio]
    
    # Global settings
    global_music: Optional[MusicSpec]  # Single track for whole video
    crossfade_duration: float = 0.5    # Between scenes
    
    # Output specs
    sample_rate: int = 48000
    bit_depth: int = 24
    channels: int = 2                  # Stereo
```

## Cost Models

```python
AUDIO_COST_MODELS = {
    AudioTier.NONE: {
        "cost_per_minute": 0,
        "description": "No audio production"
    },
    AudioTier.MUSIC_ONLY: {
        "cost_per_minute": 0.50,       # Music licensing
        "description": "Background music track"
    },
    AudioTier.SIMPLE_OVERLAY: {
        "cost_per_minute": 2.00,       # TTS generation
        "description": "AI voiceover, loose sync"
    },
    AudioTier.TIME_SYNCED: {
        "cost_per_minute": 5.00,       # TTS + timing adjustments
        "description": "Synced voiceover with music"
    },
    AudioTier.FULL_PRODUCTION: {
        "cost_per_minute": 15.00,      # Full audio production
        "description": "VO + music + SFX + mixing"
    }
}

# Voice generation providers
VOICE_PROVIDERS = {
    "elevenlabs": {
        "cost_per_minute": 0.30,
        "quality": "premium",
        "latency": "medium",
        "voices": ["professional", "conversational"]
    },
    "openai_tts": {
        "cost_per_minute": 0.15,
        "quality": "good",
        "latency": "fast",
        "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    },
    "google_tts": {
        "cost_per_minute": 0.04,
        "quality": "standard",
        "latency": "fast",
        "voices": ["standard", "wavenet", "neural2"]
    }
}
```

## Integration with Script Writer

The ScriptWriterAgent must now include audio specs:

```python
@dataclass
class Scene:
    scene_id: str
    title: str
    description: str
    duration: float
    visual_elements: List[str]
    
    # NEW: Audio elements
    voiceover_text: Optional[str]      # What to say during this scene
    sync_points: List[SyncPoint]       # Critical timing points
    music_transition: str              # "continue", "fade", "change"
    sfx_cues: List[str]               # Sound effects needed
    
    # Timing
    vo_start_offset: float = 0        # Delay before VO starts
    vo_end_buffer: float = 0.5        # Buffer after VO ends

    audio_notes: str                   # Director notes for audio
    transition_in: str
    transition_out: str
    prompt_hints: List[str]
```

## Script Writer Audio Prompt Addition

```
When breaking down scenes, include audio specifications:

For each scene, specify:
- voiceover_text: Exact words to be spoken (if any)
- sync_points: Critical moments where words must match visuals
  Example: At 2.5s, say "deploy" as the button is clicked
- music_transition: How music should behave
- sfx_cues: Sound effects needed

AUDIO GUIDELINES:
- Voiceover should be concise (roughly 150 words per minute)
- Leave 0.5s buffer at scene start/end for transitions
- Mark sync points for critical visual moments
- Consider pacing - not every scene needs narration

Return format addition:
{
  "scenes": [
    {
      "scene_id": "scene_1",
      "title": "Morning Standup",
      "description": "Developer joins video call",
      "duration": 5.0,
      "visual_elements": ["laptop", "video call"],
      
      "voiceover_text": "Every morning starts with a quick team sync.",
      "sync_points": [
        {"timestamp": 1.0, "word_or_phrase": "morning", "visual_cue": "laptop opens"}
      ],
      "music_transition": "fade_in",
      "sfx_cues": ["notification_sound"],
      "vo_start_offset": 0.5,
      "audio_notes": "Upbeat, welcoming tone"
    }
  ],
  "global_audio": {
    "music_mood": "corporate_upbeat",
    "music_tempo": "medium",
    "vo_style": "professional"
  }
}
```

## Audio Generator Agent Spec

```python
class AudioGeneratorAgent:
    """Generates audio tracks for video production"""
    
    async def generate_voiceover(
        self,
        script: str,
        voice_style: VoiceStyle,
        target_duration: float,
        provider: str = "elevenlabs"
    ) -> GeneratedAudio:
        """Generate voiceover from text"""
        pass
    
    async def generate_music(
        self,
        mood: MusicMood,
        duration: float,
        tempo: str
    ) -> GeneratedAudio:
        """Generate or select background music"""
        pass
    
    async def sync_audio_to_video(
        self,
        audio: GeneratedAudio,
        video: GeneratedVideo,
        sync_points: List[SyncPoint]
    ) -> SyncedAudio:
        """Adjust audio timing to match video sync points"""
        pass
    
    async def mix_tracks(
        self,
        voiceover: GeneratedAudio,
        music: GeneratedAudio,
        sfx: List[GeneratedAudio],
        mix_settings: MixSettings
    ) -> GeneratedAudio:
        """Mix multiple audio tracks together"""
        pass

@dataclass
class GeneratedAudio:
    audio_url: str
    duration: float
    format: str                       # "mp3", "wav", "aac"
    sample_rate: int
    generation_cost: float
    provider: str
    
@dataclass
class SyncedAudio:
    audio: GeneratedAudio
    time_adjustments: List[float]     # Stretches/compressions applied
    sync_accuracy: float              # 0-100, how well sync points hit
```

## EDL Audio Integration

The Editor Agent must include audio in EDL:

```python
@dataclass
class EditDecision:
    scene_id: str
    selected_variation: int
    video_url: str
    in_point: float
    out_point: float
    transition: str
    transition_duration: float
    
    # NEW: Audio elements
    audio_track: Optional[str]        # URL to audio file
    vo_in_point: float               # When VO starts (relative to video)
    vo_out_point: float              # When VO ends
    music_action: str                # "start", "continue", "duck", "fade_out"
    sfx_triggers: List[SFXTrigger]   # Sound effects to play

@dataclass
class SFXTrigger:
    sfx_url: str
    timestamp: float
    volume_db: float

@dataclass 
class EDLCandidate:
    candidate_id: str
    edits: List[EditDecision]
    total_duration: float
    estimated_quality: float
    editorial_approach: str
    reasoning: str
    
    # NEW: Audio master
    master_music_track: Optional[str]
    master_music_volume: float
    audio_mix_notes: str
```

## Producer Audio Budget Planning

The Producer must account for audio costs:

```python
def estimate_audio_cost(
    audio_tier: AudioTier,
    duration_seconds: float,
    num_scenes: int
) -> float:
    """Estimate audio production cost"""
    
    minutes = duration_seconds / 60
    base_cost = AUDIO_COST_MODELS[audio_tier]["cost_per_minute"] * minutes
    
    # Add per-scene overhead for sync work
    if audio_tier in [AudioTier.TIME_SYNCED, AudioTier.FULL_PRODUCTION]:
        sync_overhead = num_scenes * 0.50  # $0.50 per scene for sync
        base_cost += sync_overhead
    
    return base_cost

# Updated pilot planning prompt should include:
"""
Consider audio requirements:
- NONE: Silent or client-provided audio ($0)
- MUSIC_ONLY: Background music ($0.50/min)
- SIMPLE_OVERLAY: AI voiceover, loose sync ($2/min)
- TIME_SYNCED: Synced voiceover ($5/min)
- FULL_PRODUCTION: VO + music + SFX ($15/min)

Include audio_tier in pilot strategy based on request complexity.
"""
```

## Workflow Integration

```
1. Producer → Determines audio_tier based on request + budget

2. Script Writer → Generates scenes WITH audio specs
   - voiceover_text per scene
   - sync_points for critical moments
   - music/sfx cues

3. Audio Generator (NEW) → Creates audio assets
   - Generates voiceover
   - Selects/generates music
   - Gathers sound effects

4. Video Generator → Creates video (unchanged)

5. Audio Sync (NEW) → Aligns audio to video
   - Matches sync points
   - Adjusts timing if needed

6. QA Verifier → Now also checks audio sync quality

7. Editor → Creates EDL with full audio mix specs

8. Final Render → Combines video + mixed audio
```

## Audio QA Criteria

```python
@dataclass
class AudioQAResult:
    overall_score: float
    
    # Specific scores
    vo_clarity: float          # Is voiceover clear?
    sync_accuracy: float       # Do sync points hit?
    music_balance: float       # Is music level appropriate?
    audio_quality: float       # Any artifacts, clipping?
    pacing: float              # Does VO pacing feel natural?
    
    issues: List[str]
    suggestions: List[str]
```

## Implementation Priority

1. **Phase 1**: Add audio specs to Scene dataclass
2. **Phase 2**: Update ScriptWriter to generate VO text + sync points
3. **Phase 3**: Implement AudioGeneratorAgent
4. **Phase 4**: Add audio to EDL and Editor
5. **Phase 5**: Implement audio mixing and final render
