#!/usr/bin/env python3
"""
Assemble rough cut video from audio clips and images.

Audio clips are the primary timing source (45 clips from the generated script).
Images (27) are distributed evenly across the audio timeline.
Each image displays for (total_duration / num_images) seconds.
"""

import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple
import tempfile
import os


@dataclass
class AudioClip:
    path: Path
    duration: float  # seconds
    index: int
    start_time: float = 0.0  # cumulative start in final video


@dataclass
class ImageAsset:
    path: Path
    scene_id: str
    index: int


def get_media_duration(path: Path) -> float:
    """Get duration of audio/video file using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path)
        ],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def discover_assets(audio_dir: Path, image_dir: Path) -> Tuple[List[AudioClip], List[ImageAsset]]:
    """Discover available audio and image assets."""
    # Find audio clips
    audio_clips = []
    cumulative_time = 0.0
    for audio_file in sorted(audio_dir.glob("audio_*.mp3")):
        idx = int(audio_file.stem.split("_")[1])
        duration = get_media_duration(audio_file)
        audio_clips.append(AudioClip(
            path=audio_file,
            duration=duration,
            index=idx,
            start_time=cumulative_time
        ))
        cumulative_time += duration

    # Find images (sorted by scene number)
    images = []
    for img_file in sorted(image_dir.glob("scene_*.png")):
        idx = int(img_file.stem.split("_")[1])
        images.append(ImageAsset(path=img_file, scene_id=img_file.stem, index=idx))

    # Sort images by scene index
    images.sort(key=lambda x: x.index)

    return audio_clips, images


def create_image_timeline(total_duration: float, images: List[ImageAsset]) -> List[Tuple[float, float, ImageAsset]]:
    """
    Create timeline mapping showing which image displays when.

    Each image gets equal screen time.
    Returns list of (start_time, end_time, image) tuples.
    """
    if not images:
        return []

    time_per_image = total_duration / len(images)

    timeline = []
    for i, img in enumerate(images):
        start = i * time_per_image
        end = (i + 1) * time_per_image
        timeline.append((start, end, img))

    return timeline


def create_video_with_ken_burns(image_path: Path, duration: float, output_path: Path) -> bool:
    """Create a video from a static image with Ken Burns effect."""
    fps = 30
    total_frames = int(duration * fps)

    # zoompan: slow zoom from 1.0 to 1.1, centered
    filter_complex = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
        f"zoompan=z='min(zoom+0.0003,1.1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
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

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FFmpeg error: {result.stderr[:200]}")
    return result.returncode == 0


def concatenate_audio(audio_clips: List[AudioClip], output_path: Path) -> bool:
    """Concatenate all audio clips into a single file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for clip in audio_clips:
            # Use forward slashes and escape for ffmpeg concat
            path_str = str(clip.path).replace('\\', '/')
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
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Audio concat error: {result.stderr[:200]}")
        return result.returncode == 0
    finally:
        os.unlink(concat_file)


def create_final_video(video_segments: List[Path], audio_path: Path, output_path: Path) -> bool:
    """Concatenate video segments and add audio track."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for seg in video_segments:
            path_str = str(seg).replace('\\', '/')
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
            "-shortest",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Final video error: {result.stderr[:200]}")
        return result.returncode == 0
    finally:
        os.unlink(concat_file)


def main():
    # Paths
    base_dir = Path("c:/Users/aaron/Documents/GitHub/claude-studio-producer")
    audio_dir = base_dir / "artifacts/video_production/20260207_101747/audio"
    image_dir = base_dir / "artifacts/video_production/20260207_104648/images"
    output_dir = base_dir / "artifacts/video_production/rough_cut"

    output_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = output_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    print("=" * 50)
    print("  ROUGH CUT ASSEMBLY")
    print("=" * 50)

    # 1. Discover assets
    print("\n[1/5] Discovering assets...")
    audio_clips, images = discover_assets(audio_dir, image_dir)
    print(f"      Audio clips: {len(audio_clips)}")
    print(f"      Images: {len(images)}")

    total_audio_duration = sum(a.duration for a in audio_clips)
    print(f"      Total audio: {total_audio_duration:.1f}s ({total_audio_duration/60:.1f} min)")

    # 2. Create image timeline
    print("\n[2/5] Creating image timeline...")
    timeline = create_image_timeline(total_audio_duration, images)
    time_per_image = total_audio_duration / len(images)
    print(f"      Each image: ~{time_per_image:.1f}s")

    # 3. Concatenate audio first
    print("\n[3/5] Concatenating audio...")
    audio_combined = output_dir / "audio_combined.mp3"
    if not concatenate_audio(audio_clips, audio_combined):
        print("      ERROR: Failed to concatenate audio")
        return
    print(f"      Created: {audio_combined.name}")

    # 4. Create video segments
    print(f"\n[4/5] Creating {len(timeline)} video segments with Ken Burns...")
    video_segments = []

    for i, (start, end, img) in enumerate(timeline):
        duration = end - start
        segment_path = segments_dir / f"segment_{i:03d}.mp4"
        status = f"      [{i+1:2d}/{len(timeline)}] {img.scene_id} ({duration:.1f}s)..."
        print(status, end=" ", flush=True)

        if create_video_with_ken_burns(img.path, duration, segment_path):
            video_segments.append(segment_path)
            print("OK")
        else:
            print("FAILED")

    # 5. Create final video
    print(f"\n[5/5] Creating final video...")
    output_path = output_dir / "rough_cut.mp4"

    if create_final_video(video_segments, audio_combined, output_path):
        print("\n" + "=" * 50)
        print("  SUCCESS!")
        print("=" * 50)
        print(f"\n  Output: {output_path}")

        # Get final video info
        duration = get_media_duration(output_path)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  Duration: {duration:.1f}s ({duration/60:.1f} min)")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print("\n  ERROR: Failed to create final video")


if __name__ == "__main__":
    main()
