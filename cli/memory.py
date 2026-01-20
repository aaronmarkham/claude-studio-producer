"""Memory management CLI commands

Provides commands for managing the multi-tenant namespaced memory system:
- List learnings by namespace/level
- Promote learnings between levels
- Clear session/user learnings
- Migrate from legacy format
- Show statistics
- Generate provider guidelines for prompts
- Validate prompts against learned constraints
- Seed platform-level curated learnings
"""

import click
import asyncio
import json
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

console = Console()


def get_manager_with_context(ctx_obj: dict):
    """Get configured memory manager with CLI context"""
    from core.memory import get_memory_manager, MultiTenantConfig, MemoryMode

    # Override config if CLI options provided
    config = MultiTenantConfig.from_env()

    if ctx_obj.get("org_id"):
        config.default_org_id = ctx_obj["org_id"]
    if ctx_obj.get("actor_id"):
        config.default_actor_id = ctx_obj["actor_id"]
    if ctx_obj.get("backend") == "local":
        config.mode = MemoryMode.LOCAL

    # Reset global manager to apply new config
    from core.memory.multi_tenant_manager import reset_memory_manager, MultiTenantMemoryManager
    reset_memory_manager()

    return MultiTenantMemoryManager(config)


@click.group()
@click.option("--org", "-o", envvar="CLAUDE_STUDIO_ORG_ID",
              help="Organization ID (default: from env or 'local')")
@click.option("--actor", "-a", envvar="CLAUDE_STUDIO_ACTOR_ID",
              help="Actor/user ID (default: from env or 'dev')")
@click.option("--backend", "-b", envvar="MEMORY_BACKEND",
              type=click.Choice(["local", "hosted"]), default="local",
              help="Memory backend (local or hosted)")
@click.pass_context
def memory_cmd(ctx, org: str, actor: str, backend: str):
    """Memory system management

    \b
    Multi-tenant memory system for storing and retrieving learnings.
    Supports namespace hierarchy: Platform → Org → User → Session

    \b
    Global Options:
      --org, -o      Organization ID for multi-tenant context
      --actor, -a    Actor (user) ID for multi-tenant context
      --backend, -b  Memory backend (local or hosted)

    \b
    Commands:
      stats       Show memory statistics
      list        List learnings by provider
      search      Search learnings
      guidelines  Get formatted guidelines for a provider
      validate    Validate a prompt against learned constraints
      add         Add a new learning
      promote     Promote a learning to higher level
      export      Export learnings to file
      import      Import learnings from file
      migrate     Migrate from legacy long_term.json format
      seed        Seed curated platform learnings
      clear       Clear learnings (with confirmation)
      tree        Show namespace hierarchy
      preferences Show user preferences
      set-pref    Set a user preference
    """
    ctx.ensure_object(dict)
    ctx.obj["org_id"] = org
    ctx.obj["actor_id"] = actor
    ctx.obj["backend"] = backend


@memory_cmd.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def stats(ctx, as_json: bool):
    """Show memory system statistics"""
    manager = get_manager_with_context(ctx.obj)

    async def get_stats():
        return await manager.get_stats()

    stats_data = asyncio.run(get_stats())

    if as_json:
        click.echo(json.dumps(stats_data, indent=2))
        return

    console.print(Panel.fit(
        "[bold blue]Memory System Statistics[/bold blue]",
        border_style="blue"
    ))

    # Show context
    console.print(f"Organization: [cyan]{ctx.obj.get('org_id', 'local')}[/cyan]")
    console.print(f"Actor: [cyan]{ctx.obj.get('actor_id', 'dev')}[/cyan]")
    console.print(f"Mode: [green]{manager.config.mode.value}[/green]")
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


@memory_cmd.command("list")
@click.argument("provider", required=False)
@click.option("--level", "-l", type=click.Choice(["platform", "org", "user", "session"]),
              help="Filter by namespace level")
@click.option("--limit", "-n", default=20, help="Maximum records to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def list_cmd(ctx, provider: str, level: str, limit: int, as_json: bool):
    """List learnings, optionally filtered by provider

    \b
    Examples:
      claude-studio memory list           # List all learnings
      claude-studio memory list luma      # List Luma learnings
      claude-studio memory list -l user   # List user-level learnings
      claude-studio memory list --org myorg --actor me luma  # Multi-tenant
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    async def get_learnings():
        if provider:
            return await manager.get_provider_learnings(provider, ns_ctx, top_k=limit)
        else:
            # Search all learnings
            return await manager.search_learnings("", ctx=ns_ctx, top_k=limit)

    learnings = asyncio.run(get_learnings())

    # Filter by level if specified
    if level:
        level_enum = NamespaceLevel(level)
        learnings = [l for l in learnings if l.level == level_enum]

    if as_json:
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
            elif "content" in content:
                content_str = content["content"]
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
            ", ".join(l.record.tags[:2]) if l.record.tags else "-"
        )

    console.print(table)
    console.print(f"\n[dim]Showing {min(len(learnings), limit)} of {len(learnings)} learnings[/dim]")


@memory_cmd.command()
@click.argument("query")
@click.option("--provider", "-p", help="Filter by provider")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def search(ctx, query: str, provider: str, limit: int, as_json: bool):
    """Search learnings by text query

    \b
    Examples:
      claude-studio memory search "concrete nouns"
      claude-studio memory search "camera motion" -p luma
    """
    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    async def do_search():
        return await manager.search_learnings(
            query=query,
            provider=provider,
            ctx=ns_ctx,
            top_k=limit
        )

    results = asyncio.run(do_search())

    if as_json:
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
        elif isinstance(content, dict) and "content" in content:
            display = content["content"]
        else:
            display = r.text or str(content)[:100]

        console.print(f"\n[bold]{i}.[/bold] [{r.level.value}] {display}")
        console.print(f"   [dim]Namespace: {r.namespace}[/dim]")
        console.print(f"   [dim]Validations: {r.record.validations} | Confidence: {r.record.confidence:.2f}[/dim]")


# =============================================================================
# GUIDELINES COMMAND
# =============================================================================

@memory_cmd.command()
@click.argument("provider")
@click.option("--level", "-l",
              type=click.Choice(["platform", "org", "user", "session", "all"]),
              default="all", help="Include learnings from this level")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["rich", "json", "prompt"]),
              default="rich", help="Output format (prompt for Claude injection)")
@click.pass_context
def guidelines(ctx, provider: str, level: str, output_format: str):
    """Get formatted guidelines for a provider

    Aggregates learnings into actionable guidelines that can be:
    - Displayed in rich format for human review
    - Output as JSON for programmatic use
    - Formatted for direct injection into Claude prompts

    \b
    Examples:
      claude-studio memory guidelines luma
      claude-studio memory guidelines luma --format prompt
      claude-studio memory guidelines runway -l org --format json
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    # Map level to include flags
    include_levels = set()
    if level == "all":
        include_levels = {"platform", "org", "user", "session"}
    else:
        # Cascade down from selected level
        level_order = ["platform", "org", "user", "session"]
        for lvl in level_order:
            include_levels.add(lvl)
            if lvl == level:
                break

    async def get_guidelines():
        learnings = await manager.get_provider_learnings(
            provider, ns_ctx,
            include_session=("session" in include_levels),
            top_k=100
        )

        # Categorize learnings
        guidelines = {
            "avoid": [],
            "prefer": [],
            "tips": [],
            "patterns": [],
        }

        for l in learnings:
            # Skip if level not included
            if l.level.value not in include_levels:
                continue

            content = l.content
            category = None
            content_text = None

            if isinstance(content, dict):
                category = content.get("category")
                content_text = content.get("pattern") or content.get("content") or str(content)
            else:
                content_text = str(content)

            # Build entry with metadata
            entry = {
                "content": content_text,
                "level": l.level.value,
                "confidence": l.record.confidence,
                "validations": l.record.validations,
            }

            # Categorize based on content or tags
            if category == "avoid" or "avoid" in (l.record.tags or []):
                guidelines["avoid"].append(entry)
            elif category == "prefer" or "prefer" in (l.record.tags or []):
                guidelines["prefer"].append(entry)
            elif category == "tip" or "tip" in (l.record.tags or []):
                guidelines["tips"].append(entry)
            elif category == "pattern" or "pattern" in (l.record.tags or []):
                guidelines["patterns"].append(entry)
            else:
                # Default to tips
                guidelines["tips"].append(entry)

        return guidelines

    guidelines_data = asyncio.run(get_guidelines())

    if output_format == "json":
        click.echo(json.dumps(guidelines_data, indent=2))
        return

    if output_format == "prompt":
        # Format for injection into Claude prompt
        prompt_text = _format_guidelines_for_prompt(provider, guidelines_data)
        click.echo(prompt_text)
        return

    # Rich format
    console.print(Panel.fit(
        f"[bold]Provider Guidelines: {provider}[/bold]\n"
        f"[dim]Level: {level}[/dim]",
        title="Guidelines"
    ))

    if guidelines_data.get("avoid"):
        console.print("\n[red bold]AVOID (these cause failures):[/red bold]")
        for item in guidelines_data["avoid"]:
            conf = f"[dim](conf: {item['confidence']:.0%})[/dim]"
            lvl = f"[dim][{item['level']}][/dim]"
            console.print(f"  [red]x[/red] {item['content']} {conf} {lvl}")

    if guidelines_data.get("prefer"):
        console.print("\n[green bold]PREFER (these work well):[/green bold]")
        for item in guidelines_data["prefer"]:
            console.print(f"  [green]+[/green] {item['content']}")

    if guidelines_data.get("tips"):
        console.print("\n[blue bold]TIPS:[/blue bold]")
        for item in guidelines_data["tips"]:
            console.print(f"  [blue]*[/blue] {item['content']}")

    if guidelines_data.get("patterns"):
        console.print("\n[magenta bold]PATTERNS:[/magenta bold]")
        for item in guidelines_data["patterns"]:
            console.print(f"  [magenta]~[/magenta] {item['content']}")

    if not any(guidelines_data.values()):
        console.print("[yellow]No guidelines found for this provider[/yellow]")


def _format_guidelines_for_prompt(provider: str, guidelines: dict) -> str:
    """Format guidelines for injection into a Claude prompt"""
    lines = [f"## Provider Guidelines for {provider}", ""]

    if guidelines.get("avoid"):
        lines.append("### MUST AVOID (these cause failures):")
        for item in guidelines["avoid"][:10]:
            lines.append(f"- {item['content']}")
        lines.append("")

    if guidelines.get("prefer"):
        lines.append("### PREFERRED (these work well):")
        for item in guidelines["prefer"][:10]:
            lines.append(f"- {item['content']}")
        lines.append("")

    if guidelines.get("tips"):
        lines.append("### TIPS:")
        for item in guidelines["tips"][:8]:
            lines.append(f"- {item['content']}")
        lines.append("")

    if guidelines.get("patterns"):
        lines.append("### PATTERNS:")
        for item in guidelines["patterns"][:5]:
            lines.append(f"- {item['content']}")

    return "\n".join(lines)


# =============================================================================
# VALIDATE COMMAND
# =============================================================================

@memory_cmd.command()
@click.argument("text")
@click.option("--provider", "-p", default="luma", help="Provider to validate against")
@click.option("--level", "-l",
              type=click.Choice(["session", "user", "org", "platform", "all"]),
              default="all", help="Include constraints from these levels")
@click.option("--fix", is_flag=True, help="Show suggested fixes")
@click.pass_context
def validate(ctx, text: str, provider: str, level: str, fix: bool):
    """Validate a prompt against learned constraints

    Pre-flight check for prompts before sending to a provider.
    Checks against "avoid" learnings and suggests improvements.

    \b
    Examples:
      claude-studio memory validate "A cat dancing wildly" -p luma
      claude-studio memory validate "Person walking through abstract shapes" --fix
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    # Map level to include flags
    include_levels = set()
    if level == "all":
        include_levels = {"platform", "org", "user", "session"}
    else:
        level_order = ["platform", "org", "user", "session"]
        for lvl in level_order:
            include_levels.add(lvl)
            if lvl == level:
                break

    async def get_constraints():
        learnings = await manager.get_provider_learnings(
            provider, ns_ctx,
            include_session=("session" in include_levels),
            top_k=100
        )

        constraints = {"avoid": [], "prefer": []}

        for l in learnings:
            if l.level.value not in include_levels:
                continue

            content = l.content
            category = None
            content_text = None

            if isinstance(content, dict):
                category = content.get("category")
                content_text = content.get("pattern") or content.get("content") or str(content)
            else:
                content_text = str(content)

            entry = {
                "content": content_text,
                "level": l.level.value,
                "confidence": l.record.confidence,
            }

            if category == "avoid" or "avoid" in (l.record.tags or []):
                constraints["avoid"].append(entry)
            elif category == "prefer" or "prefer" in (l.record.tags or []):
                constraints["prefer"].append(entry)

        return constraints

    constraints = asyncio.run(get_constraints())

    console.print(f"[dim]Loaded {len(constraints['avoid'])} avoid, {len(constraints['prefer'])} prefer constraints[/dim]")
    console.print(f"[dim]Validation level: {level}[/dim]\n")

    # Check for violations
    violations = []
    text_lower = text.lower()

    for constraint in constraints["avoid"]:
        content = constraint["content"].lower()
        # Simple keyword matching - check if constraint keywords appear in text
        keywords = [w for w in content.split() if len(w) > 3]
        for keyword in keywords:
            if keyword in text_lower:
                violations.append({
                    "constraint": constraint["content"],
                    "matched": keyword,
                    "level": constraint["level"],
                    "confidence": constraint["confidence"],
                })
                break

    if not violations:
        console.print("[green]PASSED[/green] - No constraint violations found")

        # Show applicable preferences
        if constraints["prefer"]:
            console.print("\n[dim]Relevant preferences:[/dim]")
            for pref in constraints["prefer"][:5]:
                console.print(f"  [green]+[/green] {pref['content']}")
        return

    console.print(f"[red]FAILED[/red] - {len(violations)} violation(s) found\n")

    for v in violations:
        level_badge = f"[dim]({v['level']})[/dim]"
        console.print(f"  [red]x[/red] {level_badge} {v['constraint']}")
        console.print(f"    [dim]Matched: '{v['matched']}'[/dim]")

    if fix:
        console.print("\n[bold]Suggestions:[/bold]")
        for pref in constraints["prefer"][:3]:
            console.print(f"  [green]+[/green] Consider: {pref['content']}")


@memory_cmd.command()
@click.argument("provider")
@click.argument("pattern")
@click.option("--level", "-l", type=click.Choice(["platform", "org", "user", "session"]),
              default="user", help="Namespace level to store at")
@click.option("--category", "-c", type=click.Choice(["avoid", "prefer", "tip", "pattern"]),
              default="tip", help="Learning category")
@click.option("--tag", "-t", multiple=True, help="Additional tags")
@click.pass_context
def add(ctx, provider: str, pattern: str, level: str, category: str, tag: tuple):
    """Add a new learning for a provider

    \b
    Examples:
      claude-studio memory add luma "Use concrete nouns for subjects"
      claude-studio memory add runway "Avoid rapid camera movements" -c avoid
      claude-studio memory add luma "Specific objects work better than abstract" -l org
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()
    level_enum = NamespaceLevel(level)

    async def store_learning():
        tags_list = [provider, category]  # Always include provider tag for filtering
        if tag:
            tags_list.extend(list(tag))
        return await manager.store_provider_learning(
            provider=provider,
            learning={"pattern": pattern, "category": category},
            level=level_enum,
            ctx=ns_ctx,
            tags=tags_list,
        )

    record_id = asyncio.run(store_learning())

    console.print(f"[green]Learning added successfully![/green]")
    console.print(f"  Provider: [cyan]{provider}[/cyan]")
    console.print(f"  Level: [yellow]{level}[/yellow]")
    console.print(f"  Category: [magenta]{category}[/magenta]")
    console.print(f"  Pattern: {pattern}")
    console.print(f"  [dim]Record ID: {record_id}[/dim]")


@memory_cmd.command()
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--provider", "-p", help="Export only specific provider")
@click.option("--level", "-l",
              type=click.Choice(["all", "platform", "org", "user"]),
              default="user", help="Levels to export")
@click.pass_context
def export(ctx, output: str, provider: str, level: str):
    """Export learnings to JSON file

    \b
    Examples:
      claude-studio memory export -o learnings.json
      claude-studio memory export -p luma -o luma_learnings.json
    """
    from core.memory.backends.local import LocalMemoryBackend

    manager = get_manager_with_context(ctx.obj)

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

    # Filter by level
    if level != "all":
        filtered = {}
        for ns, records in data.items():
            ns_level = _get_namespace_level(ns)
            if level == "platform" and ns_level == "platform":
                filtered[ns] = records
            elif level == "org" and ns_level in ("platform", "org"):
                filtered[ns] = records
            elif level == "user" and ns_level in ("platform", "org", "user", "session"):
                filtered[ns] = records
        data = filtered

    if not data:
        console.print("[yellow]No data to export[/yellow]")
        return

    # Default output path
    if not output:
        output = f"learnings_export_{provider or 'all'}.json"

    # Add export metadata
    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "context": {
            "org_id": ctx.obj.get("org_id"),
            "actor_id": ctx.obj.get("actor_id"),
            "level": level,
        },
        "namespaces": data,
    }

    # Write to file
    with open(output, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)

    total_records = sum(len(records) for records in data.values())
    console.print(f"[green]Exported {total_records} records from {len(data)} namespaces[/green]")
    console.print(f"Output: [cyan]{output}[/cyan]")


@memory_cmd.command(name="import")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing (don't overwrite)")
@click.pass_context
def import_cmd(ctx, input_file: str, merge: bool):
    """Import learnings from JSON file

    \b
    Examples:
      claude-studio memory import learnings.json
      claude-studio memory import shared_learnings.json --merge
    """
    from core.memory.backends.local import LocalMemoryBackend

    manager = get_manager_with_context(ctx.obj)

    if not isinstance(manager.backend, LocalMemoryBackend):
        console.print("[red]Import is only supported for local backend[/red]")
        return

    # Load data
    with open(input_file, 'r') as f:
        data = json.load(f)

    # Handle export format vs raw format
    if "namespaces" in data:
        data = data["namespaces"]

    async def do_import():
        await manager.backend.import_all(data)

    asyncio.run(do_import())

    total_records = sum(len(records) for records in data.values())
    console.print(f"[green]Imported {total_records} records from {len(data)} namespaces[/green]")


@memory_cmd.command()
@click.argument("namespace")
@click.argument("record_id")
@click.option("--reason", "-r", default="manual", help="Promotion reason")
@click.pass_context
def promote(ctx, namespace: str, record_id: str, reason: str):
    """Promote a learning to the next level

    \b
    Examples:
      claude-studio memory promote "/org/local/actor/dev/learnings/provider/luma" abc123
    """
    from core.memory import MultiTenantNamespaceBuilder

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    # Parse namespace to get provider if present
    parsed = MultiTenantNamespaceBuilder.parse(namespace)
    provider = parsed.get("provider_id")

    async def do_promote():
        return await manager.promote_learning(
            record_id=record_id,
            from_namespace=namespace,
            ctx=ns_ctx,
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
@click.pass_context
def clear(ctx, provider: str, level: str, force: bool):
    """Clear learnings (requires confirmation)

    \b
    Examples:
      claude-studio memory clear -p luma -l session  # Clear session learnings for luma
      claude-studio memory clear -l user             # Clear all user learnings
    """
    from core.memory import NamespaceLevel, MultiTenantNamespaceBuilder

    if not level and not provider and not force:
        console.print("[red]Clearing all learnings requires --force flag[/red]")
        return

    if not force:
        if not click.confirm(f"Clear learnings for provider={provider or 'all'}, level={level or 'all'}?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()
    ns = MultiTenantNamespaceBuilder

    async def do_clear():
        total_deleted = 0

        # Build namespace to clear
        if provider and level:
            level_enum = NamespaceLevel(level)
            namespace = ns.for_provider_learnings(provider, level_enum, ns_ctx)
            count = await manager.backend.delete_namespace(namespace)
            total_deleted += count
        elif level:
            # Clear all providers at this level
            level_enum = NamespaceLevel(level)
            if level_enum == NamespaceLevel.USER:
                # Clear user learnings
                global_ns = ns.build(ns.USER_LEARNINGS_GLOBAL, ns_ctx)
                total_deleted += await manager.backend.delete_namespace(global_ns)
        elif provider:
            # Clear provider at all user levels
            for lvl in [NamespaceLevel.SESSION, NamespaceLevel.USER]:
                try:
                    namespace = ns.for_provider_learnings(provider, lvl, ns_ctx)
                    count = await manager.backend.delete_namespace(namespace)
                    total_deleted += count
                except Exception:
                    pass

        return total_deleted

    deleted = asyncio.run(do_clear())
    console.print(f"[green]Cleared {deleted} records[/green]")


@memory_cmd.command()
@click.option("--provider", "-p", default="luma", help="Provider for examples")
@click.pass_context
def tree(ctx, provider: str):
    """Show namespace hierarchy as a tree"""
    from core.memory import MultiTenantNamespaceBuilder
    from core.memory.backends.local import LocalMemoryBackend

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    console.print(Panel.fit(
        f"Org: [cyan]{ns_ctx.org_id}[/cyan]\n"
        f"Actor: [cyan]{ns_ctx.actor_id}[/cyan]\n"
        f"Provider: [cyan]{provider}[/cyan]",
        title="Namespace Tree"
    ))

    ns = MultiTenantNamespaceBuilder

    tree_widget = Tree("/")

    # Platform
    platform = tree_widget.add("[red bold]platform[/red bold] (curated, cross-tenant)")
    platform.add("learnings/global")
    platform.add(f"learnings/provider/{provider}")
    platform.add("config")

    # Org
    org = tree_widget.add(f"[yellow bold]org/{ns_ctx.org_id}[/yellow bold]")
    org.add("learnings/global")
    org.add(f"learnings/provider/{provider}")
    org.add("config")
    org.add("shared")

    # Actor
    actor = org.add(f"[green bold]actor/{ns_ctx.actor_id}[/green bold]")
    actor.add("learnings/global")
    actor.add(f"learnings/provider/{provider}")
    actor.add("preferences")
    actor.add("runs/{runId}")

    # Session
    session = actor.add("[blue bold]sessions/{sessionId}[/blue bold]")
    session.add("learnings")
    session.add("context")

    console.print(tree_widget)

    # Show retrieval priority
    console.print("\n[bold]Retrieval Priority (high -> low):[/bold]")
    for ns_info in ns.get_retrieval_namespaces(provider, ns_ctx):
        bar = "#" * int(ns_info['priority'] * 10)
        console.print(f"  [{ns_info['priority']:.2f}] {bar} {ns_info['namespace']}")


@memory_cmd.command()
@click.pass_context
def preferences(ctx):
    """Show current user preferences"""
    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    async def get_prefs():
        return await manager.get_preferences(ns_ctx)

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
@click.pass_context
def set_pref(ctx, key: str, value: str):
    """Set a user preference

    \b
    Examples:
      claude-studio memory set-pref default_provider luma
      claude-studio memory set-pref quality high
    """
    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    # Try to parse as JSON for complex values
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    async def set_prefs():
        return await manager.set_preferences({key: parsed_value}, ns_ctx)

    asyncio.run(set_prefs())

    console.print(f"[green]Preference set:[/green] {key} = {value}")


# =============================================================================
# MIGRATE COMMAND
# =============================================================================

@memory_cmd.command()
@click.argument("legacy_path", type=click.Path(exists=True))
@click.option("--to-level", "-l",
              type=click.Choice(["user", "org"]),
              default="org", help="Target level for migrated learnings")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated")
@click.pass_context
def migrate(ctx, legacy_path: str, to_level: str, dry_run: bool):
    """Migrate from legacy long_term.json format

    Converts legacy single-file learning storage to the new
    multi-tenant namespace structure.

    \b
    Examples:
      claude-studio memory migrate artifacts/long_term.json
      claude-studio memory migrate artifacts/long_term.json --dry-run
      claude-studio memory migrate artifacts/long_term.json --to-level user
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    with open(legacy_path) as f:
        legacy = json.load(f)

    # Analyze what will be migrated
    stats = {
        "preferences": len(legacy.get("preferences", {})),
        "provider_learnings": 0,
        "run_history": len(legacy.get("production_history", [])),
        "providers": [],
    }

    for provider, knowledge in legacy.get("provider_knowledge", {}).items():
        count = 0
        count += len(knowledge.get("avoid_list", []))
        count += len(knowledge.get("prompt_tips", []))
        count += len(knowledge.get("known_strengths", []))
        count += len(knowledge.get("recent_learnings", []))
        stats["provider_learnings"] += count
        if count > 0:
            stats["providers"].append(f"{provider} ({count})")

    console.print(Panel(
        f"[bold]Migration Preview[/bold]\n\n"
        f"Source: {legacy_path}\n"
        f"Target level: [yellow]{to_level}[/yellow]\n"
        f"Target org: [cyan]{ns_ctx.org_id}[/cyan]\n"
        f"Target actor: [cyan]{ns_ctx.actor_id}[/cyan]\n\n"
        f"Preferences: {stats['preferences']}\n"
        f"Provider learnings: {stats['provider_learnings']}\n"
        f"  Providers: {', '.join(stats['providers']) or 'none'}\n"
        f"Run history: {stats['run_history']} (not migrated)",
        title="Migration"
    ))

    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        return

    if not click.confirm("Proceed with migration?"):
        return

    level_enum = NamespaceLevel(to_level)

    async def do_migration():
        counts = {"preferences": 0, "provider_learnings": 0}

        # Migrate preferences
        if legacy.get("preferences"):
            await manager.set_preferences(legacy["preferences"], ns_ctx)
            counts["preferences"] = len(legacy["preferences"])

        # Migrate provider learnings
        for provider, knowledge in legacy.get("provider_knowledge", {}).items():
            # Avoid list -> category: avoid
            for item in knowledge.get("avoid_list", []):
                if isinstance(item, dict):
                    content = item.get("pattern") or item.get("prompt", "")
                else:
                    content = str(item)

                await manager.store_provider_learning(
                    provider=provider,
                    learning={"pattern": content, "category": "avoid"},
                    level=level_enum,
                    ctx=ns_ctx,
                    tags=[provider, "avoid", "migrated"],
                )
                counts["provider_learnings"] += 1

            # Prompt tips -> category: tip
            for item in knowledge.get("prompt_tips", []):
                content = item if isinstance(item, str) else str(item)
                await manager.store_provider_learning(
                    provider=provider,
                    learning={"pattern": content, "category": "tip"},
                    level=level_enum,
                    ctx=ns_ctx,
                    tags=[provider, "tip", "migrated"],
                )
                counts["provider_learnings"] += 1

            # Known strengths -> category: prefer
            for item in knowledge.get("known_strengths", []):
                content = item if isinstance(item, str) else str(item)
                await manager.store_provider_learning(
                    provider=provider,
                    learning={"pattern": content, "category": "prefer"},
                    level=level_enum,
                    ctx=ns_ctx,
                    tags=[provider, "prefer", "migrated"],
                )
                counts["provider_learnings"] += 1

            # Recent learnings -> category: pattern
            for item in knowledge.get("recent_learnings", []):
                if isinstance(item, dict):
                    content = item.get("pattern") or item.get("learning", "")
                else:
                    content = str(item)

                await manager.store_provider_learning(
                    provider=provider,
                    learning={"pattern": content, "category": "pattern"},
                    level=level_enum,
                    ctx=ns_ctx,
                    tags=[provider, "pattern", "migrated"],
                )
                counts["provider_learnings"] += 1

        return counts

    with console.status("Migrating..."):
        counts = asyncio.run(do_migration())

    console.print(f"[green]Migration complete![/green]")
    console.print(f"  Preferences: {counts['preferences']}")
    console.print(f"  Provider learnings: {counts['provider_learnings']}")


# =============================================================================
# SEED COMMAND
# =============================================================================

@memory_cmd.command()
@click.argument("seed_file", type=click.Path(exists=True))
@click.option("--level", "-l",
              type=click.Choice(["platform", "org"]),
              default="platform", help="Target level for seeded learnings")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def seed(ctx, seed_file: str, level: str, force: bool):
    """Seed curated learnings from a JSON file

    Seeds platform or org-level learnings from a curated JSON file.
    Platform learnings affect ALL tenants, use with caution.

    \b
    Seed file format:
    {
      "luma": [
        {"category": "avoid", "content": "Abstract concepts"},
        {"category": "prefer", "content": "Concrete objects"}
      ],
      "runway": [...]
    }

    \b
    Examples:
      claude-studio memory seed curated_learnings.json
      claude-studio memory seed org_learnings.json --level org
    """
    from core.memory import NamespaceLevel

    manager = get_manager_with_context(ctx.obj)
    ns_ctx = manager.get_context()

    with open(seed_file) as f:
        seed_data = json.load(f)

    # Count items
    total_items = sum(len(items) for items in seed_data.values())
    providers = list(seed_data.keys())

    console.print(Panel(
        f"[bold]Seed Preview[/bold]\n\n"
        f"Source: {seed_file}\n"
        f"Target level: [{'red' if level == 'platform' else 'yellow'}]{level}[/]\n"
        f"Total items: {total_items}\n"
        f"Providers: {', '.join(providers)}",
        title="Seed Learnings"
    ))

    if level == "platform" and not force:
        console.print("[yellow]Platform seeds affect ALL tenants![/yellow]")

    if not force and not click.confirm("Proceed with seeding?"):
        return

    level_enum = NamespaceLevel(level)

    async def do_seed():
        seeded = 0
        for provider, learnings in seed_data.items():
            for learning in learnings:
                category = learning.get("category", "tip")
                content = learning.get("content") or learning.get("pattern", "")

                await manager.store_provider_learning(
                    provider=provider,
                    learning={"pattern": content, "category": category},
                    level=level_enum,
                    ctx=ns_ctx,
                    tags=[provider, category, "seeded"],
                )
                seeded += 1
        return seeded

    with console.status("Seeding..."):
        seeded = asyncio.run(do_seed())

    console.print(f"[green]Seeded {seeded} learnings to {level} level[/green]")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_namespace_level(namespace: str) -> str:
    """Determine level from namespace path"""
    if namespace.startswith("/platform"):
        return "platform"
    elif "/sessions/" in namespace:
        return "session"
    elif "/actor/" in namespace:
        return "user"
    elif namespace.startswith("/org/"):
        return "org"
    return "unknown"
