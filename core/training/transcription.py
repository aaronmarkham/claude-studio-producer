"""Audio transcription using Whisper"""

import asyncio
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .models import TranscriptionResult, WordTimestamp, TranscriptSegment


async def transcribe_podcast(
    audio_path: str,
    model: str = "whisper-1",
    speaker_id: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe podcast audio with word-level timestamps.

    Uses OpenAI Whisper API with timestamps for accurate alignment.

    Args:
        audio_path: Path to audio file
        model: Whisper model to use
        speaker_id: Optional speaker identifier

    Returns:
        TranscriptionResult with full transcription and timestamps
    """
    client = OpenAI()

    # Read audio file
    with open(audio_path, "rb") as f:
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

    # Calculate overall confidence
    confidence = 0.0
    if word_timestamps:
        confidence = sum(w.confidence for w in word_timestamps) / len(word_timestamps)

    # Get total duration
    total_duration = segments[-1].end_time if segments else 0.0

    return TranscriptionResult(
        source_path=audio_path,
        transcript_text=response.text,
        word_timestamps=word_timestamps,
        segments=segments,
        total_duration=total_duration,
        speaker_id=speaker_id,
        confidence=confidence,
        language=response.language if hasattr(response, 'language') else "en",
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
