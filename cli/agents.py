"""Agent commands"""

import click
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich import box

console = Console()


@click.group()
def agents_cmd():
    """Agent information"""
    pass


@agents_cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list(as_json: bool):
    """List all agents"""

    from agents import get_all_agents

    agents = get_all_agents()

    if as_json:
        import json
        click.echo(json.dumps(agents, indent=2))
        return

    table = Table(title="Agents", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Description")

    for agent in agents:
        status_style = "green" if agent["status"] == "implemented" else "yellow"
        table.add_row(
            agent["name"],
            f"[{status_style}]{agent['status']}[/{status_style}]",
            agent["description"][:50] + "..." if len(agent["description"]) > 50 else agent["description"]
        )

    console.print(table)


@agents_cmd.command()
@click.argument("name")
def schema(name: str):
    """Show input/output schema for an agent"""

    from agents import get_agent_schema

    schema = get_agent_schema(name)

    if not schema:
        console.print(f"[red]Agent '{name}' not found[/red]")
        return

    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print(f"{schema['description']}\n")

    console.print("[bold]Inputs:[/bold]")
    for input_name, input_info in schema["inputs"].items():
        console.print(f"  {input_name}: {input_info}")

    console.print("\n[bold]Outputs:[/bold]")
    console.print(f"  {schema['output']}")

    if schema.get("example"):
        console.print("\n[bold]Example:[/bold]")
        syntax = Syntax(schema["example"], "python", theme="monokai")
        console.print(syntax)
