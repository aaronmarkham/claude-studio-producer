"""Render command - Re-render EDLs from existing runs"""

import os
import json
import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

from core.renderer import FFmpegRenderer
from core.models.edit_decision import EditDecisionList, EditCandidate, EditDecision
from core.models.render import RenderConfig

console = Console()


def load_edl_from_run(run_dir: Path) -> EditDecisionList:
    """Load EDL from a run directory"""
    edl_dir = run_dir / "edl"

    # Load main EDL metadata
    edl_meta_path = edl_dir / "edit_candidates.json"
    if not edl_meta_path.exists():
        raise FileNotFoundError(f"No EDL found at {edl_meta_path}")

    with open(edl_meta_path) as f:
        edl_meta = json.load(f)

    # Load each candidate
    candidates = []
    for cand_info in edl_meta["candidates"]:
        cand_path = edl_dir / f"{cand_info['candidate_id']}.json"
        if cand_path.exists():
            with open(cand_path) as f:
                cand_data = json.load(f)

            # Convert decisions to EditDecision objects
            decisions = []
            for d in cand_data.get("decisions", []):
                decisions.append(EditDecision(
                    scene_id=d["scene_id"],
                    selected_variation=d.get("selected_variation", 0),
                    video_url=d.get("video_url"),
                    audio_url=d.get("audio_url"),
                    in_point=d.get("in_point", 0.0),
                    out_point=d.get("out_point"),
                    transition_in=d.get("transition_in", "cut"),
                    transition_in_duration=d.get("transition_in_duration", 0.0),
                    transition_out=d.get("transition_out", "cut"),
                    transition_out_duration=d.get("transition_out_duration", 0.0),
                    start_time=d.get("start_time", 0.0),
                    duration=d.get("duration", 5.0),
                    # Text overlay fields
                    text_overlay=d.get("text_overlay"),
                    text_position=d.get("text_position", "center"),
                    text_style=d.get("text_style", "title"),
                    text_start_time=d.get("text_start_time"),
                    text_duration=d.get("text_duration"),
                    notes=d.get("notes")
                ))

            candidates.append(EditCandidate(
                candidate_id=cand_data["candidate_id"],
                name=cand_data["name"],
                style=cand_data["style"],
                decisions=decisions,
                total_duration=cand_data.get("total_duration", 0.0),
                estimated_quality=cand_data.get("estimated_quality", 0.0),
                description=cand_data.get("description", "")
            ))

    return EditDecisionList(
        edl_id=edl_meta["edl_id"],
        project_name=edl_meta["project_name"],
        candidates=candidates,
        recommended_candidate_id=edl_meta["recommended_candidate_id"],
        total_scenes=edl_meta["total_scenes"]
    )


@click.command()
@click.argument("run_id")
@click.option("--candidate", "-c", help="Candidate ID to render (default: recommended)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--list-candidates", "-l", is_flag=True, help="List available candidates")
def render_cmd(run_id: str, candidate: str, output: str, list_candidates: bool):
    """
    Render a final video from an existing production run.

    RUN_ID is the run directory name (e.g., 20260107_224324)

    Examples:

        # List available edit candidates
        claude-studio render 20260107_224324 --list-candidates

        # Render the recommended candidate
        claude-studio render 20260107_224324

        # Render a specific candidate
        claude-studio render 20260107_224324 -c creative_cut

        # Render to a specific output file
        claude-studio render 20260107_224324 -o my_video.mp4
    """
    # Find run directory
    run_dir = Path("artifacts/runs") / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        return

    # Load EDL
    try:
        edl = load_edl_from_run(run_dir)
    except Exception as e:
        console.print(f"[red]Failed to load EDL: {e}[/red]")
        return

    # List candidates mode
    if list_candidates:
        console.print(f"\n[bold]Edit Candidates for {run_id}[/bold]\n")
        table = Table(box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Style")
        table.add_column("Duration")
        table.add_column("Quality")
        table.add_column("Recommended")

        for c in edl.candidates:
            is_rec = "*" if c.candidate_id == edl.recommended_candidate_id else ""
            table.add_row(
                c.candidate_id,
                c.name,
                c.style,
                f"{c.total_duration:.1f}s",
                f"{c.estimated_quality:.0f}",
                is_rec
            )

        console.print(table)
        return

    # Select candidate
    candidate_id = candidate or edl.recommended_candidate_id
    console.print(f"[cyan]Rendering candidate: {candidate_id}[/cyan]")

    # Check videos exist
    selected = None
    for c in edl.candidates:
        if c.candidate_id == candidate_id:
            selected = c
            break

    if not selected:
        console.print(f"[red]Candidate '{candidate_id}' not found[/red]")
        console.print(f"Available: {[c.candidate_id for c in edl.candidates]}")
        return

    # Show what videos we'll use
    console.print(f"\n[bold]Videos in edit:[/bold]")
    all_exist = True
    for d in selected.decisions:
        video_path = d.video_url
        if video_path:
            # Make path absolute if relative
            if not os.path.isabs(video_path):
                video_path = os.path.abspath(video_path)

            exists = os.path.exists(video_path)
            status = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
            console.print(f"  {status} {d.scene_id}: {video_path}")
            if not exists:
                all_exist = False
        else:
            console.print(f"  [yellow]?[/yellow] {d.scene_id}: No video URL")
            all_exist = False

    if not all_exist:
        console.print("\n[yellow]Warning: Some videos are missing[/yellow]")

    # Render
    console.print("\n[bold]Rendering...[/bold]")

    try:
        result = asyncio.run(_render_edl(
            edl=edl,
            candidate_id=candidate_id,
            run_dir=run_dir,
            output_path=output
        ))

        if result.success:
            console.print(f"\n[green]Render complete![/green]")
            console.print(f"  Output: {result.output_path}")
            if result.duration:
                console.print(f"  Duration: {result.duration:.1f}s")
            if result.file_size:
                size_mb = result.file_size / (1024 * 1024)
                console.print(f"  Size: {size_mb:.1f} MB")
            console.print(f"  Render time: {result.render_time:.1f}s")
        else:
            console.print(f"\n[red]Render failed: {result.error_message}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


async def _render_edl(
    edl: EditDecisionList,
    candidate_id: str,
    run_dir: Path,
    output_path: str = None
) -> 'RenderResult':
    """Render the EDL"""
    from core.models.render import RenderResult

    # Setup renderer
    render_dir = run_dir / "renders"
    render_dir.mkdir(exist_ok=True)

    renderer = FFmpegRenderer(output_dir=str(render_dir))

    # Check FFmpeg
    ffmpeg_check = await renderer.check_ffmpeg_installed()
    if not ffmpeg_check["installed"]:
        return RenderResult(
            success=False,
            error_message="FFmpeg not installed"
        )

    # Render
    result = await renderer.render(
        edl=edl,
        candidate_id=candidate_id,
        audio_tracks=[],
        run_id=run_dir.name
    )

    # Copy to custom output path if specified
    if output_path and result.success and result.output_path:
        import shutil
        shutil.copy(result.output_path, output_path)
        result.output_path = output_path

    return result
