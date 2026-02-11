"""
Assemble command - Create rough cut video from production assets.

Phase 5 of Unified Production Architecture: Timed assembly with figure sync points.

This uses the assembly manifest from ContentLibrarian to:
1. Sync figure segments to when narration discusses them
2. Apply Ken Burns effects to DALL-E and figure images
3. Hold previous image for carry-forward segments
4. Create rough cut video with proper audio sync
"""

import subprocess
import json
import sys
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.text import Text
from rich import box

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from cli.theme import get_theme
from core.models.structured_script import StructuredScript
from core.models.content_library import ContentLibrary
from core.content_librarian import ContentLibrarian

console = Console()


@dataclass
class AudioClip:
    """Audio clip with timing information."""
    path: Path
    duration: float
    segment_idx: int
    start_time: float = 0.0  # Cumulative start in final video


@dataclass
class VisualSegment:
    """Visual segment for assembly."""
    segment_idx: int
    display_mode: str  # figure_sync, dall_e, web_image, carry_forward, text_only, transcript
    image_path: Optional[Path]
    audio_path: Optional[Path]
    audio_duration: float
    start_time: float
    end_time: float
    transcript_text: str = ""  # Narration text for transcript overlay mode


def get_media_duration(path: Path) -> float:
    """Get duration of audio/video file using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(path)
            ],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        return 0.0


def create_transcript_overlay(text: str, duration: float, output_path: Path,
                               font_size: int = 42, max_chars_per_line: int = 50,
                               bg_color: tuple = (26, 26, 46),
                               text_color: str = "white") -> bool:
    """Create a video segment showing transcript text on a dark background.

    Uses Pillow for text rendering (no freetype/drawtext dependency) and
    ffmpeg to encode the static frame into a video segment.
    """
    from PIL import Image, ImageDraw, ImageFont

    if duration <= 0:
        return False

    # Word-wrap text
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_chars_per_line and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1
    if current_line:
        lines.append(" ".join(current_line))

    # Limit to ~12 lines (screen height) — truncate if needed
    if len(lines) > 12:
        lines = lines[:12]
        lines[-1] = lines[-1][:max_chars_per_line - 3] + "..."

    wrapped = "\n".join(lines)

    # Render with Pillow
    img = Image.new('RGB', (1920, 1080), color=bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except OSError:
        try:
            # Linux fallback
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except OSError:
            font = ImageFont.load_default(size=font_size)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (1920 - text_w) // 2
    y = (1080 - text_h) // 2

    # Draw text with slight shadow for readability
    draw.multiline_text((x + 2, y + 2), wrapped, fill=(0, 0, 0), font=font, align="center")
    draw.multiline_text((x, y), wrapped, fill=text_color, font=font, align="center")

    # Save frame to temp file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        frame_path = f.name
        img.save(frame_path)

    fps = 30
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", frame_path,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(frame_path)


def create_video_with_ken_burns(image_path: Path, duration: float, output_path: Path) -> bool:
    """Create a video from a static image with smooth Ken Burns (slow zoom) effect.

    Uses ease-in-out interpolation via frame number for jitter-free zooming.
    Zooms from 1.0 to 1.08 over the duration, centered.
    """
    if duration <= 0:
        return False

    fps = 30
    total_frames = int(duration * fps)

    # Smooth ease-in-out zoom using cosine interpolation
    # progress = on/d (0→1 over duration)
    # zoom = 1 + 0.08 * (1 - cos(progress * PI)) / 2
    # This gives smooth acceleration and deceleration
    zoom_range = 0.08  # 8% zoom — subtle but visible, no jitter
    zoom_expr = f"1+{zoom_range}*(1-cos(on/{total_frames}*PI))/2"

    filter_complex = (
        f"scale=3840:2160:force_original_aspect_ratio=decrease,"
        f"pad=3840:2160:(ow-iw)/2:(oh-ih)/2:black,"
        f"zoompan=z='{zoom_expr}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s=1920x1080:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", filter_complex,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def concatenate_audio(audio_clips: List[AudioClip], output_path: Path) -> bool:
    """Concatenate all audio clips into a single file."""
    if not audio_clips:
        return False

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for clip in audio_clips:
            # Use absolute paths for ffmpeg concat (resolves relative to concat file dir)
            path_str = str(Path(clip.path).resolve()).replace('\\', '/')
            f.write(f"file '{path_str}'\n")
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(concat_file)


def create_final_video(video_segments: List[Path], audio_path: Path, output_path: Path) -> bool:
    """Concatenate video segments and add audio track."""
    if not video_segments:
        return False

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for seg in video_segments:
            path_str = str(Path(seg).resolve()).replace('\\', '/')
            f.write(f"file '{path_str}'\n")
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v", "-map", "1:a",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(concat_file)


def load_production_run(run_dir: Path) -> Tuple[Optional[StructuredScript], Optional[ContentLibrary], dict]:
    """Load structured script and content library from a production run."""

    # Load structured script
    structured_script = None
    script_files = list(run_dir.glob("*_structured_script.json"))
    if script_files:
        try:
            structured_script = StructuredScript.load(script_files[0])
        except Exception:
            pass

    # Load content library
    content_library = None
    library_path = run_dir / "content_library.json"
    if library_path.exists():
        try:
            content_library = ContentLibrary.load(library_path)
        except Exception:
            pass

    # Load asset manifest (fallback)
    manifest = {}
    manifest_path = run_dir / "asset_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass

    return structured_script, content_library, manifest


def build_visual_segments_from_manifest(
    manifest: dict,
    audio_dir: Path,
    images_dir: Path,
) -> List[VisualSegment]:
    """Build visual segments from asset manifest when no structured script available."""
    segments = []
    cumulative_time = 0.0
    last_image_path = None

    assets = manifest.get("assets", [])

    for asset in assets:
        segment_idx = int(asset.get("scene_id", "scene_000").split("_")[1])

        # Get audio
        audio_path = None
        audio_duration = 5.0  # Default

        if asset.get("audio_path"):
            audio_path = Path(asset["audio_path"])
            if audio_path.exists():
                audio_duration = get_media_duration(audio_path)
        else:
            # Try to find audio file
            for audio_file in audio_dir.glob(f"audio_{segment_idx:03d}.*"):
                audio_path = audio_file
                audio_duration = get_media_duration(audio_path)
                break

        # Get image
        image_path = None
        display_mode = "carry_forward"

        if asset.get("image_path"):
            img = Path(asset["image_path"])
            if img.exists():
                image_path = img
                display_mode = "dall_e"

        if image_path:
            last_image_path = image_path
        elif last_image_path:
            image_path = last_image_path
            display_mode = "carry_forward"

        start_time = cumulative_time
        end_time = cumulative_time + audio_duration
        cumulative_time = end_time

        segments.append(VisualSegment(
            segment_idx=segment_idx,
            display_mode=display_mode,
            image_path=image_path,
            audio_path=audio_path,
            audio_duration=audio_duration,
            start_time=start_time,
            end_time=end_time,
        ))

    return segments


def build_visual_segments_from_librarian(
    structured_script: StructuredScript,
    librarian: ContentLibrarian,
    audio_dir: Path,
) -> Tuple[List[VisualSegment], dict]:
    """
    Build visual segments from structured script and librarian manifest.

    Returns:
        Tuple of (segments, manifest) where manifest is the raw assembly manifest
        for debugging and inspection.
    """
    manifest = librarian.build_assembly_manifest(structured_script)
    segments = []
    cumulative_time = 0.0
    last_image_path = None

    for seg_data in manifest.get("segments", []):
        segment_idx = seg_data.get("segment_idx", 0)
        display_mode = seg_data.get("display_mode", "carry_forward")

        # Get audio
        audio_path = None
        audio_duration = seg_data.get("audio", {}).get("duration_sec", 5.0)

        audio_asset_path = seg_data.get("audio", {}).get("path")
        if audio_asset_path:
            audio_path = Path(audio_asset_path)
            if audio_path.exists():
                audio_duration = get_media_duration(audio_path)
        else:
            # Try to find audio file by segment index
            for audio_file in audio_dir.glob(f"audio_{segment_idx:03d}.*"):
                audio_path = audio_file
                audio_duration = get_media_duration(audio_path)
                break

        # Get visual
        image_path = None
        visual_data = seg_data.get("visual", {})

        if visual_data.get("path"):
            img = Path(visual_data["path"])
            if img.exists():
                image_path = img

        # Get transcript text for overlay
        transcript_text = seg_data.get("text_preview", "")
        # Get full text from structured script if available
        if structured_script:
            script_seg = structured_script.get_segment(segment_idx)
            if script_seg:
                transcript_text = script_seg.text

        # Handle carry-forward and transcript fallback
        if image_path:
            last_image_path = image_path
        elif display_mode == "carry_forward" and last_image_path:
            image_path = last_image_path
        elif display_mode in ("text_only", "carry_forward") or not image_path:
            # No image available — use transcript overlay
            display_mode = "transcript"

        start_time = cumulative_time
        end_time = cumulative_time + audio_duration
        cumulative_time = end_time

        segments.append(VisualSegment(
            segment_idx=segment_idx,
            display_mode=display_mode,
            image_path=image_path,
            audio_path=audio_path,
            audio_duration=audio_duration,
            start_time=start_time,
            end_time=end_time,
            transcript_text=transcript_text,
        ))

    return segments, manifest


def print_assembly_summary(segments: List[VisualSegment], t):
    """Print summary of segments to assemble."""
    table = Table(
        title="Assembly Plan",
        box=box.ROUNDED,
        border_style=t.panel_border,
    )
    table.add_column("Display Mode", style=t.label, width=15)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Total Duration", justify="right", width=14)

    mode_counts = {}
    mode_durations = {}

    for seg in segments:
        mode = seg.display_mode
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        mode_durations[mode] = mode_durations.get(mode, 0.0) + seg.audio_duration

    for mode in sorted(mode_counts.keys()):
        count = mode_counts[mode]
        duration = mode_durations[mode]
        table.add_row(mode, str(count), f"{duration:.1f}s")

    total_duration = sum(seg.audio_duration for seg in segments)
    table.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{len(segments)}[/]",
        f"[bold]{total_duration:.1f}s ({total_duration/60:.1f}m)[/]"
    )

    console.print(table)
    console.print()


async def _assemble_async(
    run_dir: str,
    output: Optional[str],
    skip_existing: bool,
):
    """Main async assembly function."""
    t = get_theme()
    run_path = Path(run_dir)

    if not run_path.exists():
        raise click.ClickException(f"Run directory not found: {run_dir}")

    # Print header
    header_text = Text()
    header_text.append("🎬 ", style="bold")
    header_text.append("Rough Cut Assembly", style=t.header)
    header_text.append(f"\n   Run: {run_path.name}", style=t.dimmed)

    console.print(Panel(
        header_text,
        border_style=t.panel_border,
        box=box.DOUBLE,
        padding=(0, 2)
    ))
    console.print()

    # Load production artifacts
    console.print(f"[{t.label}]Loading production artifacts...[/]")
    structured_script, content_library, manifest = load_production_run(run_path)

    audio_dir = run_path / "audio"
    images_dir = run_path / "images"

    assembly_manifest = None  # Will be saved for debugging

    if structured_script and content_library:
        console.print(f"[{t.success}]Found structured script and content library (Unified Architecture)[/]")
        librarian = ContentLibrarian(content_library)
        segments, assembly_manifest = build_visual_segments_from_librarian(
            structured_script, librarian, audio_dir
        )
    elif manifest:
        console.print(f"[{t.dimmed}]Using asset manifest (legacy mode)[/]")
        segments = build_visual_segments_from_manifest(manifest, audio_dir, images_dir)
    else:
        raise click.ClickException("No structured script or asset manifest found")

    console.print(f"[{t.success}]Loaded {len(segments)} segments[/]\n")

    # Print summary
    print_assembly_summary(segments, t)

    # Prepare output directory
    output_dir = run_path / "assembly"
    output_dir.mkdir(exist_ok=True)
    segments_dir = output_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    # Save assembly manifest for debugging (if using Unified Architecture)
    if assembly_manifest:
        manifest_path = output_dir / "assembly_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(assembly_manifest, f, indent=2, default=str)
        console.print(f"[{t.dimmed}]Saved assembly manifest to:[/] {manifest_path}")

    # Collect audio clips
    audio_clips = []
    for seg in segments:
        if seg.audio_path and seg.audio_path.exists():
            audio_clips.append(AudioClip(
                path=seg.audio_path,
                duration=seg.audio_duration,
                segment_idx=seg.segment_idx,
                start_time=seg.start_time,
            ))

    # Concatenate audio
    console.print(f"[{t.label}]Concatenating audio ({len(audio_clips)} clips)...[/]")
    audio_combined = output_dir / "audio_combined.mp3"

    if not concatenate_audio(audio_clips, audio_combined):
        raise click.ClickException("Failed to concatenate audio")
    console.print(f"[{t.success}]Audio combined: {audio_combined.name}[/]\n")

    # Create video segments
    console.print(f"[{t.label}]Creating video segments...[/]")
    video_segments = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console
    ) as progress:
        task = progress.add_task("Rendering segments...", total=len(segments))

        for seg in segments:
            segment_path = segments_dir / f"segment_{seg.segment_idx:03d}.mp4"

            # Skip if exists and skip_existing is True
            if skip_existing and segment_path.exists():
                video_segments.append(segment_path)
                progress.advance(task)
                continue

            progress.update(
                task,
                description=f"Segment {seg.segment_idx:03d} ({seg.display_mode})..."
            )

            success = False
            if seg.display_mode == "transcript" or (not seg.image_path or not seg.image_path.exists()):
                # Transcript overlay — text on dark background
                success = create_transcript_overlay(
                    seg.transcript_text or f"Segment {seg.segment_idx}",
                    seg.audio_duration,
                    segment_path
                )
            elif seg.image_path and seg.image_path.exists():
                success = create_video_with_ken_burns(
                    seg.image_path,
                    seg.audio_duration,
                    segment_path
                )

            if success:
                video_segments.append(segment_path)

            progress.advance(task)

    console.print(f"\n[{t.success}]Created {len(video_segments)} video segments[/]\n")

    # Create final video
    output_path = Path(output) if output else output_dir / "rough_cut.mp4"
    console.print(f"[{t.label}]Creating final video...[/]")

    if create_final_video(video_segments, audio_combined, output_path):
        duration = get_media_duration(output_path)
        size_mb = output_path.stat().st_size / (1024 * 1024)

        console.print()
        summary = Panel(
            Text.from_markup(
                f"[bold]Assembly Complete[/]\n\n"
                f"Output: [cyan]{output_path}[/]\n"
                f"Duration: [green]{duration:.1f}s ({duration/60:.1f}m)[/]\n"
                f"Size: [yellow]{size_mb:.1f} MB[/]\n"
                f"Segments: {len(video_segments)}"
            ),
            title="Success",
            border_style=t.success
        )
        console.print(summary)
    else:
        raise click.ClickException("Failed to create final video")


@click.command("assemble")
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output video path (default: <run_dir>/assembly/rough_cut.mp4)"
)
@click.option(
    "--skip-existing/--no-skip-existing",
    default=True,
    help="Skip re-rendering existing segments (default: True)"
)
def assemble_cmd(run_dir, output, skip_existing):
    """Assemble rough cut video from a production run.

    RUN_DIR is the path to a video production run directory
    (e.g., artifacts/video_production/20260207_123456).

    This command:
    - Loads the structured script and content library (if available)
    - Creates video segments with Ken Burns effects for images
    - Syncs figure segments to their correct narration timing
    - Outputs a rough cut video with audio

    \b
    Examples:
      claude-studio assemble artifacts/video_production/20260207_123456
      claude-studio assemble ./my_run --output final.mp4
    """
    import asyncio
    asyncio.run(_assemble_async(run_dir, output, skip_existing))
