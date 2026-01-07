"""Unit tests for AudioGeneratorAgent"""

import pytest
from unittest.mock import AsyncMock
from agents.audio_generator import AudioGeneratorAgent
from agents.script_writer import Scene
from core.models.audio import (
    AudioTier,
    VoiceStyle,
    MusicMood,
    SyncPoint,
)


@pytest.fixture
def mock_claude_client():
    """Create a mock Claude client"""
    client = AsyncMock()
    client.query = AsyncMock()
    return client


@pytest.fixture
def sample_scene():
    """Create a sample scene with audio specifications"""
    return Scene(
        scene_id="scene_001",
        title="Introduction",
        description="Product introduction scene",
        duration=10.0,
        visual_elements=["product showcase", "logo"],
        audio_notes="Professional voiceover",
        transition_in="fade",
        transition_out="cut",
        prompt_hints=["modern", "professional"],
        voiceover_text="Welcome to our amazing product. It changes everything.",
        sync_points=[
            SyncPoint(
                timestamp=3.0,
                word_or_phrase="product",
                visual_cue="product appears",
                tolerance=0.3
            )
        ],
        music_transition="continue",
        sfx_cues=["whoosh at 2s"],
        vo_start_offset=0.5,
        vo_end_buffer=0.5
    )


@pytest.fixture
def sample_scene_no_vo():
    """Create a sample scene without voiceover"""
    return Scene(
        scene_id="scene_002",
        title="Background Scene",
        description="Background visuals only",
        duration=8.0,
        visual_elements=["background"],
        audio_notes="Music only",
        transition_in="fade",
        transition_out="fade",
        prompt_hints=["ambient"],
        voiceover_text=None,
        music_transition="continue"
    )


class TestAudioGeneratorAgent:
    """Test AudioGeneratorAgent"""

    def test_initialization(self, mock_claude_client):
        """Test agent initialization"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)
        assert agent.claude == mock_claude_client
        assert agent.audio_provider is None  # Mock mode
        assert agent.music_provider is None  # Mock mode

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = AudioGeneratorAgent()
        assert agent.claude is not None

    def test_is_stub_attribute(self):
        """Test that agent has _is_stub attribute"""
        assert hasattr(AudioGeneratorAgent, '_is_stub')
        assert AudioGeneratorAgent._is_stub is True

    @pytest.mark.asyncio
    async def test_generate_voiceover(self, mock_claude_client):
        """Test voiceover generation"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        text = "This is a test voiceover script for audio generation."
        result = await agent.generate_voiceover(
            text=text,
            voice_style=VoiceStyle.PROFESSIONAL,
            target_duration=5.0
        )

        # Check result structure
        assert result.audio is not None
        assert result.audio.audio_type == "voiceover"
        assert result.audio.channels == 1  # Mono for voiceover
        assert result.words_per_minute > 0
        assert result.actual_duration > 0
        assert result.target_duration == 5.0
        assert len(result.timing_map) > 0

        # Check that word timings are generated
        assert len(result.timing_map) == len(text.split())
        assert result.timing_map[0].word == "This"
        assert result.timing_map[0].start_time >= 0

    @pytest.mark.asyncio
    async def test_generate_voiceover_with_sync_points(self, mock_claude_client):
        """Test voiceover generation with sync points"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        sync_points = [
            SyncPoint(2.0, "test", "visual cue", 0.3)
        ]

        result = await agent.generate_voiceover(
            text="This is a test",
            voice_style=VoiceStyle.ENERGETIC,
            sync_points=sync_points
        )

        assert result.audio is not None
        assert len(result.timing_map) == 4  # 4 words

    @pytest.mark.asyncio
    async def test_generate_music(self, mock_claude_client):
        """Test music generation"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_music(
            mood=MusicMood.UPBEAT,
            duration=30.0,
            tempo="fast"
        )

        # Check result structure
        assert result.audio_type == "music"
        assert result.duration == 30.0
        assert result.channels == 2  # Stereo for music
        assert result.generation_cost > 0

    @pytest.mark.asyncio
    async def test_get_sound_effect(self, mock_claude_client):
        """Test sound effect retrieval"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.get_sound_effect(
            effect_type="notification",
            duration=1.5
        )

        # Check result structure
        assert result.audio_type == "sfx"
        assert result.duration == 1.5
        assert result.channels == 2  # Stereo for SFX
        assert "notification" in result.audio_id

    @pytest.mark.asyncio
    async def test_get_sound_effect_default_duration(self, mock_claude_client):
        """Test sound effect with default duration"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.get_sound_effect(effect_type="whoosh")

        assert result.audio_type == "sfx"
        assert result.duration == 1.0  # Default duration

    @pytest.mark.asyncio
    async def test_generate_scene_audio_none_tier(self, mock_claude_client, sample_scene):
        """Test scene audio generation with NONE tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene,
            audio_tier=AudioTier.NONE
        )

        # NONE tier should have no audio
        assert result.scene_id == sample_scene.scene_id
        assert result.audio_tier == AudioTier.NONE
        assert result.voiceover is None
        assert result.music is None
        assert len(result.sound_effects) == 0

    @pytest.mark.asyncio
    async def test_generate_scene_audio_music_only(self, mock_claude_client, sample_scene):
        """Test scene audio generation with MUSIC_ONLY tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene,
            audio_tier=AudioTier.MUSIC_ONLY
        )

        # MUSIC_ONLY tier should have music but no voiceover
        assert result.scene_id == sample_scene.scene_id
        assert result.audio_tier == AudioTier.MUSIC_ONLY
        assert result.voiceover is None
        assert result.music is not None
        assert result.music.duration == sample_scene.duration

    @pytest.mark.asyncio
    async def test_generate_scene_audio_simple_overlay(self, mock_claude_client, sample_scene):
        """Test scene audio generation with SIMPLE_OVERLAY tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene,
            audio_tier=AudioTier.SIMPLE_OVERLAY
        )

        # SIMPLE_OVERLAY tier should have voiceover and music
        assert result.audio_tier == AudioTier.SIMPLE_OVERLAY
        assert result.voiceover is not None
        assert result.voiceover.text == sample_scene.voiceover_text
        assert result.music is not None
        assert len(result.sound_effects) == 0  # No SFX for simple overlay

    @pytest.mark.asyncio
    async def test_generate_scene_audio_time_synced(self, mock_claude_client, sample_scene):
        """Test scene audio generation with TIME_SYNCED tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene,
            audio_tier=AudioTier.TIME_SYNCED
        )

        # TIME_SYNCED tier should include sync points
        assert result.audio_tier == AudioTier.TIME_SYNCED
        assert result.voiceover is not None
        assert len(result.voiceover.sync_points) > 0
        assert result.music is not None
        assert result.music.duck_under_vo is True

    @pytest.mark.asyncio
    async def test_generate_scene_audio_full_production(self, mock_claude_client, sample_scene):
        """Test scene audio generation with FULL_PRODUCTION tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene,
            audio_tier=AudioTier.FULL_PRODUCTION
        )

        # FULL_PRODUCTION tier should have everything
        assert result.audio_tier == AudioTier.FULL_PRODUCTION
        assert result.voiceover is not None
        assert result.music is not None
        assert len(result.sound_effects) > 0  # Should have SFX from scene.sfx_cues

    @pytest.mark.asyncio
    async def test_generate_scene_audio_no_voiceover_text(self, mock_claude_client, sample_scene_no_vo):
        """Test scene audio generation with no voiceover text"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        result = await agent.generate_scene_audio(
            scene=sample_scene_no_vo,
            audio_tier=AudioTier.SIMPLE_OVERLAY
        )

        # Should have music but no voiceover
        assert result.voiceover is None
        assert result.music is not None

    @pytest.mark.asyncio
    async def test_run(self, mock_claude_client, sample_scene):
        """Test full audio generation run"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        scenes = [sample_scene]
        result = await agent.run(
            scenes=scenes,
            audio_tier=AudioTier.TIME_SYNCED,
            budget_limit=50.0
        )

        # Check that audio was generated
        assert len(result) == 1
        assert result[0].scene_id == sample_scene.scene_id
        assert result[0].audio_tier == AudioTier.TIME_SYNCED

    @pytest.mark.asyncio
    async def test_run_multiple_scenes(self, mock_claude_client, sample_scene, sample_scene_no_vo):
        """Test audio generation for multiple scenes"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        scenes = [sample_scene, sample_scene_no_vo]
        result = await agent.run(
            scenes=scenes,
            audio_tier=AudioTier.SIMPLE_OVERLAY,
            budget_limit=100.0
        )

        # Check that audio was generated for both scenes
        assert len(result) == 2
        assert result[0].scene_id == sample_scene.scene_id
        assert result[1].scene_id == sample_scene_no_vo.scene_id

    @pytest.mark.asyncio
    async def test_run_budget_limit(self, mock_claude_client, sample_scene):
        """Test that budget limit is respected"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        # Create many scenes
        scenes = [sample_scene] * 20
        result = await agent.run(
            scenes=scenes,
            audio_tier=AudioTier.FULL_PRODUCTION,
            budget_limit=5.0  # Very low budget
        )

        # Should stop early due to budget
        assert len(result) < len(scenes)

    def test_estimate_audio_cost(self, mock_claude_client, sample_scene):
        """Test audio cost estimation"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        scenes = [sample_scene]
        estimate = agent.estimate_audio_cost(
            scenes=scenes,
            audio_tier=AudioTier.TIME_SYNCED
        )

        # Check estimate structure
        assert "total_duration_seconds" in estimate
        assert "audio_tier" in estimate
        assert "base_cost" in estimate
        assert "cost_per_minute" in estimate
        assert "num_scenes" in estimate

        assert estimate["total_duration_seconds"] == sample_scene.duration
        assert estimate["audio_tier"] == "time_synced"
        assert estimate["base_cost"] > 0
        assert estimate["num_scenes"] == 1

    def test_estimate_audio_cost_none_tier(self, mock_claude_client, sample_scene):
        """Test cost estimation for NONE tier"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        estimate = agent.estimate_audio_cost(
            scenes=[sample_scene],
            audio_tier=AudioTier.NONE
        )

        # NONE tier should have zero cost
        assert estimate["base_cost"] == 0.0

    def test_estimate_audio_cost_multiple_scenes(self, mock_claude_client, sample_scene, sample_scene_no_vo):
        """Test cost estimation for multiple scenes"""
        agent = AudioGeneratorAgent(claude_client=mock_claude_client)

        scenes = [sample_scene, sample_scene_no_vo]
        estimate = agent.estimate_audio_cost(
            scenes=scenes,
            audio_tier=AudioTier.FULL_PRODUCTION
        )

        total_duration = sample_scene.duration + sample_scene_no_vo.duration
        assert estimate["total_duration_seconds"] == total_duration
        assert estimate["num_scenes"] == 2
        assert estimate["base_cost"] > 0


class TestAudioGeneratorIntegration:
    """Integration-style tests"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import AudioGeneratorAgent
        assert AudioGeneratorAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "audio_generator" in AGENT_REGISTRY
        assert AGENT_REGISTRY["audio_generator"]["class"] == "AudioGeneratorAgent"
        assert AGENT_REGISTRY["audio_generator"]["module"] == "agents.audio_generator"
