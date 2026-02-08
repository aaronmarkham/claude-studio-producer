"""
Asset tracking CLI - Review, approve, and manage production assets.

Phase 6 of Unified Production Architecture: Asset tracking and approval workflow.

This provides CLI commands for:
- Listing assets with status filtering
- Approving/rejecting individual assets
- Building final video from approved assets only
- Importing assets from previous runs
"""

import json
import sys
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from cli.theme import get_theme
from core.models.content_library import (
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.content_librarian import ContentLibrarian

console = Console()


def find_library(run_dir: Path) -> Optional[ContentLibrary]:
    """Find and load content library from a run directory."""
    # Try content_library.json first (new format)
    lib_path = run_dir / "content_library.json"
    if lib_path.exists():
        try:
            return ContentLibrary.load(lib_path)
        except Exception:
            pass

    # Try asset_manifest.json (legacy format) and migrate
    manifest_path = run_dir / "asset_manifest.json"
    if manifest_path.exists():
        try:
            return ContentLibrary.from_asset_manifest_v1(str(manifest_path))
        except Exception:
            pass

    return None


def save_library(library: ContentLibrary, run_dir: Path) -> Path:
    """Save content library to run directory."""
    lib_path = run_dir / "content_library.json"
    library.save(lib_path)
    return lib_path


def parse_segment_range(spec: str) -> List[int]:
    """Parse segment specification like '1,3,5' or '1-10' or 'all'."""
    if spec.lower() == "all":
        return []  # Empty list means all

    segments = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-")
            segments.extend(range(int(start), int(end) + 1))
        else:
            segments.append(int(part))
    return segments


@click.group("assets")
def assets():
    """Asset tracking and approval commands.

    \b
    Workflow:
      1. Generate assets with produce-video
      2. List and review: assets list <run_dir>
      3. Approve good ones: assets approve <run_dir> --audio all
      4. Reject bad ones: assets reject <run_dir> --image 3 --reason "wrong style"
      5. Build final: assets build <run_dir>
    """
    pass


@assets.command("list")
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--status", "-s",
    type=click.Choice(["all", "draft", "review", "approved", "rejected"]),
    default="all",
    help="Filter by status"
)
@click.option(
    "--type", "-t", "asset_type",
    type=click.Choice(["all", "audio", "image", "figure", "video"]),
    default="all",
    help="Filter by asset type"
)
@click.option(
    "--segment", "-g",
    type=str,
    default=None,
    help="Filter by segment (e.g., '1-10' or '5,6,7')"
)
def list_assets(run_dir, status, asset_type, segment):
    """List assets in a production run with optional filtering.

    \b
    Examples:
      claude-studio assets list ./my_run
      claude-studio assets list ./my_run --status review
      claude-studio assets list ./my_run --type audio --status approved
      claude-studio assets list ./my_run --segment 1-10
    """
    t = get_theme()
    run_path = Path(run_dir)

    library = find_library(run_path)
    if not library:
        raise click.ClickException(f"No content library found in {run_dir}")

    # Build filter criteria
    type_filter = None if asset_type == "all" else AssetType(asset_type)
    status_filter = None if status == "all" else AssetStatus(status)
    segment_filter = parse_segment_range(segment) if segment else None

    # Query assets
    assets = library.query(
        asset_type=type_filter,
        status=status_filter,
    )

    # Apply segment filter
    if segment_filter:
        assets = [a for a in assets if a.segment_idx in segment_filter]

    if not assets:
        console.print(f"[{t.dimmed}]No assets found matching criteria[/]")
        return

    # Group by type for display
    by_type = {}
    for asset in assets:
        type_name = asset.asset_type.value
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(asset)

    # Print summary
    console.print(Panel(
        f"[bold]Assets in {run_path.name}[/]\n"
        f"Total: {len(assets)} | "
        f"Filter: status={status}, type={asset_type}",
        border_style=t.panel_border,
    ))
    console.print()

    for type_name, type_assets in sorted(by_type.items()):
        table = Table(
            title=f"{type_name.upper()} Assets ({len(type_assets)})",
            box=box.ROUNDED,
            border_style=t.panel_border,
        )
        table.add_column("ID", style=t.dimmed, width=20)
        table.add_column("Segment", justify="right", width=8)
        table.add_column("Status", width=10)
        table.add_column("Path", width=40)

        for asset in sorted(type_assets, key=lambda a: a.segment_idx or 0):
            status_style = {
                AssetStatus.DRAFT: "yellow",
                AssetStatus.REVIEW: "cyan",
                AssetStatus.APPROVED: "green",
                AssetStatus.REJECTED: "red",
                AssetStatus.REVISED: "magenta",
            }.get(asset.status, "white")

            seg_str = str(asset.segment_idx) if asset.segment_idx is not None else "-"
            path_str = Path(asset.path).name if asset.path else "-"

            table.add_row(
                asset.asset_id[:20],
                seg_str,
                f"[{status_style}]{asset.status.value}[/]",
                path_str,
            )

        console.print(table)
        console.print()

    # Print status summary
    status_counts = {}
    for asset in assets:
        status_counts[asset.status.value] = status_counts.get(asset.status.value, 0) + 1

    summary_parts = [f"{s}: {c}" for s, c in sorted(status_counts.items())]
    console.print(f"[{t.dimmed}]Status breakdown: {', '.join(summary_parts)}[/]")


@assets.command("approve")
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--audio", "-a",
    type=str,
    default=None,
    help="Audio segments to approve (e.g., '1-10', 'all')"
)
@click.option(
    "--image", "-i",
    type=str,
    default=None,
    help="Image segments to approve (e.g., '1,3,5', 'all')"
)
@click.option(
    "--segment", "-g",
    type=str,
    default=None,
    help="Approve all asset types for these segments"
)
def approve_assets(run_dir, audio, image, segment):
    """Approve assets for final build.

    \b
    Examples:
      claude-studio assets approve ./my_run --audio all
      claude-studio assets approve ./my_run --image 1,3,5
      claude-studio assets approve ./my_run --segment 1-10
    """
    t = get_theme()
    run_path = Path(run_dir)

    library = find_library(run_path)
    if not library:
        raise click.ClickException(f"No content library found in {run_dir}")

    approved_count = 0

    # Approve audio
    if audio:
        segments = parse_segment_range(audio)
        audio_assets = library.query(asset_type=AssetType.AUDIO)
        for asset in audio_assets:
            if not segments or asset.segment_idx in segments:
                asset.status = AssetStatus.APPROVED
                approved_count += 1

    # Approve images
    if image:
        segments = parse_segment_range(image)
        image_assets = library.query(asset_type=AssetType.IMAGE)
        for asset in image_assets:
            if not segments or asset.segment_idx in segments:
                asset.status = AssetStatus.APPROVED
                approved_count += 1

    # Approve by segment (all types)
    if segment:
        segments = parse_segment_range(segment)
        for asset_id, asset in library.assets.items():
            if not segments or asset.segment_idx in segments:
                asset.status = AssetStatus.APPROVED
                approved_count += 1

    if approved_count > 0:
        save_library(library, run_path)
        console.print(f"[{t.success}]Approved {approved_count} assets[/]")
    else:
        console.print(f"[{t.warning}]No assets matched the criteria[/]")


@assets.command("reject")
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--audio", "-a",
    type=str,
    default=None,
    help="Audio segments to reject"
)
@click.option(
    "--image", "-i",
    type=str,
    default=None,
    help="Image segments to reject"
)
@click.option(
    "--reason", "-r",
    type=str,
    default=None,
    help="Reason for rejection"
)
def reject_assets(run_dir, audio, image, reason):
    """Reject assets that need regeneration.

    \b
    Examples:
      claude-studio assets reject ./my_run --image 3 --reason "wrong style"
      claude-studio assets reject ./my_run --audio 5-10 --reason "voice too fast"
    """
    t = get_theme()
    run_path = Path(run_dir)

    library = find_library(run_path)
    if not library:
        raise click.ClickException(f"No content library found in {run_dir}")

    rejected_count = 0

    # Reject audio
    if audio:
        segments = parse_segment_range(audio)
        audio_assets = library.query(asset_type=AssetType.AUDIO)
        for asset in audio_assets:
            if not segments or asset.segment_idx in segments:
                asset.status = AssetStatus.REJECTED
                if reason:
                    asset.rejected_reason = reason
                rejected_count += 1

    # Reject images
    if image:
        segments = parse_segment_range(image)
        image_assets = library.query(asset_type=AssetType.IMAGE)
        for asset in image_assets:
            if not segments or asset.segment_idx in segments:
                asset.status = AssetStatus.REJECTED
                if reason:
                    asset.rejected_reason = reason
                rejected_count += 1

    if rejected_count > 0:
        save_library(library, run_path)
        console.print(f"[{t.warning}]Rejected {rejected_count} assets[/]")
        if reason:
            console.print(f"[{t.dimmed}]Reason: {reason}[/]")
    else:
        console.print(f"[{t.dimmed}]No assets matched the criteria[/]")


@assets.command("build")
@click.argument("run_dir", type=click.Path(exists=True))
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output video path"
)
@click.option(
    "--only", "only_status",
    type=click.Choice(["approved", "all"]),
    default="approved",
    help="Build from approved assets only (default) or all"
)
@click.option(
    "--skip-rejected/--include-rejected",
    default=True,
    help="Skip rejected assets when building"
)
def build_assets(run_dir, output, only_status, skip_rejected):
    """Build final video from approved assets.

    \b
    Examples:
      claude-studio assets build ./my_run
      claude-studio assets build ./my_run --only all
      claude-studio assets build ./my_run --output final.mp4
    """
    t = get_theme()
    run_path = Path(run_dir)

    library = find_library(run_path)
    if not library:
        raise click.ClickException(f"No content library found in {run_dir}")

    # Count assets by status
    approved = library.query(status=AssetStatus.APPROVED)
    rejected = library.query(status=AssetStatus.REJECTED)
    total = len(library.assets)

    console.print(Panel(
        f"[bold]Build Plan[/]\n"
        f"Total assets: {total}\n"
        f"Approved: [green]{len(approved)}[/]\n"
        f"Rejected: [red]{len(rejected)}[/]\n"
        f"Other: {total - len(approved) - len(rejected)}",
        border_style=t.panel_border,
    ))

    if only_status == "approved" and len(approved) == 0:
        raise click.ClickException("No approved assets to build from")

    # Get assets to use
    if only_status == "approved":
        assets_to_use = approved
    else:
        if skip_rejected:
            assets_to_use = [a for a in library.assets.values() if a.status != AssetStatus.REJECTED]
        else:
            assets_to_use = list(library.assets.values())

    console.print(f"\n[{t.label}]Building with {len(assets_to_use)} assets...[/]")

    # For now, just call the assemble command
    # In a full implementation, this would integrate with the assembly logic
    output_path = output or (run_path / "final" / "output.mp4")
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[{t.dimmed}]Run 'claude-studio assemble {run_dir}' to create the video[/]")
    console.print(f"[{t.success}]Build plan ready. Output will be: {output_path}[/]")


@assets.command("import")
@click.argument("source_run", type=click.Path(exists=True))
@click.argument("target_run", type=click.Path(exists=True))
@click.option(
    "--status", "-s",
    type=click.Choice(["approved", "all"]),
    default="approved",
    help="Import only approved assets (default) or all"
)
@click.option(
    "--type", "-t", "asset_type",
    type=click.Choice(["audio", "image", "all"]),
    default="all",
    help="Import specific asset type"
)
def import_assets(source_run, target_run, status, asset_type):
    """Import approved assets from another run.

    Useful for reusing approved audio when regenerating images.

    \b
    Examples:
      claude-studio assets import ./old_run ./new_run --status approved
      claude-studio assets import ./old_run ./new_run --type audio
    """
    t = get_theme()
    source_path = Path(source_run)
    target_path = Path(target_run)

    source_lib = find_library(source_path)
    if not source_lib:
        raise click.ClickException(f"No content library in source: {source_run}")

    target_lib = find_library(target_path)
    if not target_lib:
        # Create new library for target
        target_lib = ContentLibrary(project_id=target_path.name)

    # Filter source assets
    type_filter = None if asset_type == "all" else AssetType(asset_type)
    status_filter = AssetStatus.APPROVED if status == "approved" else None

    source_assets = source_lib.query(
        asset_type=type_filter,
        status=status_filter,
    )

    imported_count = 0
    for asset in source_assets:
        # Check if already exists in target
        existing = target_lib.query(
            asset_type=asset.asset_type,
            segment_idx=asset.segment_idx,
        )
        if not existing:
            # Import with new ID
            new_id = target_lib.register(asset)
            imported_count += 1

    if imported_count > 0:
        save_library(target_lib, target_path)
        console.print(f"[{t.success}]Imported {imported_count} assets from {source_path.name}[/]")
    else:
        console.print(f"[{t.dimmed}]No new assets to import[/]")


@assets.command("summary")
@click.argument("run_dir", type=click.Path(exists=True))
def summary_assets(run_dir):
    """Show summary of asset status in a production run.

    \b
    Example:
      claude-studio assets summary ./my_run
    """
    t = get_theme()
    run_path = Path(run_dir)

    library = find_library(run_path)
    if not library:
        raise click.ClickException(f"No content library found in {run_dir}")

    summary = library.get_summary()

    console.print(Panel(
        f"[bold]Asset Summary: {run_path.name}[/]",
        border_style=t.panel_border,
    ))
    console.print()

    # Type counts
    table = Table(box=box.SIMPLE)
    table.add_column("Asset Type", style=t.label)
    table.add_column("Count", justify="right")

    for type_name, count in sorted(summary.get("by_type", {}).items()):
        table.add_row(type_name, str(count))
    table.add_row("[bold]Total[/]", f"[bold]{summary.get('total', 0)}[/]")

    console.print(table)
    console.print()

    # Status breakdown
    status_table = Table(box=box.SIMPLE)
    status_table.add_column("Status", style=t.label)
    status_table.add_column("Count", justify="right")

    status_styles = {
        "draft": "yellow",
        "review": "cyan",
        "approved": "green",
        "rejected": "red",
        "revised": "magenta",
    }

    for status_name, count in sorted(summary.get("by_status", {}).items()):
        style = status_styles.get(status_name, "white")
        status_table.add_row(f"[{style}]{status_name}[/]", str(count))

    console.print(status_table)
