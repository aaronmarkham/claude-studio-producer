"""
Audio-Video Mixing Utilities

Helper functions for mixing individual scenes with audio and concatenating
them into final outputs. Leverages FFmpegRenderer for the heavy lifting.
"""

import asyncio
from pathlib import Path
from typing import List

from core.renderer import FFmpegRenderer
from core.models.render import AudioTrack, TrackType


async def mix_single_scene(
    video_path: str,
    audio_path: str,
    output_path: str,
    fit_mode: str = "stretch",
) -> None:
    """Mix a single video with audio.

    fit_mode:
        - "stretch": Stretch/compress video to match audio duration
        - "truncate": Truncate longer asset to match shorter (shortest mode)
        - "loop": Loop shorter asset to match longer (longest mode)

    Args:
        video_path: Path to video file
        audio_path: Path to audio file
        output_path: Path for mixed output
        fit_mode: How to handle duration mismatches

    Raises:
        RuntimeError: If FFmpeg mixing fails
    """
    # Map our fit_mode names to FFmpegRenderer's fit_mode names
    renderer_fit_mode = {
        "stretch": "speed-match",  # Video speed adjusts to match audio
        "truncate": "shortest",    # Trim to shorter duration
        "loop": "longest",         # Extend shorter to match longer
    }.get(fit_mode, "shortest")

    # Create renderer (will find output directory from output_path)
    output_dir = Path(output_path).parent
    renderer = FFmpegRenderer(output_dir=str(output_dir))

    # Check FFmpeg is available
    ffmpeg_check = await renderer.check_ffmpeg_installed()
    if not ffmpeg_check["installed"]:
        raise RuntimeError("FFmpeg not installed")

    # Create audio track
    audio_track = AudioTrack(
        path=str(audio_path),
        start_time=0.0,
        volume_db=0.0,
        track_type=TrackType.VOICEOVER
    )

    # Mix using FFmpegRenderer
    await renderer.mix_audio(
        video_path=str(video_path),
        audio_tracks=[audio_track],
        output_path=str(output_path),
        ducking=False,  # No ducking for single VO track
        fit_mode=renderer_fit_mode
    )


async def get_media_duration(path: str) -> float:
    """Get duration of a media file in seconds.

    Args:
        path: Path to media file

    Returns:
        Duration in seconds

    Raises:
        RuntimeError: If duration cannot be determined
    """
    # Use FFmpegRenderer's _get_duration method
    renderer = FFmpegRenderer()
    duration = await renderer._get_duration(path)

    if duration is None:
        raise RuntimeError(f"Could not determine duration of {path}")

    return duration


async def concatenate_videos(video_paths: List[Path], output_path: Path) -> None:
    """Concatenate multiple videos into one.

    Args:
        video_paths: List of video file paths
        output_path: Path for concatenated output

    Raises:
        RuntimeError: If concatenation fails
    """
    # Create renderer
    output_dir = output_path.parent
    renderer = FFmpegRenderer(output_dir=str(output_dir))

    # Check FFmpeg is available
    ffmpeg_check = await renderer.check_ffmpeg_installed()
    if not ffmpeg_check["installed"]:
        raise RuntimeError("FFmpeg not installed")

    # Convert Path objects to strings
    video_paths_str = [str(p) for p in video_paths]

    # Use FFmpegRenderer's concat_videos method
    await renderer.concat_videos(
        video_paths=video_paths_str,
        output_path=str(output_path)
    )
