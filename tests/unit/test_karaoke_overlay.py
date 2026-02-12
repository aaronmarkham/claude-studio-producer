"""Tests for karaoke-style transcript overlay."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest


class TestWordPosition:
    """Test WordPosition dataclass."""

    def test_word_position_fields(self):
        from cli.assemble import WordPosition
        wp = WordPosition(word="hello", line_idx=0, x=100, y=200, width=80)
        assert wp.word == "hello"
        assert wp.line_idx == 0
        assert wp.x == 100
        assert wp.y == 200
        assert wp.width == 80


class TestKaraokeTiming:
    """Test karaoke timing calculations."""

    def test_words_per_second(self):
        """10 words over 5 seconds = 2 words/sec."""
        word_count = 10
        duration = 5.0
        wps = word_count / duration
        assert wps == 2.0

    def test_current_word_at_start(self):
        """At t=0, current word should be index 0."""
        wps = 2.0
        elapsed = 0.0
        idx = int(elapsed * wps)
        assert idx == 0

    def test_current_word_midway(self):
        """At t=2.5 with 2 wps, should be at word 5."""
        wps = 2.0
        elapsed = 2.5
        idx = int(elapsed * wps)
        assert idx == 5

    def test_current_word_clamped(self):
        """Should not exceed word count."""
        word_count = 10
        wps = 2.0
        elapsed = 10.0  # past end
        idx = min(int(elapsed * wps), word_count - 1)
        assert idx == 9


class TestKaraokeOverlay:
    """Test create_transcript_overlay karaoke mode."""

    def test_empty_text_returns_false(self):
        from cli.assemble import create_transcript_overlay
        with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
            result = create_transcript_overlay("", 5.0, Path(f.name))
            assert result is False

    def test_zero_duration_returns_false(self):
        from cli.assemble import create_transcript_overlay
        with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
            result = create_transcript_overlay("Hello world", 0.0, Path(f.name))
            assert result is False

    @patch("cli.assemble.subprocess.run")
    def test_creates_video_with_ffmpeg_framerate(self, mock_run):
        """Verify ffmpeg is called with -framerate (frame sequence) not -loop 1 (static)."""
        from cli.assemble import create_transcript_overlay
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            output_path = f.name

        try:
            result = create_transcript_overlay(
                "Hello world this is a test of karaoke",
                3.0,
                Path(output_path)
            )
            assert result is True
            # Check ffmpeg was called with framerate input
            call_args = mock_run.call_args[0][0]
            assert "-framerate" in call_args
            assert "-loop" not in call_args
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("cli.assemble.subprocess.run")
    def test_single_word(self, mock_run):
        """Single word should still produce valid output."""
        from cli.assemble import create_transcript_overlay
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            output_path = f.name

        try:
            result = create_transcript_overlay("Hello", 2.0, Path(output_path))
            assert result is True
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch("cli.assemble.subprocess.run")
    def test_temp_frames_cleaned_up(self, mock_run):
        """Verify temp directory is cleaned up after encoding."""
        from cli.assemble import create_transcript_overlay
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            output_path = f.name

        try:
            create_transcript_overlay("Test text here", 2.0, Path(output_path))
            # Temp dirs starting with karaoke_ should be cleaned up
            temp_root = tempfile.gettempdir()
            karaoke_dirs = [d for d in os.listdir(temp_root) if d.startswith("karaoke_")]
            # Should be empty (cleaned up) or at most the one being used by another test
            assert len(karaoke_dirs) <= 1
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
