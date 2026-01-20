"""Memory management CLI commands"""

import click
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box
from pathlib import Path

console = Console()


@click.group()
def memory_cmd():
    """Memory system management

    \b
    Commands for managing the multi-tenant memory system:
      stats       Show memory statistics
      list        List learnings by provider
      search      Search learnings
      export      Export learnings to file
      import      Import learnings from file
      promote     Promote a learning to higher level
      clear       Clear learnings (with confirmation)
    """
    pass


@memory_cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stats(as_json: bool):
    """Show memory system statistics"""
    from core.memory import get_memory_manager

    manager = get_memory_manager()

    async def get_stats():
        return await manager.get_stats()

    stats_data = asyncio.run(get_stats())

    if as_json:
        import json
        click.echo(json.dumps(stats_data, indent=2))
        return

    console.print(Panel.fit(
        "[bold blue]Memory System Statistics[/bold blue]",
        border_style="blue"
    ))

    # Show mode
    mode = manager.config.mode.value
    mode_color = "green" if mode == "local" else "cyan"
    console.print(f"Mode: [{mode_color}]{mode}[/{mode_color}]")
    console.print(f"Base Path: [dim]{manager.config.base_path}[/dim]")
    console.print()

    # Stats table
    table = Table(title="Storage Statistics", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Namespaces", str(stats_data.get("total_namespaces", 0)))
    table.add_row("Total Records", str(stats_data.get("total_records", 0)))

    size_bytes = stats_data.get("total_size_bytes", 0)
    if size_bytes > 1024 * 1024:
        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes > 1024:
        size_str = f"{size_bytes / 1024:.2f} KB"
    else:
        size_str = f"{size_bytes} bytes"
    table.add_row("Total Size", size_str)

    console.print(table)

    # Namespace breakdown
    if "namespaces" in stats_data and stats_data["namespaces"]:
        console.print()
        ns_table = Table(title="Namespaces", box=box.ROUNDED)
        ns_table.add_column("Namespace", style="cyan")
        ns_table.add_column("Records", style="green")
        ns_table.add_column("Size", style="dim")

        for ns in sorted(stats_data["namespaces"], key=lambda x: x["record_count"], reverse=True)[:20]:
            size = ns.get("size_bytes", 0)
            if size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} B"
            ns_table.add_row(
                ns["namespace"][:60] + "..." if len(ns["namespace"]) > 60 else ns["namespace"],
                str(ns["record_count"]),
                size_str
            )

        console.print(ns_table)


@memory_cmd.command()
@click.argument("provider", required=False)
@click.option("--level", "-l", type=click.Choice(["platform", "org", "user", "session"]),
              help="Filter by namespace level")
@click.option("--limit", "-n", default=20, help="Maximum records to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list(provider: str, level: str, limit: int, as_json: bool):
    """List learnings, optionally filtered by provider

    \b
    Examples:
      claude-studio memory list           # List all learnings
      claude-studio memory list luma      # List Luma learnings
      claude-studio memory list -l user   # List user-level learnings
    """
    from core.memory import get_memory_manager, NamespaceLevel

    manager = get_memory_manager()
    ctx = manager.get_context()

    async def get_learnings():
        if provider:
            return await manager.get_provider_learnings(provider, ctx, top_k=limit)
        else:
            # Search all learnings
            return await manager.search_learnings("", ctx=ctx, top_k=limit)

    learnings = asyncio.run(get_learnings())

    # Filter by level if specified
    if level:
        level_enum = NamespaceLevel(level)
        learnings = [l for l in learnings if l.level == level_enum]

    if as_json:
        import json
        output = []
        for l in learnings:
            output.append({
                "record_id": l.record.record_id,
                "namespace": l.namespace,
                "level": l.level.value,
                "priority": l.priority,
                "content": l.content,
                "validations": l.record.validations,
                "confidence": l.record.confidence,
                "tags": l.record.tags,
            })
        click.echo(json.dumps(output, indent=2))
        return

    if not learnings:
        console.print("[yellow]No learnings found.[/yellow]")
        if provider:
            console.print(f"[dim]Provider: {provider}[/dim]")
        return

    title = f"Learnings"
    if provider:
        title += f" for [cyan]{provider}[/cyan]"

    console.print(Panel.fit(f"[bold]{title}[/bold]", border_style="blue"))

    table = Table(box=box.ROUNDED)
    table.add_column("Level", style="cyan", width=8)
    table.add_column("Content", style="white", max_width=50)
    table.add_column("Val", style="green", width=4)
    table.add_column("Conf", style="yellow", width=5)
    table.add_column("Tags", style="dim", width=15)

    for l in learnings[:limit]:
        # Format content preview
        content = l.content
        if isinstance(content, dict):
            if "pattern" in content:
                content_str = content["pattern"]
            else:
                content_str = str(content)[:50]
        else:
            content_str = str(content)[:50]

        if len(content_str) > 47:
            content_str = content_str[:47] + "..."

        # Level with color
        level_colors = {
            NamespaceLevel.PLATFORM: "bright_green",
            NamespaceLevel.ORG: "blue",
            NamespaceLevel.USER: "yellow",
            NamespaceLevel.SESSION: "dim",
        }
        level_color = level_colors.get(l.level, "white")

        table.add_row(
            f"[{level_color}]{l.level.value}[/{level_color}]",
            content_str,
            str(l.record.validations),
            f"{l.record.confidence:.2f}",
            ", ".join(l.record.tags[:2]) if l.record.tags else "—"
        )

    console.print(table)
    console.print(f"\n[dim]Showing {min(len(learnings), limit)} of {len(learnings)} learnings[/dim]")


@memory_cmd.command()
@click.argument("query")
@click.option("--provider", "-p", help="Filter by provider")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, provider: str, limit: int, as_json: bool):
    """Search learnings by text query

    \b
    Examples:
      claude-studio memory search "concrete nouns"
      claude-studio memory search "camera motion" -p luma
    """
    from core.memory import get_memory_manager

    manager = get_memory_manager()
    ctx = manager.get_context()

    async def do_search():
        return await manager.search_learnings(
            query=query,
            provider=provider,
            ctx=ctx,
            top_k=limit
        )

    results = asyncio.run(do_search())

    if as_json:
        import json
        output = []
        for r in results:
            output.append({
                "record_id": r.record.record_id,
                "namespace": r.namespace,
                "level": r.level.value,
                "priority": r.priority,
                "content": r.content,
                "text": r.text,
            })
        click.echo(json.dumps(output, indent=2))
        return

    if not results:
        console.print(f"[yellow]No results found for:[/yellow] {query}")
        return

    console.print(Panel.fit(f"Search: [cyan]{query}[/cyan]", border_style="blue"))

    for i, r in enumerate(results, 1):
        content = r.content
        if isinstance(content, dict) and "pattern" in content:
            display = content["pattern"]
        else:
            display = r.text or str(content)[:100]

        console.print(f"\n[bold]{i}.[/bold] [{r.level.value}] {display}")
        console.print(f"   [dim]Namespace: {r.namespace}[/dim]")
        console.print(f"   [dim]Validations: {r.record.validations} | Confidence: {r.record.confidence:.2f}[/dim]")


@memory_cmd.command()
@click.argument("provider")
@click.argument("pattern")
@click.option("--level", "-l", type=click.Choice(["platform", "org", "user", "session"]),
              default="user", help="Namespace level to store at")
@click.option("--tag", "-t", multiple=True, help="Additional tags")
def add(provider: str, pattern: str, level: str, tag: tuple):
    """Add a new learning for a provider

    \b
    Examples:
      claude-studio memory add luma "Use concrete nouns for subjects"
      claude-studio memory add runway "Avoid rapid camera movements" -l org
    """
    from core.memory import get_memory_manager, NamespaceLevel

    manager = get_memory_manager()
    ctx = manager.get_context()
    level_enum = NamespaceLevel(level)

    async def store_learning():
        return await manager.store_provider_learning(
            provider=provider,
            learning={"pattern": pattern},
            level=level_enum,
            ctx=ctx,
            tags=list(tag) if tag else None,
        )

    record_id = asyncio.run(store_learning())

    console.print(f"[green]Learning added successfully![/green]")
    console.print(f"  Provider: [cyan]{provider}[/cyan]")
    console.print(f"  Level: [yellow]{level}[/yellow]")
    console.print(f"  Pattern: {pattern}")
    console.print(f"  [dim]Record ID: {record_id}[/dim]")


@memory_cmd.command()
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--provider", "-p", help="Export only specific provider")
def export(output: str, provider: str):
    """Export learnings to JSON file

    \b
    Examples:
      claude-studio memory export -o learnings.json
      claude-studio memory export -p luma -o luma_learnings.json
    """
    from core.memory import get_memory_manager
    from core.memory.backends.local import LocalMemoryBackend
    import json

    manager = get_memory_manager()

    if not isinstance(manager.backend, LocalMemoryBackend):
        console.print("[red]Export is only supported for local backend[/red]")
        return

    async def do_export():
        return await manager.backend.export_all()

    data = asyncio.run(do_export())

    # Filter by provider if specified
    if provider:
        filtered = {}
        for ns, records in data.items():
            if f"/provider/{provider}" in ns or provider in ns:
                filtered[ns] = records
        data = filtered

    if not data:
        console.print("[yellow]No data to export[/yellow]")
        return

    # Default output path
    if not output:
        output = f"learnings_export_{provider or 'all'}.json"

    # Write to file
    with open(output, 'w') as f:
        json.dump(data, f, indent=2, default=str)

    total_records = sum(len(records) for records in data.values())
    console.print(f"[green]Exported {total_records} records from {len(data)} namespaces[/green]")
    console.print(f"Output: [cyan]{output}[/cyan]")


@memory_cmd.command(name="import")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing (don't overwrite)")
def import_cmd(input_file: str, merge: bool):
    """Import learnings from JSON file

    \b
    Examples:
      claude-studio memory import learnings.json
      claude-studio memory import shared_learnings.json --merge
    """
    from core.memory import get_memory_manager
    from core.memory.backends.local import LocalMemoryBackend
    import json

    manager = get_memory_manager()

    if not isinstance(manager.backend, LocalMemoryBackend):
        console.print("[red]Import is only supported for local backend[/red]")
        return

    # Load data
    with open(input_file, 'r') as f:
        data = json.load(f)

    async def do_import():
        await manager.backend.import_all(data)

    asyncio.run(do_import())

    total_records = sum(len(records) for records in data.values())
    console.print(f"[green]Imported {total_records} records from {len(data)} namespaces[/green]")


@memory_cmd.command()
@click.argument("namespace")
@click.argument("record_id")
@click.option("--reason", "-r", default="manual", help="Promotion reason")
def promote(namespace: str, record_id: str, reason: str):
    """Promote a learning to the next level

    \b
    Examples:
      claude-studio memory promote "/org/local/actor/dev/learnings/provider/luma" abc123
    """
    from core.memory import get_memory_manager, MultiTenantNamespaceBuilder

    manager = get_memory_manager()
    ctx = manager.get_context()

    # Parse namespace to get provider if present
    parsed = MultiTenantNamespaceBuilder.parse(namespace)
    provider = parsed.get("provider_id")

    async def do_promote():
        return await manager.promote_learning(
            record_id=record_id,
            from_namespace=namespace,
            ctx=ctx,
            provider=provider,
            reason=reason,
        )

    new_id = asyncio.run(do_promote())

    if new_id:
        console.print(f"[green]Learning promoted successfully![/green]")
        console.print(f"  New record ID: [cyan]{new_id}[/cyan]")
    else:
        console.print("[yellow]Could not promote learning.[/yellow]")
        console.print("[dim]Record may already be at highest level or not found.[/dim]")


@memory_cmd.command()
@click.option("--provider", "-p", help="Clear only specific provider")
@click.option("--level", "-l", type=click.Choice(["session", "user"]),
              help="Clear only specific level")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def clear(provider: str, level: str, force: bool):
    """Clear learnings (requires confirmation)

    \b
    Examples:
      claude-studio memory clear -p luma -l session  # Clear session learnings for luma
      claude-studio memory clear -l user             # Clear all user learnings
    """
    from core.memory import get_memory_manager, NamespaceLevel, MultiTenantNamespaceBuilder

    if not level and not provider and not force:
        console.print("[red]Clearing all learnings requires --force flag[/red]")
        return

    if not force:
        if not click.confirm(f"Clear learnings for provider={provider or 'all'}, level={level or 'all'}?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    manager = get_memory_manager()
    ctx = manager.get_context()
    ns = MultiTenantNamespaceBuilder

    async def do_clear():
        total_deleted = 0

        # Build namespace to clear
        if provider and level:
            level_enum = NamespaceLevel(level)
            namespace = ns.for_provider_learnings(provider, level_enum, ctx)
            count = await manager.backend.delete_namespace(namespace)
            total_deleted += count
        elif level:
            # Clear all providers at this level
            level_enum = NamespaceLevel(level)
            if level_enum == NamespaceLevel.USER:
                # Clear user learnings
                global_ns = ns.build(ns.USER_LEARNINGS_GLOBAL, ctx)
                total_deleted += await manager.backend.delete_namespace(global_ns)
        elif provider:
            # Clear provider at all user levels
            for lvl in [NamespaceLevel.SESSION, NamespaceLevel.USER]:
                try:
                    namespace = ns.for_provider_learnings(provider, lvl, ctx)
                    count = await manager.backend.delete_namespace(namespace)
                    total_deleted += count
                except Exception:
                    pass

        return total_deleted

    deleted = asyncio.run(do_clear())
    console.print(f"[green]Cleared {deleted} records[/green]")


@memory_cmd.command()
def tree():
    """Show namespace hierarchy as a tree"""
    from core.memory import get_memory_manager
    from core.memory.backends.local import LocalMemoryBackend

    manager = get_memory_manager()

    if not isinstance(manager.backend, LocalMemoryBackend):
        console.print("[yellow]Tree view only available for local backend[/yellow]")
        return

    async def get_namespaces():
        return await manager.backend.list_namespaces()

    namespaces = asyncio.run(get_namespaces())

    if not namespaces:
        console.print("[yellow]No namespaces found[/yellow]")
        return

    # Build tree structure
    tree = Tree("[bold blue]Memory Namespaces[/bold blue]")

    # Group by first component
    groups = {}
    for ns in sorted(namespaces):
        parts = ns.strip("/").split("/")
        if parts[0] not in groups:
            groups[parts[0]] = []
        groups[parts[0]].append(ns)

    # Add to tree
    for group_name, group_namespaces in sorted(groups.items()):
        if group_name == "platform":
            style = "green"
        elif group_name == "org":
            style = "cyan"
        else:
            style = "white"

        group_branch = tree.add(f"[{style}]{group_name}/[/{style}]")

        for ns in group_namespaces:
            # Show just the part after the group
            remainder = ns.replace(f"/{group_name}/", "")
            group_branch.add(f"[dim]{remainder}[/dim]")

    console.print(tree)


@memory_cmd.command()
def preferences():
    """Show current user preferences"""
    from core.memory import get_memory_manager
    import json

    manager = get_memory_manager()
    ctx = manager.get_context()

    async def get_prefs():
        return await manager.get_preferences(ctx)

    prefs = asyncio.run(get_prefs())

    if not prefs:
        console.print("[yellow]No preferences set[/yellow]")
        console.print("[dim]Use 'claude-studio memory set-pref KEY VALUE' to set preferences[/dim]")
        return

    console.print(Panel.fit("[bold]User Preferences[/bold]", border_style="blue"))

    table = Table(box=box.ROUNDED)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    for key, value in prefs.items():
        if isinstance(value, dict):
            value = json.dumps(value)
        table.add_row(key, str(value))

    console.print(table)


@memory_cmd.command()
@click.argument("key")
@click.argument("value")
def set_pref(key: str, value: str):
    """Set a user preference

    \b
    Examples:
      claude-studio memory set-pref default_provider luma
      claude-studio memory set-pref quality high
    """
    from core.memory import get_memory_manager
    import json

    manager = get_memory_manager()
    ctx = manager.get_context()

    # Try to parse as JSON for complex values
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    async def set_prefs():
        return await manager.set_preferences({key: parsed_value}, ctx)

    asyncio.run(set_prefs())

    console.print(f"[green]Preference set:[/green] {key} = {value}")
