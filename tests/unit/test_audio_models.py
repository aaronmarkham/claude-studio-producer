"""Unit tests for audio data models"""

import pytest
from core.models.audio import (
    AudioTier,
    VoiceStyle,
    MusicMood,
    SyncPoint,
    VoiceoverSpec,
    MusicSpec,
    SoundEffectSpec,
    SceneAudio,
    ProjectAudio,
    WordTiming,
    GeneratedAudio,
    VoiceoverResult,
    SyncPointResult,
    TimeStretch,
    SyncedAudioResult,
    MixSettings,
    MixedAudio,
    AudioQAResult,
)


class TestAudioTier:
    """Test AudioTier enum"""

    def test_audio_tier_values(self):
        """Test that AudioTier has expected values"""
        assert AudioTier.NONE.value == "none"
        assert AudioTier.MUSIC_ONLY.value == "music_only"
        assert AudioTier.SIMPLE_OVERLAY.value == "simple_overlay"
        assert AudioTier.TIME_SYNCED.value == "time_synced"
        assert AudioTier.FULL_PRODUCTION.value == "full_production"

    def test_audio_tier_count(self):
        """Test that we have the expected number of tiers"""
        assert len(AudioTier) == 5


class TestVoiceStyle:
    """Test VoiceStyle enum"""

    def test_voice_style_values(self):
        """Test that VoiceStyle has expected values"""
        assert VoiceStyle.PROFESSIONAL.value == "professional"
        assert VoiceStyle.CONVERSATIONAL.value == "conversational"
        assert VoiceStyle.ENERGETIC.value == "energetic"
        assert VoiceStyle.CALM.value == "calm"
        assert VoiceStyle.DRAMATIC.value == "dramatic"


class TestMusicMood:
    """Test MusicMood enum"""

    def test_music_mood_values(self):
        """Test that MusicMood has expected values"""
        assert MusicMood.UPBEAT.value == "upbeat"
        assert MusicMood.CORPORATE.value == "corporate"
        assert MusicMood.EMOTIONAL.value == "emotional"
        assert MusicMood.TENSE.value == "tense"
        assert MusicMood.AMBIENT.value == "ambient"
        assert MusicMood.NONE.value == "none"


class TestSyncPoint:
    """Test SyncPoint dataclass"""

    def test_sync_point_creation(self):
        """Test creating a SyncPoint"""
        sp = SyncPoint(
            timestamp=2.5,
            word_or_phrase="deploy",
            visual_cue="button click",
            tolerance=0.3
        )
        assert sp.timestamp == 2.5
        assert sp.word_or_phrase == "deploy"
        assert sp.visual_cue == "button click"
        assert sp.tolerance == 0.3

    def test_sync_point_default_tolerance(self):
        """Test SyncPoint default tolerance value"""
        sp = SyncPoint(
            timestamp=1.0,
            word_or_phrase="start",
            visual_cue="animation begins"
        )
        assert sp.tolerance == 0.5  # Default value


class TestVoiceoverSpec:
    """Test VoiceoverSpec dataclass"""

    def test_voiceover_spec_creation(self):
        """Test creating a VoiceoverSpec"""
        vo_spec = VoiceoverSpec(
            text="Welcome to our product",
            voice_style=VoiceStyle.PROFESSIONAL,
            target_duration=3.0
        )
        assert vo_spec.text == "Welcome to our product"
        assert vo_spec.voice_style == VoiceStyle.PROFESSIONAL
        assert vo_spec.target_duration == 3.0
        assert vo_spec.pace == "normal"  # Default
        assert vo_spec.sync_points == []  # Default empty list
        assert vo_spec.emphasis_words == []  # Default empty list

    def test_voiceover_spec_with_sync_points(self):
        """Test VoiceoverSpec with sync points"""
        sync_point = SyncPoint(1.0, "product", "product appears", 0.3)
        vo_spec = VoiceoverSpec(
            text="Our amazing product",
            voice_style=VoiceStyle.ENERGETIC,
            sync_points=[sync_point],
            pace="fast"
        )
        assert len(vo_spec.sync_points) == 1
        assert vo_spec.sync_points[0].word_or_phrase == "product"
        assert vo_spec.pace == "fast"


class TestMusicSpec:
    """Test MusicSpec dataclass"""

    def test_music_spec_creation(self):
        """Test creating a MusicSpec"""
        music = MusicSpec(
            mood=MusicMood.CORPORATE,
            tempo="medium",
            duration=30.0
        )
        assert music.mood == MusicMood.CORPORATE
        assert music.tempo == "medium"
        assert music.duration == 30.0
        assert music.duck_under_vo is True  # Default
        assert music.duck_amount_db == -12  # Default

    def test_music_spec_no_ducking(self):
        """Test MusicSpec without ducking"""
        music = MusicSpec(
            mood=MusicMood.AMBIENT,
            tempo="slow",
            duration=60.0,
            duck_under_vo=False
        )
        assert music.duck_under_vo is False


class TestSoundEffectSpec:
    """Test SoundEffectSpec dataclass"""

    def test_sfx_spec_creation(self):
        """Test creating a SoundEffectSpec"""
        sfx = SoundEffectSpec(
            effect_type="notification",
            timestamp=1.5
        )
        assert sfx.effect_type == "notification"
        assert sfx.timestamp == 1.5
        assert sfx.duration == 1.0  # Default
        assert sfx.volume_db == -6  # Default


class TestSceneAudio:
    """Test SceneAudio dataclass"""

    def test_scene_audio_creation(self):
        """Test creating a SceneAudio"""
        scene_audio = SceneAudio(
            scene_id="scene_1",
            audio_tier=AudioTier.TIME_SYNCED
        )
        assert scene_audio.scene_id == "scene_1"
        assert scene_audio.audio_tier == AudioTier.TIME_SYNCED
        assert scene_audio.voiceover is None  # Default
        assert scene_audio.music is None  # Default
        assert scene_audio.sound_effects == []  # Default

    def test_scene_audio_full(self):
        """Test SceneAudio with all elements"""
        vo_spec = VoiceoverSpec("Hello", VoiceStyle.PROFESSIONAL)
        music_spec = MusicSpec(MusicMood.UPBEAT, "medium", 5.0)
        sfx = SoundEffectSpec("whoosh", 2.0)

        scene_audio = SceneAudio(
            scene_id="scene_2",
            audio_tier=AudioTier.FULL_PRODUCTION,
            voiceover=vo_spec,
            music=music_spec,
            sound_effects=[sfx]
        )
        assert scene_audio.voiceover is not None
        assert scene_audio.music is not None
        assert len(scene_audio.sound_effects) == 1


class TestProjectAudio:
    """Test ProjectAudio dataclass"""

    def test_project_audio_creation(self):
        """Test creating a ProjectAudio"""
        project_audio = ProjectAudio(
            audio_tier=AudioTier.SIMPLE_OVERLAY
        )
        assert project_audio.audio_tier == AudioTier.SIMPLE_OVERLAY
        assert project_audio.scenes == []  # Default
        assert project_audio.sample_rate == 48000  # Default
        assert project_audio.bit_depth == 24  # Default
        assert project_audio.channels == 2  # Default


class TestGeneratedAudio:
    """Test GeneratedAudio dataclass"""

    def test_generated_audio_creation(self):
        """Test creating a GeneratedAudio"""
        audio = GeneratedAudio(
            audio_id="audio_123",
            audio_url="https://example.com/audio.mp3",
            audio_type="voiceover",
            duration=5.5,
            format="mp3",
            sample_rate=48000
        )
        assert audio.audio_id == "audio_123"
        assert audio.audio_url == "https://example.com/audio.mp3"
        assert audio.audio_type == "voiceover"
        assert audio.duration == 5.5
        assert audio.format == "mp3"
        assert audio.channels == 2  # Default
        assert audio.generation_cost == 0.0  # Default


class TestVoiceoverResult:
    """Test VoiceoverResult dataclass"""

    def test_voiceover_result_creation(self):
        """Test creating a VoiceoverResult"""
        audio = GeneratedAudio(
            audio_id="vo_1",
            audio_url="https://example.com/vo.mp3",
            audio_type="voiceover",
            duration=4.0,
            format="mp3",
            sample_rate=48000
        )
        result = VoiceoverResult(
            audio=audio,
            words_per_minute=150.0,
            actual_duration=4.0,
            target_duration=4.0
        )
        assert result.audio.audio_id == "vo_1"
        assert result.words_per_minute == 150.0
        assert result.timing_map == []  # Default


class TestSyncPointResult:
    """Test SyncPointResult dataclass"""

    def test_sync_point_result_within_tolerance(self):
        """Test SyncPointResult within tolerance"""
        sync_point = SyncPoint(2.0, "click", "button animation", 0.3)
        result = SyncPointResult(
            sync_point=sync_point,
            actual_timestamp=2.1,
            target_timestamp=2.0,
            error_ms=100.0,
            within_tolerance=True
        )
        assert result.within_tolerance is True
        assert result.error_ms == 100.0

    def test_sync_point_result_outside_tolerance(self):
        """Test SyncPointResult outside tolerance"""
        sync_point = SyncPoint(2.0, "click", "button animation", 0.2)
        result = SyncPointResult(
            sync_point=sync_point,
            actual_timestamp=2.5,
            target_timestamp=2.0,
            error_ms=500.0,
            within_tolerance=False
        )
        assert result.within_tolerance is False


class TestMixSettings:
    """Test MixSettings dataclass"""

    def test_mix_settings_defaults(self):
        """Test MixSettings default values"""
        settings = MixSettings()
        assert settings.vo_volume_db == 0
        assert settings.music_volume_db == -18
        assert settings.sfx_volume_db == -6
        assert settings.ducking_enabled is True
        assert settings.ducking_amount_db == -12
        assert settings.master_limiter is True
        assert settings.target_loudness_lufs == -14

    def test_mix_settings_custom(self):
        """Test MixSettings with custom values"""
        settings = MixSettings(
            vo_volume_db=2.0,
            music_volume_db=-20.0,
            ducking_enabled=False
        )
        assert settings.vo_volume_db == 2.0
        assert settings.music_volume_db == -20.0
        assert settings.ducking_enabled is False


class TestAudioQAResult:
    """Test AudioQAResult dataclass"""

    def test_audio_qa_result_creation(self):
        """Test creating an AudioQAResult"""
        qa = AudioQAResult(
            overall_score=85.0,
            vo_clarity=90.0,
            sync_accuracy=80.0,
            music_balance=85.0
        )
        assert qa.overall_score == 85.0
        assert qa.vo_clarity == 90.0
        assert qa.sync_accuracy == 80.0
        assert qa.issues == []  # Default
        assert qa.suggestions == []  # Default

    def test_audio_qa_result_with_issues(self):
        """Test AudioQAResult with issues"""
        qa = AudioQAResult(
            overall_score=65.0,
            issues=["Voiceover too quiet", "Music drowns out VO"],
            suggestions=["Increase VO volume by 3dB", "Enable ducking"]
        )
        assert len(qa.issues) == 2
        assert len(qa.suggestions) == 2
