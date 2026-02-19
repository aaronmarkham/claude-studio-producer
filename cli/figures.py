"""Figure management for video production runs.

Inject, list, and remove custom figures (diagrams, charts, etc.)
into a production run's content library and structured script.
"""

import shutil
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from core.models.content_library import (
    AssetRecord,
    AssetSource,
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import StructuredScript

console = Console()


def _load_run(run_dir: Path):
    """Load structured script and content library from a run directory."""
    script_files = list(run_dir.glob("*_structured_script.json"))
    if not script_files:
        raise click.ClickException(f"No structured script found in {run_dir}")

    library_path = run_dir / "content_library.json"
    if not library_path.exists():
        raise click.ClickException(f"No content_library.json found in {run_dir}")

    try:
        script = StructuredScript.load(script_files[0])
    except Exception as e:
        raise click.ClickException(f"Failed to load structured script: {e}")

    try:
        library = ContentLibrary.load(library_path)
    except Exception as e:
        raise click.ClickException(f"Failed to load content library: {e}")

    return script, script_files[0], library, library_path


@click.group()
def figures():
    """Manage figures in a video production run.

    Inject custom diagrams/images, list current figure assignments,
    or remove figures from segments.

    Examples:
        cs figures inject <run_dir> 3 diagram.png
        cs figures list <run_dir>
        cs figures remove <run_dir> 3
    """
    pass


@figures.command()
@click.argument("run_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("segment", type=int)
@click.argument("image_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--description", "-d", default=None,
    help="Description of the figure (auto-generated if omitted)",
)
@click.option(
    "--display-mode", "-m",
    type=click.Choice(["figure_sync", "web_image", "dall_e"]),
    default="figure_sync",
    help="Display mode (default: figure_sync = static hold, no Ken Burns)",
)
def inject(
    run_dir: Path,
    segment: int,
    image_path: Path,
    description: Optional[str],
    display_mode: str,
):
    """Inject a figure into a specific segment.

    Copies the image into the run's images directory, registers it
    in the content library, and updates the structured script.

    SEGMENT is the 0-based segment index.

    Examples:
        cs figures inject ./artifacts/video_production/20260218_012411 3 boundary.png
        cs figures inject ./run 7 multi_agent.png -d "Multi-agent adjudication"
    """
    script, script_path, library, library_path = _load_run(run_dir)

    # Validate segment index
    seg = script.get_segment(segment)
    if not seg:
        raise click.ClickException(
            f"Segment {segment} not found. Script has {len(script.segments)} segments (0-{len(script.segments)-1})."
        )

    # Copy image to run's images directory
    images_dir = run_dir / "images"
    images_dir.mkdir(exist_ok=True)
    dest_filename = f"scene_{segment:03d}{image_path.suffix}"
    dest_path = images_dir / dest_filename
    shutil.copy2(image_path, dest_path)

    # Register in content library
    desc = description or f"Figure for segment {segment}: {seg.text[:60]}..."
    asset_id = f"fig_{segment:03d}"

    # Remove old asset if exists
    if library.get(asset_id):
        del library.assets[asset_id]

    record = AssetRecord(
        asset_id=asset_id,
        asset_type=AssetType.FIGURE,
        source=AssetSource.MANUAL,
        status=AssetStatus.APPROVED,
        segment_idx=segment,
        describes=desc,
        path=str(dest_path),
        format=image_path.suffix.lstrip("."),
    )
    library.register(record)
    library.save(library_path)

    # Update structured script
    script.update_segment(
        segment,
        display_mode=display_mode,
        visual_asset_id=asset_id,
        image_path=str(dest_path),
    )
    script.save(script_path)

    console.print(f"[green]✓[/] Injected [bold]{image_path.name}[/] into segment {segment}")
    console.print(f"  Asset ID: {asset_id}")
    console.print(f"  Display mode: {display_mode}")
    console.print(f"  Copied to: {dest_path}")


@figures.command("list")
@click.argument("run_dir", type=click.Path(exists=True, path_type=Path))
def list_figures(run_dir: Path):
    """List all figure assignments in a production run.

    Shows which segments have figures, their display modes,
    and image paths.
    """
    script, _, library, _ = _load_run(run_dir)

    table = Table(title="Figure Assignments")
    table.add_column("Seg", style="cyan", width=4)
    table.add_column("Display Mode", width=14)
    table.add_column("Asset ID", width=10)
    table.add_column("Image", style="dim")
    table.add_column("Text Preview", width=40, no_wrap=True)

    for seg in script.segments:
        has_figure = seg.display_mode in ("figure_sync", "dall_e", "web_image")
        asset_id = getattr(seg, "visual_asset_id", None) or ""
        image_path = getattr(seg, "image_path", None) or ""
        if image_path:
            image_path = Path(image_path).name

        style = "bold green" if has_figure else "dim"
        table.add_row(
            str(seg.idx),
            seg.display_mode or "—",
            asset_id,
            image_path,
            seg.text[:40] + "..." if len(seg.text) > 40 else seg.text,
            style=style,
        )

    console.print(table)


@figures.command()
@click.argument("run_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("segment", type=int)
def remove(run_dir: Path, segment: int):
    """Remove a figure from a segment, reverting to carry_forward.

    Does not delete the image file — just unlinks it from the
    content library and structured script.
    """
    script, script_path, library, library_path = _load_run(run_dir)

    seg = script.get_segment(segment)
    if not seg:
        raise click.ClickException(f"Segment {segment} not found.")

    # Remove from content library
    asset_id = f"fig_{segment:03d}"
    if library.get(asset_id):
        del library.assets[asset_id]
        library.save(library_path)

    # Reset structured script
    script.update_segment(
        segment,
        display_mode="carry_forward",
        visual_asset_id=None,
        image_path=None,
    )
    script.save(script_path)

    console.print(f"[yellow]✓[/] Removed figure from segment {segment} (reverted to carry_forward)")
