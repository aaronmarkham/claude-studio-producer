"""Audio transcription using Whisper"""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional

from openai import OpenAI

from core.secrets import get_api_key
from .models import TranscriptionResult, WordTimestamp, TranscriptSegment

# OpenAI Whisper API has a 25MB file size limit
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25MB


async def split_audio_into_chunks(audio_path: str, chunk_duration_seconds: int = 1200) -> list[str]:
    """
    Split audio into chunks of specified duration (default 20 minutes).

    Returns list of chunk file paths.
    """
    duration = await get_audio_duration(audio_path)
    if duration == 0:
        raise ValueError(f"Could not determine duration of {audio_path}")

    path = Path(audio_path)
    chunks = []
    num_chunks = int((duration + chunk_duration_seconds - 1) // chunk_duration_seconds)

    for i in range(num_chunks):
        start_time = i * chunk_duration_seconds
        chunk_path = path.parent / f"{path.stem}_chunk{i:03d}.mp3"

        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-ss", str(start_time),
            "-t", str(chunk_duration_seconds),
            "-c", "copy",  # Copy codec for speed
            "-y",
            str(chunk_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg chunk splitting failed: {result.stderr}")

        chunks.append(str(chunk_path))

    return chunks


async def compress_audio_if_needed(audio_path: str) -> tuple[str, bool]:
    """
    Compress audio file if it exceeds OpenAI's 25MB limit.

    Returns (path, needs_chunking) where:
    - path: compressed file path (or original if no compression needed)
    - needs_chunking: True if even compressed version exceeds limit
    """
    file_size = os.path.getsize(audio_path)

    if file_size <= MAX_FILE_SIZE_BYTES:
        return audio_path, False

    # Need to compress
    path = Path(audio_path)
    compressed_path = path.parent / f"{path.stem}_compressed.mp3"

    # Calculate target bitrate (aim for ~20MB to have buffer)
    # Get duration first
    duration = await get_audio_duration(audio_path)
    if duration == 0:
        raise ValueError(f"Could not determine duration of {audio_path}")

    # Target 20MB, converted to bits per second
    target_size_bits = 20 * 1024 * 1024 * 8
    target_bitrate = int(target_size_bits / duration)

    # Convert to kbps
    target_bitrate_kbps = max(32, target_bitrate // 1000)  # Minimum 32kbps

    # Compress with ffmpeg
    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-b:a", f"{target_bitrate_kbps}k",
        "-ar", "16000",  # 16kHz sample rate (sufficient for speech)
        "-ac", "1",      # Mono
        "-y",            # Overwrite
        str(compressed_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg compression failed: {result.stderr}")

    compressed_size = os.path.getsize(compressed_path)
    print(f"  Compressed {file_size / 1024 / 1024:.1f}MB -> {compressed_size / 1024 / 1024:.1f}MB")

    # Check if still too large
    needs_chunking = compressed_size > MAX_FILE_SIZE_BYTES

    return str(compressed_path), needs_chunking


async def transcribe_podcast(
    audio_path: str,
    model: str = "whisper-1",
    speaker_id: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe podcast audio with word-level timestamps.

    Uses OpenAI Whisper API with timestamps for accurate alignment.
    Automatically compresses files over 25MB to meet API limits.

    Args:
        audio_path: Path to audio file
        model: Whisper model to use
        speaker_id: Optional speaker identifier

    Returns:
        TranscriptionResult with full transcription and timestamps
    """
    # Get API key from keychain (or environment variable as fallback)
    api_key = get_api_key("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in keychain or environment")

    client = OpenAI(api_key=api_key)

    # Compress if needed and check if chunking is required
    transcribe_path, needs_chunking = await compress_audio_if_needed(audio_path)

    # Handle chunking for very long files
    if needs_chunking:
        print(f"  File still too large after compression, splitting into chunks...")
        chunks = await split_audio_into_chunks(transcribe_path)

        all_words = []
        all_segments = []
        time_offset = 0.0
        full_text = ""

        for chunk_path in chunks:
            with open(chunk_path, "rb") as f:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda f=f: client.audio.transcriptions.create(
                        model=model,
                        file=f,
                        response_format="verbose_json",
                        timestamp_granularities=["word", "segment"]
                    )
                )

            full_text += response.text + " "

            # Adjust timestamps and append
            if hasattr(response, 'words') and response.words:
                for w in response.words:
                    all_words.append(WordTimestamp(
                        word=w.word,
                        start_time=w.start + time_offset,
                        end_time=w.end + time_offset,
                        confidence=getattr(w, 'confidence', 1.0)
                    ))

            if hasattr(response, 'segments') and response.segments:
                for s in response.segments:
                    all_segments.append(TranscriptSegment(
                        segment_id=f"seg_{len(all_segments):03d}",
                        text=s.text.strip(),
                        start_time=s.start + time_offset,
                        end_time=s.end + time_offset,
                        duration=s.end - s.start,
                    ))

            # Update offset for next chunk
            if hasattr(response, 'segments') and response.segments and response.segments:
                time_offset += response.segments[-1].end

            # Clean up chunk
            try:
                os.remove(chunk_path)
            except Exception:
                pass

        word_timestamps = all_words
        segments = all_segments
        transcript_text = full_text.strip()
        language = "en"

    else:
        # Single file transcription
        with open(transcribe_path, "rb") as f:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"]
                )
            )

        # Parse word timestamps
        word_timestamps = []
        if hasattr(response, 'words') and response.words:
            for w in response.words:
                word_timestamps.append(WordTimestamp(
                    word=w.word,
                    start_time=w.start,
                    end_time=w.end,
                    confidence=getattr(w, 'confidence', 1.0)
                ))

        # Parse segments
        segments = []
        if hasattr(response, 'segments') and response.segments:
            for i, s in enumerate(response.segments):
                segments.append(TranscriptSegment(
                    segment_id=f"seg_{i:03d}",
                    text=s.text.strip(),
                    start_time=s.start,
                    end_time=s.end,
                    duration=s.end - s.start,
                ))

        transcript_text = response.text
        language = response.language if hasattr(response, 'language') else "en"

    # Calculate overall confidence
    confidence = 0.0
    if word_timestamps:
        confidence = sum(w.confidence for w in word_timestamps) / len(word_timestamps)

    # Get total duration
    total_duration = segments[-1].end_time if segments else 0.0

    # Sanity check transcription quality
    word_count = len(transcript_text.split())
    wpm = (word_count / total_duration * 60) if total_duration > 0 else 0

    # Validate word count is reasonable
    if word_count < 10:
        raise ValueError(
            f"Transcription produced suspiciously few words ({word_count}). "
            f"Audio may be corrupted or too short."
        )

    # Validate WPM is in reasonable range for speech (50-250 WPM)
    if wpm < 50 or wpm > 250:
        print(f"  WARNING: Words per minute ({wpm:.1f}) is outside normal range (50-250 WPM).")
        print(f"  This may indicate compression/chunking issues or unusual audio content.")

    # Validate word timestamps roughly match word count
    timestamp_word_count = len(word_timestamps)
    if abs(timestamp_word_count - word_count) > word_count * 0.2:  # More than 20% difference
        print(f"  WARNING: Word timestamp count ({timestamp_word_count}) differs significantly from word count ({word_count}).")
        print(f"  This may indicate timing data issues.")

    # Validate segments cover full duration
    if segments and total_duration > 0:
        coverage = segments[-1].end_time / total_duration
        if coverage < 0.95:  # Last segment should reach at least 95% of duration
            print(f"  WARNING: Segments only cover {coverage*100:.1f}% of audio duration.")
            print(f"  Some audio content may be missing from transcription.")

    # Print summary metrics
    print(f"  Transcribed: {word_count} words, {total_duration/60:.1f} min, {wpm:.1f} WPM, {len(segments)} segments")

    # Clean up compressed file if we created one
    if transcribe_path != audio_path:
        try:
            os.remove(transcribe_path)
        except Exception:
            pass  # Non-critical if cleanup fails

    return TranscriptionResult(
        source_path=audio_path,  # Use original path, not compressed
        transcript_text=transcript_text,
        word_timestamps=word_timestamps,
        segments=segments,
        total_duration=total_duration,
        speaker_id=speaker_id,
        confidence=confidence,
        language=language,
    )


async def get_audio_duration(audio_path: str) -> float:
    """
    Get duration of audio file in seconds.

    Uses existing FFmpegRenderer infrastructure.
    """
    from core.renderer import FFmpegRenderer

    renderer = FFmpegRenderer()
    duration = await renderer._get_duration(audio_path)
    return duration if duration else 0.0
