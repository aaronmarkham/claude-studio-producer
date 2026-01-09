"""Combine command - Create custom video sequences from specific scenes"""

import os
import subprocess
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

# Try to find ffmpeg - check common locations on Windows
FFMPEG_PATHS = [
    "ffmpeg",  # System PATH
    r"C:\Users\aaron\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]


def find_ffmpeg() -> str:
    """Find ffmpeg executable"""
    for path in FFMPEG_PATHS:
        try:
            result = subprocess.run(
                [path, "-version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return path
        except (subprocess.SubprocessError, FileNotFoundError):
            continue

    raise FileNotFoundError(
        "ffmpeg not found. Please install ffmpeg and ensure it's in your PATH, "
        "or install via: winget install Gyan.FFmpeg"
    )


def list_scenes(run_dir: Path) -> list:
    """List available video scenes in a run"""
    videos_dir = run_dir / "videos"
    if not videos_dir.exists():
        return []

    scenes = []
    for video in sorted(videos_dir.glob("scene_*.mp4")):
        # Parse scene number from filename (e.g., scene_1_v0.mp4)
        name = video.stem
        parts = name.split("_")
        if len(parts) >= 2:
            try:
                scene_num = int(parts[1])
                scenes.append({
                    "number": scene_num,
                    "filename": video.name,
                    "path": video,
                    "size": video.stat().st_size
                })
            except ValueError:
                continue

    return sorted(scenes, key=lambda x: x["number"])


@click.command()
@click.argument("run_id")
@click.option("--scenes", "-s", help="Comma-separated scene numbers to combine (e.g., '1,3,4')")
@click.option("--output", "-o", help="Output filename (default: scenes_X_Y_combined.mp4)")
@click.option("--list", "-l", "list_only", is_flag=True, help="List available scenes")
def combine_cmd(run_id: str, scenes: str, output: str, list_only: bool):
    """
    Combine specific scenes from a production run into a custom sequence.

    RUN_ID is the run directory name (e.g., 20260109_080534)

    Examples:

        # List available scenes
        python -m cli.combine 20260109_080534 --list

        # Combine scenes 1 and 3 (skipping scene 2)
        python -m cli.combine 20260109_080534 --scenes 1,3

        # Combine with custom output name
        python -m cli.combine 20260109_080534 --scenes 1,3,5 -o highlight_reel.mp4
    """
    # Find run directory
    run_dir = Path("artifacts/runs") / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        return

    # Get available scenes
    available_scenes = list_scenes(run_dir)
    if not available_scenes:
        console.print(f"[red]No video scenes found in {run_dir / 'videos'}[/red]")
        return

    # List mode
    if list_only:
        console.print(f"\n[bold]Available Scenes in {run_id}[/bold]\n")
        table = Table(box=box.ROUNDED)
        table.add_column("Scene #", style="cyan", justify="right")
        table.add_column("Filename")
        table.add_column("Size", justify="right")

        for scene in available_scenes:
            size_kb = scene["size"] / 1024
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            table.add_row(
                str(scene["number"]),
                scene["filename"],
                size_str
            )

        console.print(table)
        console.print(f"\n[dim]Use --scenes 1,3,4 to combine specific scenes[/dim]")
        return

    # Require scenes for combine mode
    if not scenes:
        console.print("[red]Please specify scenes to combine with --scenes (e.g., --scenes 1,3)[/red]")
        console.print("[dim]Use --list to see available scenes[/dim]")
        return

    # Parse scene numbers
    try:
        scene_nums = [int(s.strip()) for s in scenes.split(",")]
    except ValueError:
        console.print("[red]Invalid scene format. Use comma-separated numbers (e.g., 1,3,4)[/red]")
        return

    if len(scene_nums) < 2:
        console.print("[red]Please specify at least 2 scenes to combine[/red]")
        return

    # Map scene numbers to files
    scene_map = {s["number"]: s for s in available_scenes}
    missing = [n for n in scene_nums if n not in scene_map]
    if missing:
        console.print(f"[red]Scene(s) not found: {missing}[/red]")
        console.print(f"[dim]Available: {[s['number'] for s in available_scenes]}[/dim]")
        return

    selected_scenes = [scene_map[n] for n in scene_nums]

    # Find ffmpeg
    try:
        ffmpeg = find_ffmpeg()
        console.print(f"[dim]Using ffmpeg: {ffmpeg}[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    # Determine output path
    renders_dir = run_dir / "renders"
    renders_dir.mkdir(exist_ok=True)

    if output:
        if not output.endswith(".mp4"):
            output += ".mp4"
        output_path = renders_dir / output
    else:
        scene_str = "_".join(str(n) for n in scene_nums)
        output_path = renders_dir / f"scenes_{scene_str}_combined.mp4"

    # Show what we're combining
    console.print(f"\n[bold]Combining {len(selected_scenes)} scenes:[/bold]")
    for i, scene in enumerate(selected_scenes, 1):
        console.print(f"  {i}. Scene {scene['number']}: {scene['filename']}")

    # Create concat file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as concat_file:
        for scene in selected_scenes:
            # Use absolute paths
            abs_path = scene["path"].absolute()
            concat_file.write(f"file '{abs_path}'\n")
        concat_path = concat_file.name

    try:
        # Run ffmpeg concat
        console.print(f"\n[cyan]Combining videos...[/cyan]")

        cmd = [
            ffmpeg,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-c", "copy",
            "-y",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print(f"[red]ffmpeg failed:[/red]")
            console.print(result.stderr[:500])
            return

        # Success
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            console.print(f"\n[green]✓ Combined video created![/green]")
            console.print(f"  Output: {output_path}")
            console.print(f"  Size: {size_mb:.1f} MB")
        else:
            console.print("[red]Output file not created[/red]")

    finally:
        # Clean up concat file
        if os.path.exists(concat_path):
            os.unlink(concat_path)


if __name__ == "__main__":
    combine_cmd()
