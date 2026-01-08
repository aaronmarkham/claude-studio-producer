"""Unit tests for FFmpegRenderer"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from core.renderer import FFmpegRenderer, RenderError, FFmpegNotFoundError
from core.models.render import (
    AudioTrack,
    Transition,
    TransitionType,
    TrackType,
    RenderConfig,
    RenderResult,
)
from core.models.edit_decision import (
    EditDecision,
    EditCandidate,
    EditDecisionList,
)


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def renderer(temp_output_dir):
    """Create a renderer with temp output directory"""
    return FFmpegRenderer(output_dir=temp_output_dir)


@pytest.fixture
def sample_edit_candidate():
    """Create a sample edit candidate"""
    return EditCandidate(
        candidate_id="test_candidate",
        name="Test Cut",
        style="balanced",
        decisions=[
            EditDecision(
                scene_id="scene_001",
                selected_variation=0,
                video_url="mock://video1.mp4",
                in_point=0.0,
                out_point=5.0,
                transition_in="fade_in",
                transition_in_duration=0.5,
                transition_out="cut",
                start_time=0.0,
                duration=5.0
            ),
            EditDecision(
                scene_id="scene_002",
                selected_variation=0,
                video_url="mock://video2.mp4",
                in_point=0.0,
                out_point=8.0,
                transition_in="cut",
                transition_out="fade_out",
                transition_out_duration=1.0,
                start_time=5.0,
                duration=8.0
            ),
        ],
        total_duration=13.0,
        estimated_quality=85.0,
        description="Test edit candidate"
    )


@pytest.fixture
def sample_edl(sample_edit_candidate):
    """Create a sample EDL"""
    return EditDecisionList(
        edl_id="test_edl",
        project_name="Test Project",
        candidates=[sample_edit_candidate],
        recommended_candidate_id="test_candidate",
        total_scenes=2
    )


@pytest.fixture
def sample_audio_tracks():
    """Create sample audio tracks"""
    return [
        AudioTrack(
            path="mock://voiceover.mp3",
            start_time=0.0,
            volume_db=-3.0,
            track_type=TrackType.VOICEOVER,
            fade_in=0.5
        ),
        AudioTrack(
            path="mock://music.mp3",
            start_time=0.0,
            volume_db=-12.0,
            track_type=TrackType.MUSIC,
            duck_under=[TrackType.VOICEOVER],
            fade_in=1.0,
            fade_out=2.0
        ),
    ]


class TestFFmpegRenderer:
    """Tests for FFmpegRenderer initialization"""

    def test_init_creates_output_dir(self, temp_output_dir):
        """Test that renderer creates output directory"""
        output_path = os.path.join(temp_output_dir, "renders")
        renderer = FFmpegRenderer(output_dir=output_path)
        assert os.path.exists(output_path)

    def test_init_with_custom_config(self, temp_output_dir):
        """Test initialization with custom config"""
        config = RenderConfig(
            output_width=1280,
            output_height=720,
            output_fps=24.0,
            crf=18
        )
        renderer = FFmpegRenderer(output_dir=temp_output_dir, config=config)
        assert renderer.config.output_width == 1280
        assert renderer.config.crf == 18


class TestConcatFile:
    """Tests for concat file generation"""

    def test_generate_concat_file(self, renderer):
        """Test generating FFmpeg concat file"""
        video_paths = [
            "/path/to/video1.mp4",
            "/path/to/video2.mp4",
            "/path/to/video3.mp4"
        ]

        concat_path = renderer._generate_concat_file(video_paths)

        try:
            assert os.path.exists(concat_path)

            with open(concat_path, 'r') as f:
                content = f.read()

            # Paths are converted to absolute, so just check they appear
            # (on Windows they'll have drive letter, on Unix they stay the same)
            assert "video1.mp4" in content
            assert "video2.mp4" in content
            assert "video3.mp4" in content
            # Each line should be in concat format: file 'path'
            assert content.count("file '") == 3
        finally:
            if os.path.exists(concat_path):
                os.remove(concat_path)

    def test_generate_concat_file_escapes_quotes(self, renderer):
        """Test that paths with quotes are escaped"""
        video_paths = ["/path/to/video's file.mp4"]

        concat_path = renderer._generate_concat_file(video_paths)

        try:
            with open(concat_path, 'r') as f:
                content = f.read()

            # Single quotes should be escaped
            assert "video" in content
        finally:
            if os.path.exists(concat_path):
                os.remove(concat_path)


class TestFilterComplex:
    """Tests for filter_complex generation"""

    def test_generate_filter_simple(self, renderer, sample_audio_tracks):
        """Test generating filter for audio mixing"""
        filter_str = renderer._generate_filter_complex(sample_audio_tracks[:1])

        # Should have volume adjustment for first track
        assert "volume" in filter_str or "acopy" in filter_str

    def test_generate_filter_with_delay(self, renderer):
        """Test filter generation with delayed audio"""
        tracks = [
            AudioTrack(
                path="audio.mp3",
                start_time=5.0,  # Start 5 seconds in
                volume_db=0.0,
                track_type=TrackType.MUSIC
            )
        ]

        filter_str = renderer._generate_filter_complex(tracks)

        # Should have adelay filter
        assert "adelay" in filter_str

    def test_generate_filter_with_fade(self, renderer):
        """Test filter generation with fade in/out"""
        tracks = [
            AudioTrack(
                path="audio.mp3",
                start_time=0.0,
                volume_db=0.0,
                track_type=TrackType.MUSIC,
                fade_in=2.0,
                fade_out=3.0
            )
        ]

        filter_str = renderer._generate_filter_complex(tracks)

        # Should have afade filters
        assert "afade" in filter_str

    def test_generate_filter_multiple_tracks(self, renderer, sample_audio_tracks):
        """Test filter for mixing multiple tracks"""
        filter_str = renderer._generate_filter_complex(sample_audio_tracks)

        # Should have amix for multiple tracks
        assert "amix" in filter_str
        assert "inputs=2" in filter_str


class TestTransitionBuilding:
    """Tests for building transitions from edit decisions"""

    def test_build_transitions_fade_in(self, renderer, sample_edit_candidate):
        """Test building fade in transition"""
        transitions = renderer._build_transitions(sample_edit_candidate.decisions)

        # First scene has fade_in
        fade_in = [t for t in transitions if t.type == TransitionType.FADE_IN]
        assert len(fade_in) >= 1
        assert fade_in[0].duration == 0.5

    def test_build_transitions_fade_out(self, renderer, sample_edit_candidate):
        """Test building fade out transition"""
        transitions = renderer._build_transitions(sample_edit_candidate.decisions)

        # Second scene has fade_out
        fade_out = [t for t in transitions if t.type == TransitionType.FADE_OUT]
        assert len(fade_out) >= 1

    def test_build_transitions_cut_has_no_transition(self, renderer):
        """Test that cuts don't generate transitions"""
        decisions = [
            EditDecision(
                scene_id="scene_001",
                selected_variation=0,
                video_url="video.mp4",
                transition_in="cut",
                transition_out="cut",
                duration=5.0
            )
        ]

        transitions = renderer._build_transitions(decisions)

        # Cuts should not generate transitions
        assert len(transitions) == 0


class TestMockRender:
    """Tests for mock rendering (when no real files exist)"""

    @pytest.mark.asyncio
    async def test_render_with_mock_files(self, renderer, sample_edl):
        """Test rendering with mock video paths"""
        result = await renderer.render(sample_edl)

        # Should succeed in mock mode
        assert result.success
        assert "Mock render" in result.error_message

    @pytest.mark.asyncio
    async def test_render_candidate_mock(self, renderer, sample_edit_candidate, temp_output_dir):
        """Test rendering a candidate with mock files"""
        result = await renderer.render_candidate(
            candidate=sample_edit_candidate,
            audio_tracks=[],
            output_dir=Path(temp_output_dir)
        )

        assert result.success
        assert result.render_time is not None

    @pytest.mark.asyncio
    async def test_render_selects_recommended(self, renderer, sample_edl):
        """Test that render uses recommended candidate by default"""
        result = await renderer.render(sample_edl)

        assert result.success

    @pytest.mark.asyncio
    async def test_render_specific_candidate(self, renderer, sample_edl):
        """Test rendering a specific candidate"""
        result = await renderer.render(sample_edl, candidate_id="test_candidate")

        assert result.success

    @pytest.mark.asyncio
    async def test_render_invalid_candidate(self, renderer, sample_edl):
        """Test rendering with invalid candidate ID"""
        result = await renderer.render(sample_edl, candidate_id="nonexistent")

        assert not result.success
        assert "not found" in result.error_message


class TestRenderConfig:
    """Tests for RenderConfig"""

    def test_default_config(self):
        """Test default render configuration"""
        config = RenderConfig()

        assert config.output_width == 1920
        assert config.output_height == 1080
        assert config.output_fps == 30.0
        assert config.video_codec == "libx264"
        assert config.audio_codec == "aac"
        assert config.crf == 23

    def test_custom_config(self):
        """Test custom render configuration"""
        config = RenderConfig(
            output_width=3840,
            output_height=2160,
            output_fps=60.0,
            preset="slow",
            crf=18
        )

        assert config.output_width == 3840
        assert config.output_height == 2160
        assert config.preset == "slow"


class TestAudioTrack:
    """Tests for AudioTrack model"""

    def test_audio_track_defaults(self):
        """Test AudioTrack default values"""
        track = AudioTrack(path="audio.mp3")

        assert track.start_time == 0.0
        assert track.volume_db == 0.0
        assert track.track_type == TrackType.MUSIC
        assert track.fade_in == 0.0
        assert track.fade_out == 0.0

    def test_audio_track_with_settings(self):
        """Test AudioTrack with custom settings"""
        track = AudioTrack(
            path="voiceover.mp3",
            start_time=2.5,
            volume_db=-6.0,
            track_type=TrackType.VOICEOVER,
            duck_under=[TrackType.MUSIC],
            fade_in=0.5
        )

        assert track.start_time == 2.5
        assert track.volume_db == -6.0
        assert track.track_type == TrackType.VOICEOVER
        assert TrackType.MUSIC in track.duck_under


class TestTransition:
    """Tests for Transition model"""

    def test_transition_defaults(self):
        """Test Transition default values"""
        transition = Transition()

        assert transition.type == TransitionType.CUT
        assert transition.duration == 0.0
        assert transition.position == 0.0

    def test_transition_with_settings(self):
        """Test Transition with custom settings"""
        transition = Transition(
            type=TransitionType.DISSOLVE,
            duration=1.5,
            position=10.0,
            from_scene="scene_001",
            to_scene="scene_002"
        )

        assert transition.type == TransitionType.DISSOLVE
        assert transition.duration == 1.5
        assert transition.from_scene == "scene_001"


class TestFFmpegCheck:
    """Tests for FFmpeg installation check"""

    @pytest.mark.asyncio
    async def test_check_ffmpeg_installed(self, renderer):
        """Test checking FFmpeg installation"""
        result = await renderer.check_ffmpeg_installed()

        # Result should indicate whether FFmpeg is available
        assert "installed" in result

        if result["installed"]:
            assert result["path"] is not None
            assert "ffmpeg" in result["version"].lower()
        else:
            assert "error" in result
