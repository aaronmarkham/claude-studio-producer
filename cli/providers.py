"""Provider commands"""

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group()
def providers_cmd():
    """Provider information and testing"""
    pass


@providers_cmd.command()
@click.option("--category", "-c", help="Filter by category (video, audio, music, image, storage)")
@click.option("--status", "-s", type=click.Choice(["all", "implemented", "stub"]), default="all")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list(category: str, status: str, as_json: bool):
    """List all providers with their status"""

    from core.providers import get_all_providers

    providers = get_all_providers()

    # Filter
    if category:
        providers = [p for p in providers if p["category"] == category]
    if status != "all":
        providers = [p for p in providers if p["status"] == status]

    if as_json:
        import json
        click.echo(json.dumps(providers, indent=2))
        return

    table = Table(title="Providers", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("Cost")
    table.add_column("API Key")

    for p in providers:
        status_style = "green" if p["status"] == "implemented" else "yellow"
        key_status = "[green]✓[/green]" if p["api_key_set"] else "[dim]—[/dim]"

        table.add_row(
            p["name"],
            p["category"],
            f"[{status_style}]{p['status']}[/{status_style}]",
            p["cost_info"],
            key_status
        )

    console.print(table)


@providers_cmd.command()
@click.argument("name")
def check(name: str):
    """Check detailed status of a specific provider"""

    from core.providers import get_provider_info

    info = get_provider_info(name)

    if not info:
        console.print(f"[red]Provider '{name}' not found[/red]")
        return

    console.print(f"\n[bold cyan]{info['name']}[/bold cyan]")
    console.print(f"Category: {info['category']}")
    console.print(f"Status: {info['status']}")
    console.print(f"Cost: {info['cost_info']}")
    console.print(f"API Key Env: {info['api_key_env']}")
    console.print(f"API Key Set: {'Yes' if info['api_key_set'] else 'No'}")

    if info.get("features"):
        console.print("\nFeatures:")
        for f in info["features"]:
            console.print(f"  • {f}")

    if info.get("limitations"):
        console.print("\nLimitations:")
        for l in info["limitations"]:
            console.print(f"  • {l}")

    if info["status"] == "stub":
        console.print("\n[yellow]⚠ This provider is not yet implemented[/yellow]")
        console.print("Methods will raise NotImplementedError")


@providers_cmd.command()
@click.argument("name")
@click.option("--prompt", "-p", default="A serene mountain landscape", help="Test prompt")
def test(name: str, prompt: str):
    """Test a provider with a real API call"""

    import asyncio
    from core.providers import get_provider_instance

    provider = get_provider_instance(name)

    if not provider:
        console.print(f"[red]Provider '{name}' not found[/red]")
        return

    console.print(f"Testing [cyan]{name}[/cyan] with prompt: {prompt[:50]}...")

    try:
        if hasattr(provider, "generate"):
            result = asyncio.run(provider.generate(prompt=prompt, duration=4.0))
            console.print(f"[green]✓ Success![/green]")
            console.print(f"  ID: {result.video_id if hasattr(result, 'video_id') else result.audio_id}")
            console.print(f"  Cost: ${result.generation_cost:.4f}")
        elif hasattr(provider, "generate_speech"):
            result = asyncio.run(provider.generate_speech(text=prompt, voice_id="default"))
            console.print(f"[green]✓ Success![/green]")
            console.print(f"  Duration: {result.duration:.1f}s")
            console.print(f"  Cost: ${result.generation_cost:.4f}")
        else:
            console.print("[yellow]Provider has no testable generate method[/yellow]")
    except NotImplementedError:
        console.print(f"[yellow]⚠ Provider is stubbed (not implemented)[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
