"""QA inspection CLI - View quality analysis results from production runs"""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

ARTIFACTS_DIR = Path("artifacts")


@click.group()
def qa_cmd():
    """QA (Quality Assurance) inspection

    \b
    View and analyze video quality scores from production runs.

    \b
    Examples:
      claude-studio qa show 20260122_014425
      claude-studio qa show 20260122_014425 --scene scene_1
      claude-studio qa show 20260122_014425 --verbose
    """
    pass


@qa_cmd.command("show")
@click.argument("run_id")
@click.option("--scene", "-s", help="Filter to a specific scene ID")
@click.option("--verbose", "-v", is_flag=True, help="Show frame-by-frame breakdown")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def show_cmd(run_id: str, scene: str, verbose: bool, as_json: bool):
    """Display QA results for a production run."""
    memory_path = ARTIFACTS_DIR / "runs" / run_id / "memory.json"

    if not memory_path.exists():
        console.print(f"[red]Run not found:[/red] {run_id}")
        console.print(f"[dim]Looked at: {memory_path}[/dim]")
        return

    with open(memory_path) as f:
        memory = json.load(f)

    assets = memory.get("assets", [])
    if not assets:
        console.print(f"[yellow]No assets found in run {run_id}[/yellow]")
        return

    # Filter by scene if requested
    if scene:
        assets = [a for a in assets if a.get("scene_id") == scene]
        if not assets:
            console.print(f"[red]Scene '{scene}' not found in run {run_id}[/red]")
            return

    if as_json:
        qa_data = []
        for asset in assets:
            meta = asset.get("metadata", {})
            if meta.get("qa_overall_score") is not None:
                qa_data.append({
                    "scene_id": asset.get("scene_id"),
                    "asset_id": asset.get("asset_id"),
                    "scores": {
                        "overall": meta.get("qa_overall_score"),
                        "visual_accuracy": meta.get("qa_visual_accuracy"),
                        "style_consistency": meta.get("qa_style_consistency"),
                        "technical_quality": meta.get("qa_technical_quality"),
                        "narrative_fit": meta.get("qa_narrative_fit"),
                    },
                    "passed": meta.get("qa_passed"),
                    "issues": meta.get("qa_issues"),
                    "visual_analysis": meta.get("qa_visual_analysis"),
                })
        click.echo(json.dumps(qa_data, indent=2))
        return

    # Header
    concept = memory.get("concept", "")[:80]
    console.print(Panel.fit(
        f"[bold]QA Results: {run_id}[/bold]\n[dim]{concept}...[/dim]",
        border_style="blue"
    ))

    # Summary table
    table = Table(box=box.ROUNDED, title="Scene Scores")
    table.add_column("Scene", style="cyan", width=12)
    table.add_column("Overall", justify="right", width=7)
    table.add_column("Visual", justify="right", width=7)
    table.add_column("Style", justify="right", width=7)
    table.add_column("Tech", justify="right", width=7)
    table.add_column("Narrative", justify="right", width=9)
    table.add_column("Status", justify="center", width=6)

    for asset in assets:
        meta = asset.get("metadata", {})
        if meta.get("qa_overall_score") is None:
            continue

        overall = meta["qa_overall_score"]
        passed = meta.get("qa_passed", False)
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"

        # Color-code scores
        def score_color(s):
            if s >= 85:
                return f"[green]{s:.0f}[/green]"
            elif s >= 70:
                return f"[yellow]{s:.0f}[/yellow]"
            else:
                return f"[red]{s:.0f}[/red]"

        table.add_row(
            asset.get("scene_id", "?"),
            score_color(overall),
            score_color(meta.get("qa_visual_accuracy", 0)),
            score_color(meta.get("qa_style_consistency", 0)),
            score_color(meta.get("qa_technical_quality", 0)),
            score_color(meta.get("qa_narrative_fit", 0)),
            status
        )

    console.print(table)
    console.print()

    # Detailed view (per-scene or verbose)
    show_detail = scene is not None or verbose
    if show_detail:
        for asset in assets:
            meta = asset.get("metadata", {})
            if meta.get("qa_overall_score") is None:
                continue
            _print_scene_detail(asset, meta, verbose)


def _print_scene_detail(asset: dict, meta: dict, verbose: bool):
    """Print detailed QA info for a single scene."""
    scene_id = asset.get("scene_id", "unknown")
    console.print(f"\n[bold cyan]--- {scene_id} ---[/bold cyan]")

    # Issues
    issues = meta.get("qa_issues", [])
    if issues:
        console.print("[bold]Issues:[/bold]")
        for issue in issues:
            console.print(f"  [red]•[/red] {issue}")

    # Suggestions
    suggestions = meta.get("qa_suggestions", [])
    if suggestions:
        console.print("[bold]Suggestions:[/bold]")
        for sug in suggestions:
            console.print(f"  [yellow]→[/yellow] {sug}")

    # Visual analysis (enriched data)
    analysis = meta.get("qa_visual_analysis")
    if analysis:
        console.print()
        console.print(f"[bold]Observed:[/bold] {analysis.get('overall_description', 'N/A')}")
        console.print(f"  Subject: [white]{analysis.get('primary_subject', '?')}[/white]")
        console.print(f"  Setting: [white]{analysis.get('setting', '?')}[/white]")
        console.print(f"  Action:  [white]{analysis.get('action', '?')}[/white]")

        # Element comparison
        matched = analysis.get("matched_elements", [])
        missing = analysis.get("missing_elements", [])
        unexpected = analysis.get("unexpected_elements", [])

        if matched or missing or unexpected:
            console.print()
            console.print("[bold]Element Comparison:[/bold]")
            for el in matched:
                console.print(f"  [green]✓[/green] {el}")
            for el in missing:
                console.print(f"  [red]✗[/red] {el} [dim](missing)[/dim]")
            for el in unexpected:
                console.print(f"  [yellow]?[/yellow] {el} [dim](unexpected)[/dim]")

        # Provider observations
        prov_obs = analysis.get("provider_observations")
        if prov_obs:
            console.print()
            console.print("[bold]Provider:[/bold]")
            if prov_obs.get("prompt_interpretation"):
                console.print(f"  [dim]{prov_obs['prompt_interpretation']}[/dim]")
            for s in prov_obs.get("strengths", []):
                console.print(f"  [green]+[/green] {s}")
            for w in prov_obs.get("weaknesses", []):
                console.print(f"  [red]-[/red] {w}")

        # Frame-by-frame (verbose only)
        if verbose:
            frame_analyses = analysis.get("frame_analyses", [])
            if frame_analyses:
                console.print()
                console.print("[bold]Frame Analysis:[/bold]")
                for fa in frame_analyses:
                    ts = fa.get("timestamp", 0)
                    console.print(f"  [cyan]Frame {fa.get('frame_index', '?')} ({ts:.1f}s):[/cyan]")
                    console.print(f"    {fa.get('description', 'N/A')}")
                    elements = fa.get("detected_elements", [])
                    if elements:
                        console.print(f"    Elements: {', '.join(elements)}")
                    camera = fa.get("detected_camera", "")
                    lighting = fa.get("lighting", "")
                    if camera or lighting:
                        console.print(f"    Camera: {camera}  Lighting: {lighting}")
                    artifacts = fa.get("artifacts_detected", [])
                    if artifacts:
                        console.print(f"    [red]Artifacts: {', '.join(artifacts)}[/red]")

    console.print()
