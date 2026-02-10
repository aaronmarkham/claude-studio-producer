"""
Shared audio generation utilities.

Used by both the training pipeline and produce-video CLI to generate
per-chunk TTS audio via any AudioProvider, get durations, and concatenate.
"""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple


@dataclass
class AudioChunkResult:
    """Result of generating a single audio chunk."""
    audio_id: str
    path: Path
    duration_sec: float
    text: str
    char_count: int
    estimated_cost: float


async def generate_audio_chunks(
    provider,  # AudioProvider — any provider implementing generate_speech()
    items: List[Tuple[str, str]],
    output_dir: Path,
    voice_id: str = "pFZP5JQG7iQjIQuC4Bku",
    on_chunk_complete: Optional[Callable[[int, int, str], None]] = None,
    on_chunk_error: Optional[Callable[[str, Exception], None]] = None,
) -> List[AudioChunkResult]:
    """
    Generate individual audio files for a list of text items.

    Args:
        provider: Any AudioProvider implementing generate_speech()
        items: List of (audio_id, text) tuples. Items with text < 5 chars are skipped.
        output_dir: Directory to write MP3 files into (created if missing)
        voice_id: Voice identifier passed to provider.generate_speech()
        on_chunk_complete: Optional callback(current_index, total, audio_id) after each chunk
        on_chunk_error: Optional callback(audio_id, exception) on failure

    Returns:
        List of AudioChunkResult for successfully generated chunks.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(items)

    for i, (audio_id, text) in enumerate(items):
        if not text or len(text.strip()) < 5:
            if on_chunk_complete:
                on_chunk_complete(i, total, audio_id)
            continue

        try:
            result = await provider.generate_speech(text=text, voice_id=voice_id)

            if result.success and result.audio_data:
                audio_path = output_dir / f"{audio_id}.mp3"
                audio_path.write_bytes(result.audio_data)

                duration = await get_audio_duration(audio_path)
                cost = provider.estimate_cost(text)

                results.append(AudioChunkResult(
                    audio_id=audio_id,
                    path=audio_path,
                    duration_sec=duration,
                    text=text,
                    char_count=len(text),
                    estimated_cost=cost,
                ))
        except Exception as e:
            if on_chunk_error:
                on_chunk_error(audio_id, e)

        if on_chunk_complete:
            on_chunk_complete(i, total, audio_id)

    return results


async def get_audio_duration(audio_path: Path) -> float:
    """
    Get duration of an audio file in seconds.

    Tries mutagen first (fast, pure-Python), falls back to ffprobe.
    Returns 0.0 if neither works.
    """
    # Try mutagen (no subprocess needed)
    try:
        from mutagen.mp3 import MP3
        audio_info = MP3(str(audio_path))
        return audio_info.info.length
    except Exception:
        pass

    # Fall back to ffprobe via FFmpegRenderer
    try:
        from core.renderer import FFmpegRenderer
        renderer = FFmpegRenderer()
        duration = await renderer._get_duration(str(audio_path))
        return duration if duration else 0.0
    except Exception:
        return 0.0


async def concatenate_audio_files(
    chunk_paths: List[Path],
    output_path: Path,
) -> float:
    """
    Concatenate MP3 files into a single file using ffmpeg concat demuxer.

    Returns duration of the concatenated file in seconds.
    Raises RuntimeError if ffmpeg fails or chunk_paths is empty.
    """
    if not chunk_paths:
        raise RuntimeError("No audio chunks to concatenate")

    # Write ffmpeg concat list with absolute paths
    # (concat demuxer resolves relative paths from the list file's directory,
    # not the working directory, so absolute paths are required)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for cp in chunk_paths:
            abs_path = str(Path(cp).resolve()).replace('\\', '/')
            f.write(f"file '{abs_path}'\n")
        list_path = f.name

    try:
        proc = await asyncio.subprocess.create_subprocess_exec(
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_path, '-c', 'copy', str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            # Skip ffmpeg banner — real error is at the end of stderr
            err_text = stderr.decode()
            raise RuntimeError(f"ffmpeg concat failed: {err_text[-500:]}")
    finally:
        Path(list_path).unlink(missing_ok=True)

    return await get_audio_duration(output_path)
