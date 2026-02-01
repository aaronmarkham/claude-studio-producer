"""Tests for audio-video mixing functionality"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from agents.script_writer import ProductionMode


class TestProductionMode:
    """Tests for ProductionMode enum"""

    def test_production_mode_values(self):
        """Test that ProductionMode has correct values"""
        assert ProductionMode.VIDEO_LED.value == "video_led"
        assert ProductionMode.AUDIO_LED.value == "audio_led"

    def test_production_mode_is_string_enum(self):
        """Test that ProductionMode is a string enum"""
        assert isinstance(ProductionMode.VIDEO_LED.value, str)
        assert isinstance(ProductionMode.AUDIO_LED.value, str)


class TestMixerFunctions:
    """Tests for mixer helper functions"""

    @pytest.mark.asyncio
    async def test_mix_single_scene_stretch_mode(self):
        """Test mixing with stretch fit mode"""
        from core.rendering.mixer import mix_single_scene

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer.check_ffmpeg_installed = AsyncMock(return_value={"installed": True})
            mock_renderer.mix_audio = AsyncMock()
            mock_renderer_class.return_value = mock_renderer

            await mix_single_scene(
                video_path="test_video.mp4",
                audio_path="test_audio.mp3",
                output_path="output.mp4",
                fit_mode="stretch"
            )

            # Verify FFmpegRenderer.mix_audio was called with speed-match
            mock_renderer.mix_audio.assert_called_once()
            call_args = mock_renderer.mix_audio.call_args
            assert call_args.kwargs['fit_mode'] == "speed-match"

    @pytest.mark.asyncio
    async def test_mix_single_scene_truncate_mode(self):
        """Test mixing with truncate fit mode"""
        from core.rendering.mixer import mix_single_scene

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer.check_ffmpeg_installed = AsyncMock(return_value={"installed": True})
            mock_renderer.mix_audio = AsyncMock()
            mock_renderer_class.return_value = mock_renderer

            await mix_single_scene(
                video_path="test_video.mp4",
                audio_path="test_audio.mp3",
                output_path="output.mp4",
                fit_mode="truncate"
            )

            # Verify FFmpegRenderer.mix_audio was called with shortest
            mock_renderer.mix_audio.assert_called_once()
            call_args = mock_renderer.mix_audio.call_args
            assert call_args.kwargs['fit_mode'] == "shortest"

    @pytest.mark.asyncio
    async def test_mix_single_scene_raises_if_ffmpeg_missing(self):
        """Test that mix_single_scene raises error if FFmpeg is not installed"""
        from core.rendering.mixer import mix_single_scene

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer.check_ffmpeg_installed = AsyncMock(return_value={"installed": False})
            mock_renderer_class.return_value = mock_renderer

            with pytest.raises(RuntimeError, match="FFmpeg not installed"):
                await mix_single_scene(
                    video_path="test_video.mp4",
                    audio_path="test_audio.mp3",
                    output_path="output.mp4",
                    fit_mode="stretch"
                )

    @pytest.mark.asyncio
    async def test_get_media_duration(self):
        """Test getting media duration"""
        from core.rendering.mixer import get_media_duration

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer._get_duration = AsyncMock(return_value=45.5)
            mock_renderer_class.return_value = mock_renderer

            duration = await get_media_duration("test.mp4")
            assert duration == 45.5

    @pytest.mark.asyncio
    async def test_get_media_duration_raises_if_none(self):
        """Test that get_media_duration raises error if duration cannot be determined"""
        from core.rendering.mixer import get_media_duration

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer._get_duration = AsyncMock(return_value=None)
            mock_renderer_class.return_value = mock_renderer

            with pytest.raises(RuntimeError, match="Could not determine duration"):
                await get_media_duration("test.mp4")

    @pytest.mark.asyncio
    async def test_concatenate_videos(self):
        """Test video concatenation"""
        from core.rendering.mixer import concatenate_videos

        with patch('core.rendering.mixer.FFmpegRenderer') as mock_renderer_class:
            mock_renderer = Mock()
            mock_renderer.check_ffmpeg_installed = AsyncMock(return_value={"installed": True})
            mock_renderer.concat_videos = AsyncMock()
            mock_renderer_class.return_value = mock_renderer

            video_paths = [Path("video1.mp4"), Path("video2.mp4"), Path("video3.mp4")]
            output_path = Path("output.mp4")

            await concatenate_videos(video_paths, output_path)

            # Verify concat_videos was called with correct paths
            mock_renderer.concat_videos.assert_called_once()
            call_args = mock_renderer.concat_videos.call_args
            assert len(call_args.kwargs['video_paths']) == 3


class TestEditorWithAudio:
    """Tests for EditorAgent with scene_audio parameter"""

    @pytest.mark.asyncio
    async def test_editor_run_accepts_scene_audio(self):
        """Test that EditorAgent.run accepts scene_audio parameter"""
        from agents.editor import EditorAgent
        from agents.script_writer import Scene
        from agents.video_generator import GeneratedVideo
        from agents.qa_verifier import QAResult

        with patch('agents.editor.ClaudeClient') as mock_client_class:
            # Create mock Claude client
            mock_client = Mock()
            mock_client.query = AsyncMock(return_value='{"candidates": []}')
            mock_client_class.return_value = mock_client

            editor = EditorAgent(claude_client=mock_client)

            scenes = [
                Scene(
                    scene_id="scene_001",
                    title="Test Scene",
                    description="Test description",
                    duration=5.0,
                    visual_elements=["element1"],
                    audio_notes="notes",
                    transition_in="cut",
                    transition_out="cut",
                    prompt_hints=["hint1"]
                )
            ]

            video_candidates = {
                "scene_001": [
                    GeneratedVideo(
                        scene_id="scene_001",
                        variation_id=0,
                        video_url="video.mp4",
                        duration=5.0,
                        generation_cost=1.0,
                        provider="luma",
                        thumbnail_url="",
                        metadata={}
                    )
                ]
            }

            qa_results = {
                "scene_001": [
                    QAResult(
                        scene_id="scene_001",
                        video_url="video.mp4",
                        overall_score=85.0,
                        visual_accuracy=80.0,
                        style_consistency=85.0,
                        technical_quality=90.0,
                        narrative_fit=85.0,
                        issues=[],
                        suggestions=[],
                        passed=True,
                        threshold=70.0
                    )
                ]
            }

            scene_audio = {"scene_001": "audio.mp3"}

            # This should not raise an error
            try:
                edl = await editor.run(
                    scenes=scenes,
                    video_candidates=video_candidates,
                    qa_results=qa_results,
                    scene_audio=scene_audio,
                    original_request="test",
                    num_candidates=1
                )
                # If we get here, the parameter was accepted
                assert True
            except TypeError as e:
                if "scene_audio" in str(e):
                    pytest.fail(f"EditorAgent.run does not accept scene_audio parameter: {e}")
                raise

    @pytest.mark.asyncio
    async def test_editor_populates_audio_url_in_decisions(self):
        """Test that EditorAgent populates audio_url in EditDecision objects"""
        from agents.editor import EditorAgent
        from agents.script_writer import Scene
        from agents.video_generator import GeneratedVideo
        from agents.qa_verifier import QAResult

        with patch('agents.editor.ClaudeClient') as mock_client_class:
            # Create mock Claude client that returns a valid candidate structure
            mock_response = '''{
                "candidates": [
                    {
                        "candidate_id": "test_candidate",
                        "name": "Test Candidate",
                        "editorial_approach": "balanced",
                        "reasoning": "test reasoning",
                        "description": "test description",
                        "estimated_quality": 85.0,
                        "total_duration": 5.0,
                        "edits": [
                            {
                                "scene_id": "scene_001",
                                "selected_variation": 0,
                                "in_point": 0.0,
                                "out_point": 5.0,
                                "duration": 5.0,
                                "transition_in": "cut",
                                "transition_in_duration": 0.0,
                                "transition_out": "cut",
                                "transition_out_duration": 0.0,
                                "notes": "test note"
                            }
                        ]
                    }
                ]
            }'''
            mock_client = Mock()
            mock_client.query = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            editor = EditorAgent(claude_client=mock_client)

            scenes = [
                Scene(
                    scene_id="scene_001",
                    title="Test Scene",
                    description="Test description",
                    duration=5.0,
                    visual_elements=["element1"],
                    audio_notes="notes",
                    transition_in="cut",
                    transition_out="cut",
                    prompt_hints=["hint1"]
                )
            ]

            video_candidates = {
                "scene_001": [
                    GeneratedVideo(
                        scene_id="scene_001",
                        variation_id=0,
                        video_url="video.mp4",
                        duration=5.0,
                        generation_cost=1.0,
                        provider="luma",
                        thumbnail_url="",
                        metadata={}
                    )
                ]
            }

            qa_results = {
                "scene_001": [
                    QAResult(
                        scene_id="scene_001",
                        video_url="video.mp4",
                        overall_score=85.0,
                        visual_accuracy=80.0,
                        style_consistency=85.0,
                        technical_quality=90.0,
                        narrative_fit=85.0,
                        issues=[],
                        suggestions=[],
                        passed=True,
                        threshold=70.0
                    )
                ]
            }

            scene_audio = {"scene_001": "audio.mp3"}

            edl = await editor.run(
                scenes=scenes,
                video_candidates=video_candidates,
                qa_results=qa_results,
                scene_audio=scene_audio,
                original_request="test",
                num_candidates=1
            )

            # Verify that the audio_url was populated in the decision
            assert edl is not None
            assert len(edl.candidates) > 0
            candidate = edl.candidates[0]
            assert len(candidate.decisions) > 0
            decision = candidate.decisions[0]
            assert decision.audio_url == "audio.mp3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
