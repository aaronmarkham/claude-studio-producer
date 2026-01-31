---
layout: default
title: Audio Generator Agent Specification
---
# Audio Generator Agent Specification

## Purpose

The Audio Generator Agent creates all audio assets for video production: voiceovers, background music, and sound effects. It handles text-to-speech generation, music selection/generation, and audio synchronization with video.

## Inputs

- `scene_audio`: SceneAudio specification from ScriptWriter
- `audio_tier`: Production quality tier
- `budget_limit`: Maximum spend for audio
- `sync_requirements`: Video timing for sync points

## Outputs

```python
@dataclass
class GeneratedAudio:
    audio_id: str
    audio_url: str
    audio_type: str              # "voiceover", "music", "sfx"
    duration: float              # Seconds
    format: str                  # "mp3", "wav", "aac"
    sample_rate: int             # 44100, 48000
    bit_depth: int               # 16, 24
    channels: int                # 1 (mono), 2 (stereo)
    generation_cost: float
    provider: str
    metadata: Dict

@dataclass
class VoiceoverResult:
    audio: GeneratedAudio
    words_per_minute: float
    actual_duration: float
    target_duration: float
    timing_map: List[WordTiming]  # When each word is spoken

@dataclass
class WordTiming:
    word: str
    start_time: float
    end_time: float

@dataclass
class SyncedAudioResult:
    original_audio: GeneratedAudio
    synced_audio: GeneratedAudio
    sync_points_hit: List[SyncPointResult]
    overall_sync_accuracy: float  # 0-100
    time_stretches_applied: List[TimeStretch]

@dataclass
class SyncPointResult:
    sync_point: SyncPoint
    actual_timestamp: float
    target_timestamp: float
    error_ms: float              # How far off (milliseconds)
    within_tolerance: bool

@dataclass
class TimeStretch:
    start_time: float
    end_time: float
    stretch_factor: float        # 1.0 = no change, 0.9 = faster, 1.1 = slower

@dataclass
class MixedAudio:
    audio: GeneratedAudio
    tracks_mixed: int
    mix_settings: MixSettings
    peak_level_db: float
    loudness_lufs: float         # Broadcast standard loudness

@dataclass
class MixSettings:
    vo_volume_db: float = 0
    music_volume_db: float = -18
    sfx_volume_db: float = -6
    ducking_enabled: bool = True
    ducking_amount_db: float = -12
    ducking_attack_ms: float = 50
    ducking_release_ms: float = 200
    master_limiter: bool = True
    target_loudness_lufs: float = -14  # YouTube/streaming standard
```

## Supported Providers

### Voiceover Providers

#### ElevenLabs (Premium)
```python
ELEVENLABS_CONFIG = {
    "api_key_env": "ELEVENLABS_API_KEY",
    "base_url": "https://api.elevenlabs.io/v1",
    "cost_per_1k_chars": 0.30,
    "max_chars_per_request": 5000,
    "supported_voices": [
        "rachel",      # Professional female
        "drew",        # Professional male
        "clyde",       # Conversational male
        "domi",        # Energetic female
        "dave",        # Conversational male
        "fin",         # Dramatic male
        "sarah",       # Calm female
    ],
    "voice_settings": {
        "stability": 0.5,        # 0-1, higher = more consistent
        "similarity_boost": 0.75, # 0-1, higher = more like original
        "style": 0.5,            # 0-1, style exaggeration
        "use_speaker_boost": True
    },
    "quality": "premium",
    "latency": "medium"
}
```

#### OpenAI TTS
```python
OPENAI_TTS_CONFIG = {
    "api_key_env": "OPENAI_API_KEY",
    "base_url": "https://api.openai.com/v1/audio/speech",
    "cost_per_1k_chars": 0.015,  # TTS standard
    "cost_per_1k_chars_hd": 0.030,  # TTS HD
    "supported_voices": [
        "alloy",       # Neutral
        "echo",        # Male
        "fable",       # British male
        "onyx",        # Deep male
        "nova",        # Female
        "shimmer"      # Female
    ],
    "models": ["tts-1", "tts-1-hd"],
    "quality": "good",
    "latency": "fast"
}
```

#### Google Cloud TTS
```python
GOOGLE_TTS_CONFIG = {
    "api_key_env": "GOOGLE_CLOUD_API_KEY",
    "cost_per_1m_chars_standard": 4.00,
    "cost_per_1m_chars_wavenet": 16.00,
    "cost_per_1m_chars_neural2": 16.00,
    "voice_types": ["Standard", "WaveNet", "Neural2"],
    "languages": 40,  # Number of supported languages
    "quality": "standard_to_premium",
    "latency": "fast"
}
```

### Music Providers

#### Mubert (AI Generated)
```python
MUBERT_CONFIG = {
    "api_key_env": "MUBERT_API_KEY",
    "base_url": "https://api.mubert.com/v2",
    "cost_per_track": 0.50,
    "max_duration": 300,  # 5 minutes
    "moods": [
        "upbeat", "corporate", "emotional", 
        "tense", "ambient", "happy", "sad"
    ],
    "genres": [
        "electronic", "acoustic", "orchestral",
        "pop", "rock", "jazz", "ambient"
    ],
    "quality": "good",
    "license": "royalty_free"
}
```

#### Epidemic Sound (Licensed)
```python
EPIDEMIC_CONFIG = {
    "api_key_env": "EPIDEMIC_API_KEY",
    "cost_per_track": 2.00,  # Per use
    "subscription_available": True,
    "quality": "premium",
    "license": "sync_license"
}
```

#### Soundraw (AI Generated)
```python
SOUNDRAW_CONFIG = {
    "api_key_env": "SOUNDRAW_API_KEY",
    "cost_per_track": 0.75,
    "customization": True,  # Can adjust tempo, mood, instruments
    "max_duration": 300,
    "quality": "good"
}
```

### Sound Effects Providers

#### Freesound (Free)
```python
FREESOUND_CONFIG = {
    "api_key_env": "FREESOUND_API_KEY",
    "base_url": "https://freesound.org/apiv2",
    "cost": 0,  # Free with attribution
    "license": "creative_commons",
    "quality": "variable"
}
```

#### Artlist (Premium)
```python
ARTLIST_CONFIG = {
    "subscription_required": True,
    "quality": "premium",
    "categories": ["whoosh", "impact", "ui", "ambient", "foley"]
}
```

## Behavior

### 1. Voiceover Generation

```python
async def generate_voiceover(
    self,
    text: str,
    voice_style: VoiceStyle,
    target_duration: Optional[float] = None,
    provider: str = "elevenlabs"
) -> VoiceoverResult:
    """
    Generate voiceover from text
    
    Args:
        text: Script to speak
        voice_style: Desired voice character
        target_duration: If set, adjust speech rate to hit this duration
        provider: TTS provider to use
        
    Returns:
        VoiceoverResult with audio and timing information
    """
    
    # 1. Select voice based on style
    voice_id = self._select_voice(voice_style, provider)
    
    # 2. Estimate natural duration
    word_count = len(text.split())
    natural_duration = word_count / 2.5  # ~150 WPM = 2.5 words/sec
    
    # 3. Calculate speech rate adjustment if target specified
    if target_duration:
        rate_adjustment = natural_duration / target_duration
        # Clamp to reasonable range (0.8x to 1.3x)
        rate_adjustment = max(0.8, min(1.3, rate_adjustment))
    else:
        rate_adjustment = 1.0
    
    # 4. Generate audio
    audio = await self._call_tts_api(
        text=text,
        voice_id=voice_id,
        rate=rate_adjustment,
        provider=provider
    )
    
    # 5. Get word timings
    timing_map = await self._get_word_timings(audio, text)
    
    return VoiceoverResult(
        audio=audio,
        words_per_minute=word_count / (audio.duration / 60),
        actual_duration=audio.duration,
        target_duration=target_duration or audio.duration,
        timing_map=timing_map
    )
```

### 2. Audio Synchronization

```python
async def sync_to_video(
    self,
    voiceover: VoiceoverResult,
    sync_points: List[SyncPoint],
    video_duration: float
) -> SyncedAudioResult:
    """
    Adjust voiceover timing to hit sync points
    
    Uses time-stretching to align specific words with visual cues
    without significantly affecting audio quality.
    """
    
    sync_results = []
    stretches_needed = []
    
    for sync_point in sync_points:
        # Find the word in timing map
        word_timing = self._find_word_timing(
            voiceover.timing_map, 
            sync_point.word_or_phrase
        )
        
        if not word_timing:
            continue
            
        # Calculate error
        current_time = word_timing.start_time
        target_time = sync_point.timestamp
        error_ms = abs(current_time - target_time) * 1000
        
        sync_results.append(SyncPointResult(
            sync_point=sync_point,
            actual_timestamp=current_time,
            target_timestamp=target_time,
            error_ms=error_ms,
            within_tolerance=error_ms <= sync_point.tolerance * 1000
        ))
        
        # If outside tolerance, calculate needed stretch
        if not sync_results[-1].within_tolerance:
            stretches_needed.append(self._calculate_stretch(
                word_timing, target_time
            ))
    
    # Apply time stretches if needed
    if stretches_needed:
        synced_audio = await self._apply_time_stretches(
            voiceover.audio,
            stretches_needed
        )
    else:
        synced_audio = voiceover.audio
    
    # Calculate overall accuracy
    accuracy = sum(1 for r in sync_results if r.within_tolerance) / len(sync_results) * 100
    
    return SyncedAudioResult(
        original_audio=voiceover.audio,
        synced_audio=synced_audio,
        sync_points_hit=sync_results,
        overall_sync_accuracy=accuracy,
        time_stretches_applied=stretches_needed
    )
```

### 3. Music Generation/Selection

```python
async def generate_music(
    self,
    mood: MusicMood,
    duration: float,
    tempo: str = "medium",
    provider: str = "mubert"
) -> GeneratedAudio:
    """
    Generate or select background music
    
    Args:
        mood: Desired emotional tone
        duration: Length needed in seconds
        tempo: "slow", "medium", "fast"
        provider: Music provider
    """
    
    if provider == "mubert":
        audio = await self._generate_mubert(
            mood=mood.value,
            duration=duration,
            tempo=tempo
        )
    elif provider == "soundraw":
        audio = await self._generate_soundraw(
            mood=mood.value,
            duration=duration,
            tempo=tempo
        )
    else:
        # Licensed library search
        audio = await self._search_music_library(
            mood=mood.value,
            min_duration=duration,
            tempo=tempo
        )
    
    return audio
```

### 4. Sound Effects

```python
async def get_sound_effect(
    self,
    effect_type: str,
    duration: Optional[float] = None
) -> GeneratedAudio:
    """
    Find or generate a sound effect
    
    Common effect types:
    - "whoosh" - Transition swoosh
    - "click" - Button/UI click
    - "notification" - Alert sound
    - "ambient_office" - Background noise
    - "typing" - Keyboard sounds
    - "success" - Achievement/completion
    - "error" - Failure/warning
    """
    
    # Search free libraries first
    results = await self._search_freesound(effect_type)
    
    if results:
        best_match = self._select_best_match(results, duration)
        return await self._download_and_process(best_match)
    
    # Fall back to premium library
    return await self._search_premium_sfx(effect_type)
```

### 5. Audio Mixing

```python
async def mix_scene_audio(
    self,
    voiceover: Optional[GeneratedAudio],
    music: Optional[GeneratedAudio],
    sfx: List[Tuple[GeneratedAudio, float]],  # (audio, timestamp)
    scene_duration: float,
    mix_settings: MixSettings
) -> MixedAudio:
    """
    Mix all audio elements for a scene
    
    Handles:
    - Volume balancing
    - Music ducking under voiceover
    - SFX placement
    - Loudness normalization
    """
    
    tracks = []
    
    # Add voiceover (centered, full volume)
    if voiceover:
        tracks.append({
            "audio": voiceover,
            "start": 0,
            "volume_db": mix_settings.vo_volume_db,
            "pan": 0  # Center
        })
    
    # Add music (ducked under VO)
    if music:
        music_track = {
            "audio": music,
            "start": 0,
            "volume_db": mix_settings.music_volume_db,
            "pan": 0
        }
        
        if voiceover and mix_settings.ducking_enabled:
            music_track["ducking"] = {
                "trigger": voiceover,
                "amount_db": mix_settings.ducking_amount_db,
                "attack_ms": mix_settings.ducking_attack_ms,
                "release_ms": mix_settings.ducking_release_ms
            }
        
        tracks.append(music_track)
    
    # Add sound effects at their timestamps
    for sfx_audio, timestamp in sfx:
        tracks.append({
            "audio": sfx_audio,
            "start": timestamp,
            "volume_db": mix_settings.sfx_volume_db,
            "pan": 0
        })
    
    # Mix and normalize
    mixed = await self._mix_tracks(tracks, scene_duration)
    normalized = await self._normalize_loudness(
        mixed, 
        target_lufs=mix_settings.target_loudness_lufs
    )
    
    return MixedAudio(
        audio=normalized,
        tracks_mixed=len(tracks),
        mix_settings=mix_settings,
        peak_level_db=await self._measure_peak(normalized),
        loudness_lufs=await self._measure_loudness(normalized)
    )
```

## Integration

- **Called by**: `StudioOrchestrator` after video generation
- **Receives from**: `ScriptWriterAgent` (audio specs per scene)
- **Output used by**: `EditorAgent` for final EDL with audio

## Example Usage

```python
from agents.audio_generator import AudioGeneratorAgent
from core.claude_client import ClaudeClient

claude = ClaudeClient()
audio_gen = AudioGeneratorAgent(claude_client=claude)

# Generate voiceover
vo_result = await audio_gen.generate_voiceover(
    text="Every morning starts with a quick team sync.",
    voice_style=VoiceStyle.PROFESSIONAL,
    target_duration=4.0,
    provider="elevenlabs"
)

print(f"Generated VO: {vo_result.audio.duration}s")
print(f"WPM: {vo_result.words_per_minute}")

# Sync to video
sync_points = [
    SyncPoint(
        timestamp=1.0,
        word_or_phrase="morning",
        visual_cue="laptop opens",
        tolerance=0.3
    )
]

synced = await audio_gen.sync_to_video(
    voiceover=vo_result,
    sync_points=sync_points,
    video_duration=5.0
)

print(f"Sync accuracy: {synced.overall_sync_accuracy}%")

# Generate music
music = await audio_gen.generate_music(
    mood=MusicMood.CORPORATE,
    duration=60.0,
    tempo="medium"
)

# Get sound effect
notification = await audio_gen.get_sound_effect(
    effect_type="notification",
    duration=1.0
)

# Mix everything
mixed = await audio_gen.mix_scene_audio(
    voiceover=synced.synced_audio,
    music=music,
    sfx=[(notification, 0.5)],
    scene_duration=5.0,
    mix_settings=MixSettings(ducking_enabled=True)
)

print(f"Final mix: {mixed.loudness_lufs} LUFS")
```

## Cost Tracking

```python
def estimate_audio_cost(
    self,
    scene_audios: List[SceneAudio],
    audio_tier: AudioTier
) -> Dict[str, float]:
    """Estimate total audio production cost"""
    
    costs = {
        "voiceover": 0,
        "music": 0,
        "sfx": 0,
        "mixing": 0,
        "total": 0
    }
    
    for scene in scene_audios:
        if scene.voiceover:
            char_count = len(scene.voiceover.text)
            costs["voiceover"] += char_count * 0.0003  # ElevenLabs rate
        
        if scene.music:
            costs["music"] += 0.50  # Per track
        
        costs["sfx"] += len(scene.sound_effects) * 0.10
    
    # Add mixing overhead for higher tiers
    if audio_tier in [AudioTier.TIME_SYNCED, AudioTier.FULL_PRODUCTION]:
        costs["mixing"] = len(scene_audios) * 0.25
    
    costs["total"] = sum(costs.values())
    return costs
```

## Error Handling

| Error | Handling |
|-------|----------|
| TTS rate limit | Exponential backoff, queue requests |
| Voice unavailable | Fall back to similar voice |
| Sync impossible | Return best effort, flag in QA |
| Music too short | Loop with crossfade |
| Audio clipping | Apply limiter, reduce gain |

## Quality Checks

```python
async def validate_audio(self, audio: GeneratedAudio) -> List[str]:
    """Check audio quality issues"""
    
    issues = []
    
    # Check for clipping
    peak_db = await self._measure_peak(audio)
    if peak_db > -0.1:
        issues.append(f"Audio clipping detected (peak: {peak_db}dB)")
    
    # Check loudness
    loudness = await self._measure_loudness(audio)
    if loudness < -24 or loudness > -10:
        issues.append(f"Loudness outside range: {loudness} LUFS")
    
    # Check for silence
    silence_ratio = await self._detect_silence(audio)
    if silence_ratio > 0.3:
        issues.append(f"Excessive silence: {silence_ratio*100:.0f}%")
    
    # Check sync accuracy if applicable
    # ...
    
    return issues
```
