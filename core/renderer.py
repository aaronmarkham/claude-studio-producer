"""
FFmpeg-based video renderer for final output assembly.

Combines video clips and audio tracks from an EDL into a final rendered video.
"""

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models.edit_decision import EditDecisionList, EditCandidate, EditDecision
from core.models.render import (
    AudioTrack,
    Transition,
    TransitionType,
    TrackType,
    RenderConfig,
    RenderResult,
    RenderJob,
)


class FFmpegNotFoundError(Exception):
    """Raised when FFmpeg is not installed or not in PATH."""
    pass


class RenderError(Exception):
    """Raised when rendering fails."""
    pass


class FFmpegRenderer:
    """
    FFmpeg-based renderer for combining video and audio into final output.

    Handles:
    - Video concatenation
    - Audio mixing with ducking
    - Transitions (fade, dissolve)
    - Output encoding
    """

    def __init__(
        self,
        output_dir: str = "artifacts/renders",
        config: Optional[RenderConfig] = None
    ):
        """
        Initialize the renderer.

        Args:
            output_dir: Directory for rendered output files
            config: Render configuration (uses defaults if not provided)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or RenderConfig()

        # Check FFmpeg availability
        self._ffmpeg_path = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg

        # Check common locations on Windows
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path

        # Check WinGet installation location
        winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
        if os.path.exists(winget_base):
            import glob
            # Search for FFmpeg in WinGet packages
            patterns = [
                os.path.join(winget_base, "Gyan.FFmpeg*", "ffmpeg-*", "bin", "ffmpeg.exe"),
                os.path.join(winget_base, "*FFmpeg*", "*", "bin", "ffmpeg.exe"),
            ]
            for pattern in patterns:
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]

        # FFmpeg not found - will raise error when trying to render
        return "ffmpeg"

    def _check_ffmpeg(self) -> bool:
        """Check if FFmpeg is available."""
        try:
            result = asyncio.subprocess.create_subprocess_exec(
                self._ffmpeg_path, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            return True
        except FileNotFoundError:
            return False

    async def render(
        self,
        edl: EditDecisionList,
        candidate_id: Optional[str] = None,
        audio_tracks: Optional[List[AudioTrack]] = None,
        run_id: Optional[str] = None
    ) -> RenderResult:
        """
        Render an EDL candidate to final video.

        Args:
            edl: The Edit Decision List containing candidates
            candidate_id: Which candidate to render (default: recommended)
            audio_tracks: Additional audio tracks to mix in
            run_id: Optional run ID for output organization

        Returns:
            RenderResult with output path and metadata
        """
        # Select candidate
        if candidate_id is None:
            candidate_id = edl.recommended_candidate_id

        candidate = None
        for c in edl.candidates:
            if c.candidate_id == candidate_id:
                candidate = c
                break

        if candidate is None:
            return RenderResult(
                success=False,
                error_message=f"Candidate '{candidate_id}' not found in EDL"
            )

        # Create output directory for this render
        run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        render_dir = self.output_dir / run_id
        render_dir.mkdir(parents=True, exist_ok=True)

        # Render the candidate
        return await self.render_candidate(
            candidate=candidate,
            audio_tracks=audio_tracks or [],
            output_dir=render_dir
        )

    async def render_candidate(
        self,
        candidate: EditCandidate,
        audio_tracks: List[AudioTrack],
        output_dir: Path
    ) -> RenderResult:
        """
        Full render pipeline for one edit candidate.

        Steps:
        1. Validate all input files exist
        2. Trim each clip according to in_point/out_point
        3. Apply transitions (fade in/out, dissolves between clips)
        4. Mix audio tracks
        5. Output final file

        Args:
            candidate: The edit candidate to render
            audio_tracks: Audio tracks to mix in
            output_dir: Directory for output files

        Returns:
            RenderResult with final video path
        """
        start_time = time.time()

        # Validate decisions have video files
        valid_decisions = []
        for d in candidate.decisions:
            if not d.video_url:
                continue
            video_path = d.video_url
            if not os.path.exists(video_path):
                video_path = os.path.abspath(d.video_url)
            if os.path.exists(video_path):
                valid_decisions.append((d, video_path))

        if not valid_decisions:
            # Mock mode - no real files to render
            output_path = output_dir / f"{candidate.candidate_id}_final.mp4"
            return RenderResult(
                success=True,
                output_path=str(output_path),
                duration=candidate.total_duration,
                file_size=0,
                render_time=time.time() - start_time,
                error_message="Mock render - no real video files to process"
            )

        try:
            # Step 1: Trim clips according to in_point/out_point
            trimmed_clips = []
            trim_dir = output_dir / "trimmed"
            trim_dir.mkdir(exist_ok=True)

            for i, (decision, video_path) in enumerate(valid_decisions):
                trimmed_path = trim_dir / f"clip_{i:02d}_{decision.scene_id}.mp4"
                await self._trim_clip(
                    input_path=video_path,
                    output_path=str(trimmed_path),
                    in_point=decision.in_point or 0.0,
                    out_point=decision.out_point
                )

                # Step 1b: Apply text overlay if specified
                current_path = str(trimmed_path) if os.path.exists(trimmed_path) else video_path
                if decision.text_overlay:
                    text_path = trim_dir / f"clip_{i:02d}_{decision.scene_id}_text.mp4"
                    await self.add_text_overlay(
                        video_path=current_path,
                        text=decision.text_overlay,
                        output_path=str(text_path),
                        position=decision.text_position or "center",
                        style=decision.text_style or "title",
                        start_time=decision.text_start_time,
                        duration=decision.text_duration
                    )
                    if os.path.exists(text_path):
                        current_path = str(text_path)

                if os.path.exists(current_path):
                    trimmed_clips.append((decision, current_path))
                else:
                    # Fallback to original if processing fails
                    trimmed_clips.append((decision, video_path))

            # Step 2: Apply transitions and concatenate
            # Check if we have any dissolve transitions
            has_dissolves = any(
                d.transition_out in ("dissolve", "cross_dissolve") or
                d.transition_in in ("dissolve", "cross_dissolve")
                for d, _ in trimmed_clips
            )

            if has_dissolves and len(trimmed_clips) > 1:
                # Use xfade for dissolve transitions
                concat_output = output_dir / f"{candidate.candidate_id}_concat.mp4"
                await self._concat_with_transitions(
                    clips=trimmed_clips,
                    output_path=str(concat_output)
                )
            else:
                # Simple concatenation with fade in/out at edges
                concat_output = output_dir / f"{candidate.candidate_id}_concat.mp4"
                await self.concat_videos(
                    video_paths=[path for _, path in trimmed_clips],
                    output_path=str(concat_output)
                )

            if not os.path.exists(concat_output):
                return RenderResult(
                    success=False,
                    error_message="Concatenation failed",
                    render_time=time.time() - start_time
                )

            # Step 3: Apply fade in/out at video boundaries
            transitions = self._build_transitions(candidate.decisions)
            if transitions:
                transition_output = output_dir / f"{candidate.candidate_id}_transitions.mp4"
                await self.add_transitions(
                    video_path=str(concat_output),
                    transitions=transitions,
                    output_path=str(transition_output)
                )
                if os.path.exists(transition_output):
                    concat_output = transition_output

            # Step 4: Mix audio if we have tracks
            final_output = output_dir / f"{candidate.candidate_id}_final.mp4"

            if audio_tracks:
                await self.mix_audio(
                    video_path=str(concat_output),
                    audio_tracks=audio_tracks,
                    output_path=str(final_output)
                )
            else:
                # Just copy to final output
                shutil.copy(concat_output, final_output)

            # Get file info
            file_size = os.path.getsize(final_output) if os.path.exists(final_output) else 0
            duration = await self._get_duration(str(final_output))

            return RenderResult(
                success=True,
                output_path=str(final_output),
                duration=duration,
                file_size=file_size,
                render_time=time.time() - start_time
            )

        except Exception as e:
            return RenderResult(
                success=False,
                error_message=str(e),
                render_time=time.time() - start_time
            )

    async def _trim_clip(
        self,
        input_path: str,
        output_path: str,
        in_point: float,
        out_point: Optional[float]
    ) -> None:
        """
        Trim a video clip to the specified in/out points.

        Args:
            input_path: Source video file
            output_path: Trimmed output file
            in_point: Start time in seconds
            out_point: End time in seconds (None = to end of clip)
        """
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-ss", str(in_point),  # Seek before input (fast)
            "-i", input_path,
        ]

        if out_point is not None:
            duration = out_point - in_point
            cmd.extend(["-t", str(duration)])

        cmd.extend([
            "-c:v", self.config.video_codec,
            "-c:a", self.config.audio_codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-pix_fmt", self.config.pixel_format,
            output_path
        ])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

    async def _concat_with_transitions(
        self,
        clips: List[tuple],  # List of (EditDecision, path)
        output_path: str
    ) -> None:
        """
        Concatenate clips with xfade transitions between them.

        Uses FFmpeg's xfade filter for dissolve/cross_dissolve transitions.

        Args:
            clips: List of (EditDecision, video_path) tuples
            output_path: Output file path
        """
        if len(clips) == 1:
            shutil.copy(clips[0][1], output_path)
            return

        # Build xfade filter chain
        # xfade requires chaining: [0:v][1:v]xfade=...[v01]; [v01][2:v]xfade=...[v012]; etc.
        inputs = []
        for _, path in clips:
            inputs.extend(["-i", path])

        # Get durations for calculating xfade offsets
        durations = []
        for _, path in clips:
            dur = await self._get_duration(path)
            durations.append(dur or 5.0)

        # Build filter chain
        filter_parts = []
        current_label = "[0:v]"
        cumulative_duration = durations[0]

        for i in range(1, len(clips)):
            decision = clips[i - 1][0]  # Previous clip's decision (for transition_out)

            # Determine transition type and duration
            trans_out = decision.transition_out or "cut"
            trans_dur = decision.transition_out_duration or 0.5

            if trans_out in ("dissolve", "cross_dissolve"):
                # xfade offset is when the transition starts (relative to output timeline)
                offset = cumulative_duration - trans_dur
                next_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"

                filter_parts.append(
                    f"{current_label}[{i}:v]xfade=transition=fade:duration={trans_dur}:offset={offset}{next_label}"
                )
                current_label = next_label
                # Accumulate duration minus overlap
                cumulative_duration += durations[i] - trans_dur
            else:
                # Cut transition - just concat without xfade
                # This is trickier with xfade chain, so we use offset=duration (no overlap)
                offset = cumulative_duration
                next_label = f"[v{i}]" if i < len(clips) - 1 else "[vout]"

                filter_parts.append(
                    f"{current_label}[{i}:v]xfade=transition=fade:duration=0.01:offset={offset}{next_label}"
                )
                current_label = next_label
                cumulative_duration += durations[i]

        filter_complex = ";".join(filter_parts)

        cmd = [
            self._ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", self.config.video_codec,
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            "-pix_fmt", self.config.pixel_format,
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Fallback to simple concat if xfade fails
            await self.concat_videos(
                video_paths=[path for _, path in clips],
                output_path=output_path
            )

    async def concat_videos(
        self,
        video_paths: List[str],
        output_path: str
    ) -> str:
        """
        Concatenate video clips using FFmpeg concat demuxer.

        Args:
            video_paths: List of video file paths in order
            output_path: Path for the concatenated output

        Returns:
            Path to concatenated video
        """
        if not video_paths:
            raise RenderError("No video paths provided for concatenation")

        # Filter to only existing files (check both relative and absolute)
        existing_paths = []
        for p in video_paths:
            if os.path.exists(p):
                existing_paths.append(p)
            elif os.path.exists(os.path.abspath(p)):
                existing_paths.append(os.path.abspath(p))

        if not existing_paths:
            raise RenderError(f"None of the provided video files exist: {video_paths[:3]}...")

        # If only one file, just copy it
        if len(existing_paths) == 1:
            shutil.copy(existing_paths[0], output_path)
            return output_path

        # Create concat file for FFmpeg
        concat_file = self._generate_concat_file(existing_paths)

        try:
            # Run FFmpeg concat
            cmd = [
                self._ffmpeg_path,
                "-y",  # Overwrite output
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # Stream copy (fast, no re-encoding)
                output_path
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                # Try with re-encoding if stream copy fails
                cmd = [
                    self._ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c:v", self.config.video_codec,
                    "-c:a", self.config.audio_codec,
                    "-preset", self.config.preset,
                    "-crf", str(self.config.crf),
                    "-pix_fmt", self.config.pixel_format,
                    output_path
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    raise RenderError(f"FFmpeg concat failed: {stderr.decode()}")

            return output_path

        finally:
            # Clean up concat file
            if os.path.exists(concat_file):
                os.remove(concat_file)

    async def mix_audio(
        self,
        video_path: str,
        audio_tracks: List[AudioTrack],
        output_path: str,
        ducking: bool = True
    ) -> str:
        """
        Mix audio tracks into the video.

        Supports:
        - Multiple audio tracks (VO, music, SFX)
        - Volume adjustment per track
        - Ducking (lower music when VO plays)
        - Fade in/out

        Args:
            video_path: Path to the video file
            audio_tracks: List of audio tracks to mix
            output_path: Path for the output file
            ducking: Whether to apply ducking (lower music under VO)

        Returns:
            Path to the output video with mixed audio
        """
        if not audio_tracks:
            shutil.copy(video_path, output_path)
            return output_path

        # Filter to existing audio files
        existing_tracks = [t for t in audio_tracks if os.path.exists(t.path)]
        if not existing_tracks:
            shutil.copy(video_path, output_path)
            return output_path

        # Build FFmpeg filter complex
        filter_complex = self._generate_filter_complex(existing_tracks, ducking)

        # Build input arguments
        inputs = ["-i", video_path]
        for track in existing_tracks:
            inputs.extend(["-i", track.path])

        cmd = [
            self._ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "0:v",  # Video from first input
            "-map", "[aout]",  # Mixed audio
            "-c:v", "copy",  # Copy video stream
            "-c:a", self.config.audio_codec,
            "-b:a", self.config.audio_bitrate,
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RenderError(f"FFmpeg audio mix failed: {stderr.decode()}")

        return output_path

    async def add_transitions(
        self,
        video_path: str,
        transitions: List[Transition],
        output_path: str
    ) -> str:
        """
        Apply transitions to video.

        Currently supports:
        - fade_in: Fade from black at start
        - fade_out: Fade to black at end
        - fade: Cross-fade between clips (requires re-encoding)

        Args:
            video_path: Path to the video file
            transitions: List of transitions to apply
            output_path: Path for the output file

        Returns:
            Path to the output video with transitions
        """
        if not transitions:
            shutil.copy(video_path, output_path)
            return output_path

        # Build video filter for transitions
        filters = []

        for t in transitions:
            if t.type == TransitionType.FADE_IN:
                filters.append(f"fade=t=in:st=0:d={t.duration}")
            elif t.type == TransitionType.FADE_OUT:
                filters.append(f"fade=t=out:st={t.position}:d={t.duration}")
            elif t.type == TransitionType.FADE:
                # Cross-fade requires xfade filter (complex)
                filters.append(f"fade=t=out:st={t.position}:d={t.duration}")

        if not filters:
            shutil.copy(video_path, output_path)
            return output_path

        filter_str = ",".join(filters)

        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", filter_str,
            "-c:v", self.config.video_codec,
            "-c:a", "copy",
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RenderError(f"FFmpeg transition failed: {stderr.decode()}")

        return output_path

    async def add_text_overlay(
        self,
        video_path: str,
        text: str,
        output_path: str,
        position: str = "center",
        style: str = "title",
        start_time: Optional[float] = None,
        duration: Optional[float] = None
    ) -> str:
        """
        Add text overlay to video using FFmpeg drawtext filter.

        Args:
            video_path: Path to the video file
            text: Text to display
            output_path: Path for the output file
            position: Where to place text ("center", "lower_third", "upper_third", "top", "bottom")
            style: Text style ("title", "subtitle", "caption", "watermark")
            start_time: When text appears (None = start of video)
            duration: How long text shows (None = entire video)

        Returns:
            Path to the output video with text overlay
        """
        if not text:
            shutil.copy(video_path, output_path)
            return output_path

        # Escape special characters for FFmpeg drawtext
        escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

        # Style settings
        style_settings = {
            "title": {
                "fontsize": 72,
                "fontcolor": "white",
                "borderw": 3,
                "bordercolor": "black",
            },
            "subtitle": {
                "fontsize": 48,
                "fontcolor": "white",
                "borderw": 2,
                "bordercolor": "black",
            },
            "caption": {
                "fontsize": 36,
                "fontcolor": "white",
                "box": 1,
                "boxcolor": "black@0.6",
                "boxborderw": 10,
            },
            "watermark": {
                "fontsize": 24,
                "fontcolor": "white@0.7",
                "borderw": 1,
                "bordercolor": "black@0.5",
            },
        }

        settings = style_settings.get(style, style_settings["title"])

        # Position settings (x, y coordinates)
        position_coords = {
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "lower_third": "x=(w-text_w)/2:y=h-text_h-h/6",
            "upper_third": "x=(w-text_w)/2:y=h/6",
            "top": "x=(w-text_w)/2:y=50",
            "bottom": "x=(w-text_w)/2:y=h-text_h-50",
        }

        # Special position for watermark (bottom-right corner)
        if style == "watermark":
            coords = "x=w-text_w-20:y=h-text_h-20"
        else:
            coords = position_coords.get(position, position_coords["center"])

        # Build drawtext filter
        filter_parts = [
            f"text='{escaped_text}'",
            f"fontsize={settings['fontsize']}",
            f"fontcolor={settings['fontcolor']}",
            coords,
        ]

        # Add border if specified
        if "borderw" in settings:
            filter_parts.append(f"borderw={settings['borderw']}")
            filter_parts.append(f"bordercolor={settings['bordercolor']}")

        # Add box (background) if specified
        if settings.get("box"):
            filter_parts.append("box=1")
            filter_parts.append(f"boxcolor={settings['boxcolor']}")
            filter_parts.append(f"boxborderw={settings['boxborderw']}")

        # Add timing (enable filter)
        if start_time is not None or duration is not None:
            video_duration = await self._get_duration(video_path) or 30.0
            start = start_time or 0.0
            end = start + duration if duration else video_duration
            filter_parts.append(f"enable='between(t,{start},{end})'")

        # Try to find a font file
        font_path = self._find_font()
        if font_path:
            # Escape backslashes and colons for Windows paths
            escaped_font = font_path.replace("\\", "/").replace(":", "\\:")
            filter_parts.append(f"fontfile='{escaped_font}'")

        drawtext_filter = f"drawtext={':'.join(filter_parts)}"

        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", drawtext_filter,
            "-c:v", self.config.video_codec,
            "-c:a", "copy",
            "-preset", self.config.preset,
            "-crf", str(self.config.crf),
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # If drawtext fails (often due to font issues), return original
            shutil.copy(video_path, output_path)

        return output_path

    def _find_font(self) -> Optional[str]:
        """Find a suitable font file for text overlays."""
        # Common font paths
        font_paths = [
            # Windows
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            # macOS
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]

        for path in font_paths:
            if os.path.exists(path):
                return path

        return None

    def _generate_concat_file(self, video_paths: List[str]) -> str:
        """
        Generate FFmpeg concat demuxer file.

        Args:
            video_paths: List of video file paths

        Returns:
            Path to the temporary concat file
        """
        # Create temp file for concat list
        fd, concat_path = tempfile.mkstemp(suffix=".txt", prefix="ffmpeg_concat_")

        with os.fdopen(fd, 'w') as f:
            for path in video_paths:
                # Convert to absolute path to avoid working directory issues
                abs_path = os.path.abspath(path)
                # Escape single quotes and write in concat format
                escaped_path = abs_path.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        return concat_path

    def _generate_filter_complex(
        self,
        audio_tracks: List[AudioTrack],
        ducking: bool = True
    ) -> str:
        """
        Generate FFmpeg filter_complex for audio mixing.

        Args:
            audio_tracks: List of audio tracks
            ducking: Whether to apply ducking

        Returns:
            Filter complex string for FFmpeg
        """
        if not audio_tracks:
            return ""

        filters = []
        track_labels = []

        # Process each track
        for i, track in enumerate(audio_tracks):
            input_idx = i + 1  # Input 0 is video, audio starts at 1
            label = f"a{i}"

            # Build filter chain for this track
            track_filters = []

            # Volume adjustment
            if track.volume_db != 0:
                # Convert dB to linear
                volume = 10 ** (track.volume_db / 20)
                track_filters.append(f"volume={volume:.2f}")

            # Fade in
            if track.fade_in > 0:
                track_filters.append(f"afade=t=in:st=0:d={track.fade_in}")

            # Fade out (would need duration info)
            if track.fade_out > 0:
                track_filters.append(f"afade=t=out:d={track.fade_out}")

            # Delay if start_time > 0
            if track.start_time > 0:
                delay_ms = int(track.start_time * 1000)
                track_filters.append(f"adelay={delay_ms}|{delay_ms}")

            if track_filters:
                filter_str = f"[{input_idx}:a]{','.join(track_filters)}[{label}]"
            else:
                filter_str = f"[{input_idx}:a]acopy[{label}]"

            filters.append(filter_str)
            track_labels.append(f"[{label}]")

        # Mix all tracks together
        if len(track_labels) > 1:
            mix_inputs = "".join(track_labels)
            filters.append(f"{mix_inputs}amix=inputs={len(track_labels)}:normalize=0[aout]")
        else:
            # Single track, just rename
            filters.append(f"{track_labels[0]}acopy[aout]")

        return ";".join(filters)

    def _build_transitions(self, decisions: List[EditDecision]) -> List[Transition]:
        """
        Build transition list from edit decisions.

        NOTE: Currently only supports fade-in at the start and fade-out at the end
        of the entire video. Mid-video transitions (cross-fades between scenes) would
        require the xfade filter with pre-segmented clips, which is much more complex.

        Applying multiple fade-out filters to a concatenated video causes it to go
        black at the first fade point and stay black. So we only handle:
        - First scene's transition_in (fade from black at video start)
        - Last scene's transition_out (fade to black at video end)

        Args:
            decisions: List of edit decisions

        Returns:
            List of Transition objects
        """
        if not decisions:
            return []

        transitions = []

        # Calculate total duration
        total_duration = sum(d.duration or 5.0 for d in decisions)

        # Only apply fade-in at the very start (first scene)
        first = decisions[0]
        if first.transition_in and first.transition_in in ("fade_in", "fade"):
            transitions.append(Transition(
                type=TransitionType.FADE_IN,
                duration=first.transition_in_duration or 0.5,
                position=0.0,
                to_scene=first.scene_id
            ))

        # Only apply fade-out at the very end (last scene)
        last = decisions[-1]
        if last.transition_out and last.transition_out in ("fade_out", "fade"):
            fade_duration = last.transition_out_duration or 0.5
            transitions.append(Transition(
                type=TransitionType.FADE_OUT,
                duration=fade_duration,
                position=total_duration - fade_duration,
                from_scene=last.scene_id
            ))

        return transitions

    async def _get_duration(self, video_path: str) -> Optional[float]:
        """Get duration of a video file using FFprobe."""
        if not os.path.exists(video_path):
            return None

        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            # Try to find it next to ffmpeg
            ffmpeg_dir = os.path.dirname(self._ffmpeg_path)
            ffprobe = os.path.join(ffmpeg_dir, "ffprobe")
            if not os.path.exists(ffprobe):
                ffprobe = os.path.join(ffmpeg_dir, "ffprobe.exe")
                if not os.path.exists(ffprobe):
                    return None

        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return float(stdout.decode().strip())
        except Exception:
            pass

        return None

    async def check_ffmpeg_installed(self) -> Dict[str, Any]:
        """
        Check if FFmpeg is properly installed.

        Returns:
            Dict with installation status and version info
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self._ffmpeg_path, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                version_line = stdout.decode().split('\n')[0]
                return {
                    "installed": True,
                    "path": self._ffmpeg_path,
                    "version": version_line
                }
        except FileNotFoundError:
            pass

        return {
            "installed": False,
            "path": None,
            "version": None,
            "error": "FFmpeg not found. Please install FFmpeg and add it to your PATH."
        }
