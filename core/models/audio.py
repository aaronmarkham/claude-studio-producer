"""
Audio Data Models

Defines all audio-related data structures for the video production system:
- Audio production tiers
- Voiceover specifications with sync points
- Music and sound effect specs
- Scene and project audio configurations
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class AudioTier(Enum):
    """Audio production quality tiers with increasing complexity and cost"""
    NONE = "none"                          # Silent video or music-only
    MUSIC_ONLY = "music_only"             # Background music track
    SIMPLE_OVERLAY = "simple_overlay"     # Single voiceover, loose sync
    TIME_SYNCED = "time_synced"           # Voiceover synced to visual cues
    FULL_PRODUCTION = "full_production"   # VO + music + SFX + mixing


class VoiceStyle(Enum):
    """Voice character types for TTS generation"""
    PROFESSIONAL = "professional"          # Warm, authoritative
    CONVERSATIONAL = "conversational"      # Casual, friendly
    ENERGETIC = "energetic"                # Upbeat, excited
    CALM = "calm"                          # Soothing, measured
    DRAMATIC = "dramatic"                  # Intense, storytelling


class MusicMood(Enum):
    """Background music emotional tones"""
    UPBEAT = "upbeat"
    CORPORATE = "corporate"
    EMOTIONAL = "emotional"
    TENSE = "tense"
    AMBIENT = "ambient"
    NONE = "none"


@dataclass
class SyncPoint:
    """A point where audio must align with video"""
    timestamp: float                       # Seconds into the scene
    word_or_phrase: str                   # What should be said at this point
    visual_cue: str                       # What's happening visually
    tolerance: float = 0.5                # Acceptable timing variance (seconds)


@dataclass
class VoiceoverSpec:
    """Specification for voiceover generation"""
    text: str                              # The script to speak
    voice_style: VoiceStyle
    target_duration: Optional[float] = None  # Desired duration in seconds
    sync_points: List[SyncPoint] = field(default_factory=list)
    emphasis_words: List[str] = field(default_factory=list)  # Words to emphasize
    pace: str = "normal"                   # "slow", "normal", "fast"


@dataclass
class MusicSpec:
    """Specification for background music"""
    mood: MusicMood
    tempo: str                             # "slow", "medium", "fast"
    duration: float                        # Total length needed
    fade_in: float = 0.5                  # Seconds to fade in
    fade_out: float = 0.5                 # Seconds to fade out
    duck_under_vo: bool = True            # Lower volume during voiceover
    duck_amount_db: float = -12           # How much to duck (dB)


@dataclass
class SoundEffectSpec:
    """Specification for a sound effect"""
    effect_type: str                       # "whoosh", "click", "notification", etc.
    timestamp: float                       # When to play (seconds)
    duration: float = 1.0                 # How long
    volume_db: float = -6                 # Relative volume


@dataclass
class SceneAudio:
    """Complete audio specification for a single scene"""
    scene_id: str
    audio_tier: AudioTier
    voiceover: Optional[VoiceoverSpec] = None
    music: Optional[MusicSpec] = None
    sound_effects: List[SoundEffectSpec] = field(default_factory=list)

    # Mixing notes
    vo_volume_db: float = 0               # Voiceover level
    music_volume_db: float = -18          # Music level (under VO)
    master_volume_db: float = 0           # Overall level


@dataclass
class ProjectAudio:
    """Audio specification for entire project"""
    audio_tier: AudioTier
    scenes: List[SceneAudio] = field(default_factory=list)

    # Global settings
    global_music: Optional[MusicSpec] = None  # Single track for whole video
    crossfade_duration: float = 0.5       # Between scenes

    # Output specs
    sample_rate: int = 48000
    bit_depth: int = 24
    channels: int = 2                      # Stereo


# Audio generation result models (for AudioGeneratorAgent)

@dataclass
class WordTiming:
    """Timing information for a single word in voiceover"""
    word: str
    start_time: float
    end_time: float


@dataclass
class GeneratedAudio:
    """Result of audio generation"""
    audio_id: str
    audio_url: str
    audio_type: str                        # "voiceover", "music", "sfx"
    duration: float                        # Seconds
    format: str                            # "mp3", "wav", "aac"
    sample_rate: int                       # 44100, 48000
    bit_depth: int = 24
    channels: int = 2                      # 1 (mono), 2 (stereo)
    generation_cost: float = 0.0
    provider: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class VoiceoverResult:
    """Result of voiceover generation with timing"""
    audio: GeneratedAudio
    words_per_minute: float
    actual_duration: float
    target_duration: float
    timing_map: List[WordTiming] = field(default_factory=list)


@dataclass
class SyncPointResult:
    """Result of sync point alignment"""
    sync_point: SyncPoint
    actual_timestamp: float
    target_timestamp: float
    error_ms: float                        # How far off (milliseconds)
    within_tolerance: bool


@dataclass
class TimeStretch:
    """Time stretching applied to audio"""
    start_time: float
    end_time: float
    stretch_factor: float                  # 1.0 = no change, 0.9 = faster, 1.1 = slower


@dataclass
class SyncedAudioResult:
    """Result of audio synchronization"""
    original_audio: GeneratedAudio
    synced_audio: GeneratedAudio
    sync_points_hit: List[SyncPointResult] = field(default_factory=list)
    overall_sync_accuracy: float = 0.0    # 0-100
    time_stretches_applied: List[TimeStretch] = field(default_factory=list)


@dataclass
class MixSettings:
    """Audio mixing configuration"""
    vo_volume_db: float = 0
    music_volume_db: float = -18
    sfx_volume_db: float = -6
    ducking_enabled: bool = True
    ducking_amount_db: float = -12
    ducking_attack_ms: float = 50
    ducking_release_ms: float = 200
    master_limiter: bool = True
    target_loudness_lufs: float = -14      # YouTube/streaming standard


@dataclass
class MixedAudio:
    """Result of audio mixing"""
    audio: GeneratedAudio
    tracks_mixed: int
    mix_settings: MixSettings
    peak_level_db: float
    loudness_lufs: float                   # Broadcast standard loudness


@dataclass
class AudioQAResult:
    """Quality assessment result for audio"""
    overall_score: float

    # Specific scores
    vo_clarity: float = 0.0                # Is voiceover clear?
    sync_accuracy: float = 0.0             # Do sync points hit?
    music_balance: float = 0.0             # Is music level appropriate?
    audio_quality: float = 0.0             # Any artifacts, clipping?
    pacing: float = 0.0                    # Does VO pacing feel natural?

    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
