"""System status command"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box


console = Console()


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status_cmd(as_json: bool):
    """Show overall system status"""

    if as_json:
        import json
        click.echo(json.dumps(get_status_dict(), indent=2))
        return

    console.print(Panel.fit(
        "[bold blue]Claude Studio Producer[/bold blue]\n"
        "AI Video Production Pipeline",
        border_style="blue"
    ))

    # Provider summary
    from core.providers import get_all_providers

    providers = get_all_providers()
    implemented = sum(1 for p in providers if p["status"] == "implemented")
    stubbed = sum(1 for p in providers if p["status"] == "stub")

    provider_table = Table(title="Providers", box=box.ROUNDED)
    provider_table.add_column("Category", style="cyan")
    provider_table.add_column("Implemented", style="green")
    provider_table.add_column("Stubbed", style="yellow")

    categories = {}
    for p in providers:
        cat = p["category"]
        if cat not in categories:
            categories[cat] = {"implemented": 0, "stub": 0}
        categories[cat][p["status"]] += 1

    for cat, counts in categories.items():
        provider_table.add_row(
            cat.title(),
            str(counts.get("implemented", 0)),
            str(counts.get("stub", 0))
        )

    console.print(provider_table)

    # Agent summary
    from agents import get_all_agents

    agents = get_all_agents()

    agent_table = Table(title="Agents", box=box.ROUNDED)
    agent_table.add_column("Agent", style="cyan")
    agent_table.add_column("Status", style="green")

    for agent in agents:
        status_style = "green" if agent["status"] == "implemented" else "yellow"
        agent_table.add_row(
            agent["name"],
            f"[{status_style}]{agent['status']}[/{status_style}]"
        )

    console.print(agent_table)

    # Config status
    config = check_config()

    config_table = Table(title="Configuration", box=box.ROUNDED)
    config_table.add_column("Key", style="cyan")
    config_table.add_column("Status")

    for key, present in config.items():
        status = "[green]✓ Set[/green]" if present else "[red]✗ Missing[/red]"
        config_table.add_row(key, status)

    console.print(config_table)


def get_status_dict() -> dict:
    """Get status as dictionary for JSON output"""
    from core.providers import get_all_providers
    from agents import get_all_agents

    return {
        "providers": get_all_providers(),
        "agents": get_all_agents(),
        "config": check_config()
    }


def check_config() -> dict:
    """Check which API keys are configured"""
    import os
    from dotenv import load_dotenv

    # Load .env if it exists
    load_dotenv()

    keys = [
        "ANTHROPIC_API_KEY",
        "RUNWAY_API_KEY",
        "PIKA_API_KEY",
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY",
        "MUBERT_API_KEY",
    ]

    return {key: bool(os.getenv(key)) for key in keys}
