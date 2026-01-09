"""Luma API management commands"""

import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def get_luma_provider():
    """Get configured Luma provider"""
    api_key = os.getenv("LUMA_API_KEY")
    if not api_key:
        console.print("[red]Error: LUMA_API_KEY environment variable not set[/red]")
        raise SystemExit(1)

    from core.providers.video.luma import LumaProvider
    from core.providers.base import VideoProviderConfig, ProviderType

    config = VideoProviderConfig(
        provider_type=ProviderType.LUMA,
        api_key=api_key,
        timeout=600
    )
    return LumaProvider(config=config)


@click.group()
def luma_cmd():
    """Luma AI API management commands

    \b
    Commands:
      list      List all Luma generations
      status    Show details for a specific generation
      download  Download a completed generation
      recover   Download all completed but unfetched generations
    """
    pass


@luma_cmd.command("list")
@click.option("--limit", "-n", type=int, default=50, help="Number of generations to list")
@click.option("--state", "-s", type=click.Choice(["all", "completed", "failed", "pending"]),
              default="all", help="Filter by state")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_generations(limit: int, state: str, as_json: bool):
    """List all Luma generations

    Shows recent generations from your Luma account with their status,
    creation time, and prompt preview.

    \b
    Examples:
      claude-studio luma list
      claude-studio luma list -n 100 -s completed
      claude-studio luma list --json
    """
    provider = get_luma_provider()

    async def _list():
        return await provider.list_generations(limit=limit)

    generations = asyncio.run(_list())

    # Filter by state if specified
    if state != "all":
        state_map = {
            "completed": "completed",
            "failed": "failed",
            "pending": ["queued", "dreaming", "pending"]
        }
        if state == "pending":
            generations = [g for g in generations if g["state"] in state_map["pending"]]
        else:
            generations = [g for g in generations if g["state"] == state_map[state]]

    if as_json:
        import json
        click.echo(json.dumps(generations, indent=2, default=str))
        return

    if not generations:
        console.print("[dim]No generations found[/dim]")
        return

    # Build table
    table = Table(title=f"Luma Generations ({len(generations)} shown)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("State", style="bold")
    table.add_column("Created", style="dim")
    table.add_column("Prompt", max_width=40)

    # Count by state
    state_counts = {}
    for g in generations:
        s = g["state"]
        state_counts[s] = state_counts.get(s, 0) + 1

    for g in generations:
        # Format state with color
        state_val = g["state"]
        if state_val == "completed":
            state_display = "[green]completed[/green]"
        elif state_val == "failed":
            state_display = f"[red]failed[/red]"
        elif state_val in ["queued", "pending"]:
            state_display = f"[yellow]{state_val}[/yellow]"
        elif state_val == "dreaming":
            state_display = f"[blue]dreaming[/blue]"
        else:
            state_display = state_val

        # Format created time
        created = g.get("created_at", "")
        if created:
            try:
                if isinstance(created, str):
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                else:
                    dt = created
                created = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                created = str(created)[:16]

        # Format prompt
        prompt = g.get("prompt", "N/A")
        if len(prompt) > 40:
            prompt = prompt[:37] + "..."

        table.add_row(g["id"], state_display, created, prompt)

    console.print(table)

    # Summary
    summary_parts = [f"[bold]{s}[/bold]: {c}" for s, c in sorted(state_counts.items())]
    console.print(f"\nSummary: {', '.join(summary_parts)}")


@luma_cmd.command("status")
@click.argument("generation_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_status(generation_id: str, as_json: bool):
    """Show details for a specific generation

    \b
    Examples:
      claude-studio luma status abc123-def456
    """
    provider = get_luma_provider()

    async def _status():
        return await provider.check_status(generation_id)

    status = asyncio.run(_status())

    if as_json:
        import json
        click.echo(json.dumps(status, indent=2, default=str))
        return

    # Build panel
    state = status.get("status", "unknown")
    if state == "completed":
        state_display = "[green]COMPLETED[/green]"
    elif state == "failed":
        state_display = "[red]FAILED[/red]"
    elif state in ["queued", "pending"]:
        state_display = f"[yellow]{state.upper()}[/yellow]"
    elif state == "dreaming":
        state_display = "[blue]DREAMING[/blue]"
    else:
        state_display = state.upper()

    content = f"""[bold]Generation ID:[/bold] {generation_id}
[bold]State:[/bold] {state_display}"""

    if status.get("video_url"):
        content += f"\n[bold]Video URL:[/bold] {status['video_url']}"

    if status.get("failure_reason"):
        content += f"\n[bold]Failure Reason:[/bold] [red]{status['failure_reason']}[/red]"

    if status.get("error"):
        content += f"\n[bold]Error:[/bold] [red]{status['error']}[/red]"

    console.print(Panel(content, title="Generation Status"))


@luma_cmd.command("download")
@click.argument("generation_id")
@click.option("--output", "-o", type=click.Path(), help="Output file path (default: <id>.mp4)")
def download_generation(generation_id: str, output: Optional[str]):
    """Download a completed generation

    \b
    Examples:
      claude-studio luma download abc123-def456
      claude-studio luma download abc123-def456 -o my_video.mp4
    """
    provider = get_luma_provider()

    # Default output path
    if not output:
        output = f"{generation_id}.mp4"

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"[dim]Downloading generation {generation_id}...[/dim]")

    async def _download():
        return await provider.download_generation(generation_id, str(output_path))

    try:
        result = asyncio.run(_download())
        console.print(f"[green]Downloaded to: {result}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@luma_cmd.command("recover")
@click.option("--output-dir", "-o", type=click.Path(), default="./recovered",
              help="Output directory for recovered videos")
@click.option("--limit", "-n", type=int, default=100, help="Number of generations to check")
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading")
def recover_generations(output_dir: str, limit: int, dry_run: bool):
    """Download all completed but unfetched generations

    Scans your Luma account for completed generations and downloads any
    that haven't been saved locally yet.

    \b
    Examples:
      claude-studio luma recover
      claude-studio luma recover -o ./my_videos --dry-run
      claude-studio luma recover -n 200
    """
    provider = get_luma_provider()
    output_path = Path(output_dir)

    async def _recover():
        generations = await provider.list_generations(limit=limit)

        # Filter to completed only
        completed = [g for g in generations if g["state"] == "completed" and g.get("video_url")]

        if not completed:
            console.print("[dim]No completed generations found[/dim]")
            return []

        console.print(f"Found [bold]{len(completed)}[/bold] completed generation(s)")

        if dry_run:
            console.print("\n[yellow]Dry run - showing what would be downloaded:[/yellow]")
            for g in completed:
                prompt = g.get("prompt", "N/A")
                console.print(f"  • {g['id']}: {prompt}")
            return []

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        downloaded = []
        for i, g in enumerate(completed, 1):
            gen_id = g["id"]
            file_path = output_path / f"{gen_id}.mp4"

            # Skip if already exists
            if file_path.exists():
                console.print(f"[dim]  [{i}/{len(completed)}] {gen_id} - already exists, skipping[/dim]")
                continue

            console.print(f"  [{i}/{len(completed)}] Downloading {gen_id}...")
            try:
                await provider.download_generation(gen_id, str(file_path))
                downloaded.append(str(file_path))
                console.print(f"    [green]Saved to {file_path}[/green]")
            except Exception as e:
                console.print(f"    [red]Failed: {e}[/red]")

        return downloaded

    downloaded = asyncio.run(_recover())

    if downloaded:
        console.print(f"\n[green]Successfully recovered {len(downloaded)} video(s)[/green]")
    elif not dry_run:
        console.print("\n[dim]No new videos to download[/dim]")
