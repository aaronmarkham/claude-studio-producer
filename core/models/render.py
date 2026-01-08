"""
Render models for FFmpeg video assembly

These models represent the rendering configuration and results
for combining video clips and audio tracks into final outputs.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class TrackType(Enum):
    """Audio track types for mixing"""
    VOICEOVER = "vo"
    MUSIC = "music"
    SFX = "sfx"
    AMBIENT = "ambient"


class TransitionType(Enum):
    """Video transition types"""
    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    WIPE = "wipe"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"


@dataclass
class AudioTrack:
    """
    An audio track to be mixed into the final render.

    Attributes:
        path: Path to the audio file
        start_time: When this track starts in the timeline (seconds)
        duration: Duration of the track (None = use full duration)
        volume_db: Volume adjustment in decibels (0 = original, -6 = half volume)
        track_type: Type of audio (voiceover, music, sfx)
        duck_under: List of track types this should duck under
        fade_in: Fade in duration in seconds
        fade_out: Fade out duration in seconds
    """
    path: str
    start_time: float = 0.0
    duration: Optional[float] = None
    volume_db: float = 0.0
    track_type: TrackType = TrackType.MUSIC
    duck_under: List[TrackType] = field(default_factory=list)
    fade_in: float = 0.0
    fade_out: float = 0.0

    # Scene association (for scene-specific audio)
    scene_id: Optional[str] = None


@dataclass
class Transition:
    """
    A transition between video clips.

    Attributes:
        type: Type of transition (cut, fade, dissolve, etc.)
        duration: Duration of the transition in seconds
        position: Position in timeline where transition occurs (seconds)
        from_scene: Scene ID transitioning from
        to_scene: Scene ID transitioning to
    """
    type: TransitionType = TransitionType.CUT
    duration: float = 0.0
    position: float = 0.0
    from_scene: Optional[str] = None
    to_scene: Optional[str] = None


@dataclass
class RenderConfig:
    """
    Configuration for rendering.

    Attributes:
        output_width: Output video width in pixels
        output_height: Output video height in pixels
        output_fps: Output frame rate
        video_codec: Video codec (h264, h265, etc.)
        audio_codec: Audio codec (aac, mp3, etc.)
        video_bitrate: Video bitrate (e.g., "5M" for 5 Mbps)
        audio_bitrate: Audio bitrate (e.g., "192k")
        pixel_format: Pixel format (yuv420p for compatibility)
    """
    output_width: int = 1920
    output_height: int = 1080
    output_fps: float = 30.0
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    video_bitrate: str = "5M"
    audio_bitrate: str = "192k"
    pixel_format: str = "yuv420p"

    # Quality preset (ultrafast, fast, medium, slow, veryslow)
    preset: str = "medium"

    # CRF for quality-based encoding (0-51, lower = better, 23 is default)
    crf: int = 23


@dataclass
class RenderResult:
    """
    Result from a render operation.

    Attributes:
        success: Whether the render completed successfully
        output_path: Path to the rendered video file
        duration: Duration of the rendered video in seconds
        file_size: Size of the output file in bytes
        render_time: Time taken to render in seconds
        error_message: Error message if render failed
        ffmpeg_command: The FFmpeg command that was executed
    """
    success: bool
    output_path: Optional[str] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None
    render_time: Optional[float] = None
    error_message: Optional[str] = None
    ffmpeg_command: Optional[str] = None

    # Detailed logs
    ffmpeg_stdout: Optional[str] = None
    ffmpeg_stderr: Optional[str] = None


@dataclass
class RenderJob:
    """
    A complete render job with all inputs and configuration.

    Attributes:
        job_id: Unique identifier for this render job
        video_clips: List of video file paths in order
        audio_tracks: List of audio tracks to mix
        transitions: List of transitions between clips
        config: Render configuration
        output_path: Where to save the final render
    """
    job_id: str
    video_clips: List[str] = field(default_factory=list)
    audio_tracks: List[AudioTrack] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)
    config: RenderConfig = field(default_factory=RenderConfig)
    output_path: str = ""

    # Metadata
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = None
