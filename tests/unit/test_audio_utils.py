"""Unit tests for core.audio_utils shared audio generation utilities."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.audio_utils import (
    AudioChunkResult,
    generate_audio_chunks,
    get_audio_duration,
    concatenate_audio_files,
)
from core.providers.base import AudioGenerationResult


@pytest.fixture
def mock_provider():
    """Mock AudioProvider that returns fake audio bytes."""
    provider = AsyncMock()
    provider.generate_speech = AsyncMock(return_value=AudioGenerationResult(
        success=True,
        audio_data=b"fake mp3 data",
        duration=None,
        format="mp3",
        sample_rate=44100,
    ))
    provider.estimate_cost = MagicMock(return_value=0.001)
    return provider


@pytest.fixture
def failing_provider():
    """Mock AudioProvider that raises on generate_speech."""
    provider = AsyncMock()
    provider.generate_speech = AsyncMock(side_effect=RuntimeError("API down"))
    provider.estimate_cost = MagicMock(return_value=0.0)
    return provider


class TestGenerateAudioChunks:
    """Tests for generate_audio_chunks."""

    @pytest.mark.asyncio
    async def test_generates_files(self, mock_provider, tmp_path):
        """Should create MP3 files for each item."""
        items = [("chunk_000", "Hello world this is a test"), ("chunk_001", "Another paragraph here")]

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=3.0):
            results = await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=tmp_path,
                voice_id="test_voice",
            )

        assert len(results) == 2
        assert results[0].audio_id == "chunk_000"
        assert results[1].audio_id == "chunk_001"
        assert (tmp_path / "chunk_000.mp3").exists()
        assert (tmp_path / "chunk_001.mp3").exists()
        assert mock_provider.generate_speech.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_short_text(self, mock_provider, tmp_path):
        """Items with text < 5 chars should be skipped."""
        items = [("chunk_000", "Hi"), ("chunk_001", "This is long enough")]

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=2.0):
            results = await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=tmp_path,
                voice_id="test_voice",
            )

        assert len(results) == 1
        assert results[0].audio_id == "chunk_001"
        assert mock_provider.generate_speech.call_count == 1

    @pytest.mark.asyncio
    async def test_skips_empty_text(self, mock_provider, tmp_path):
        """Items with empty or None text should be skipped."""
        items = [("chunk_000", ""), ("chunk_001", None), ("chunk_002", "Valid paragraph text")]

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=2.0):
            results = await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=tmp_path,
                voice_id="test_voice",
            )

        assert len(results) == 1
        assert results[0].audio_id == "chunk_002"

    @pytest.mark.asyncio
    async def test_calls_on_chunk_complete(self, mock_provider, tmp_path):
        """Callback should be invoked for each item (including skipped)."""
        items = [("a", "Short"), ("b", "This is long enough text")]
        callback_calls = []

        def on_complete(idx, total, audio_id):
            callback_calls.append((idx, total, audio_id))

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=1.0):
            await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=tmp_path,
                voice_id="test_voice",
                on_chunk_complete=on_complete,
            )

        assert len(callback_calls) == 2
        assert callback_calls[0] == (0, 2, "a")
        assert callback_calls[1] == (1, 2, "b")

    @pytest.mark.asyncio
    async def test_calls_on_chunk_error(self, failing_provider, tmp_path):
        """Error callback should be invoked when generation fails."""
        items = [("chunk_000", "This should fail badly")]
        error_calls = []

        def on_error(audio_id, exc):
            error_calls.append((audio_id, str(exc)))

        results = await generate_audio_chunks(
            provider=failing_provider,
            items=items,
            output_dir=tmp_path,
            voice_id="test_voice",
            on_chunk_error=on_error,
        )

        assert len(results) == 0
        assert len(error_calls) == 1
        assert error_calls[0][0] == "chunk_000"
        assert "API down" in error_calls[0][1]

    @pytest.mark.asyncio
    async def test_result_fields(self, mock_provider, tmp_path):
        """AudioChunkResult should have correct fields."""
        items = [("chunk_000", "Hello world this is a test sentence")]

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=2.5):
            results = await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=tmp_path,
                voice_id="test_voice",
            )

        r = results[0]
        assert r.audio_id == "chunk_000"
        assert r.path == tmp_path / "chunk_000.mp3"
        assert r.duration_sec == 2.5
        assert r.text == "Hello world this is a test sentence"
        assert r.char_count == len("Hello world this is a test sentence")
        assert r.estimated_cost == 0.001

    @pytest.mark.asyncio
    async def test_creates_output_dir(self, mock_provider, tmp_path):
        """Should create output_dir if it doesn't exist."""
        nested = tmp_path / "deep" / "nested" / "dir"
        items = [("chunk_000", "Some text that is long enough")]

        with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=1.0):
            results = await generate_audio_chunks(
                provider=mock_provider,
                items=items,
                output_dir=nested,
                voice_id="test_voice",
            )

        assert nested.exists()
        assert len(results) == 1


class TestGetAudioDuration:
    """Tests for get_audio_duration."""

    @pytest.mark.asyncio
    async def test_mutagen_path(self, tmp_path):
        """Should use mutagen when available."""
        fake_mp3 = tmp_path / "test.mp3"
        fake_mp3.write_bytes(b"fake")

        mock_mp3_cls = MagicMock()
        mock_info = MagicMock()
        mock_info.info.length = 5.5
        mock_mp3_cls.return_value = mock_info

        with patch.dict("sys.modules", {"mutagen": MagicMock(), "mutagen.mp3": MagicMock(MP3=mock_mp3_cls)}):
            duration = await get_audio_duration(fake_mp3)

        assert duration == 5.5

    @pytest.mark.asyncio
    async def test_fallback_to_ffprobe(self, tmp_path):
        """Should fall back to ffprobe when mutagen fails."""
        fake_mp3 = tmp_path / "test.mp3"
        fake_mp3.write_bytes(b"fake")

        mock_renderer = AsyncMock()
        mock_renderer._get_duration = AsyncMock(return_value=7.2)

        with patch.dict("sys.modules", {"mutagen": None, "mutagen.mp3": None}):
            with patch("core.renderer.FFmpegRenderer", return_value=mock_renderer):
                duration = await get_audio_duration(fake_mp3)

        assert duration == 7.2

    @pytest.mark.asyncio
    async def test_fallback_to_zero(self, tmp_path):
        """Should return 0.0 when both mutagen and ffprobe fail."""
        fake_mp3 = tmp_path / "test.mp3"
        fake_mp3.write_bytes(b"fake")

        with patch.dict("sys.modules", {"mutagen": None, "mutagen.mp3": None}):
            with patch("core.renderer.FFmpegRenderer", side_effect=Exception("also nope")):
                duration = await get_audio_duration(fake_mp3)

        assert duration == 0.0


class TestConcatenateAudioFiles:
    """Tests for concatenate_audio_files."""

    @pytest.mark.asyncio
    async def test_empty_list_raises(self):
        """Should raise RuntimeError with empty chunk list."""
        with pytest.raises(RuntimeError, match="No audio chunks"):
            await concatenate_audio_files([], Path("output.mp3"))

    @pytest.mark.asyncio
    async def test_calls_ffmpeg(self, tmp_path):
        """Should invoke ffmpeg with correct concat arguments."""
        chunk1 = tmp_path / "a.mp3"
        chunk2 = tmp_path / "b.mp3"
        chunk1.write_bytes(b"fake1")
        chunk2.write_bytes(b"fake2")
        output = tmp_path / "out.mp3"

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.subprocess.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            with patch("core.audio_utils.get_audio_duration", new_callable=AsyncMock, return_value=10.0):
                duration = await concatenate_audio_files([chunk1, chunk2], output)

        assert duration == 10.0
        # Verify ffmpeg was called with concat demuxer
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "ffmpeg"
        assert "-f" in call_args
        assert "concat" in call_args

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_raises(self, tmp_path):
        """Should raise RuntimeError when ffmpeg fails."""
        chunk = tmp_path / "a.mp3"
        chunk.write_bytes(b"fake")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error output"))
        mock_proc.returncode = 1

        with patch("asyncio.subprocess.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="ffmpeg concat failed"):
                await concatenate_audio_files([chunk], tmp_path / "out.mp3")
