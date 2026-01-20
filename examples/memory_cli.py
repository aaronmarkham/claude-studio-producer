"""
Memory CLI Commands

Provides commands for managing the multi-tenant namespaced memory system:
- List learnings by namespace/level
- Promote learnings between levels
- Clear session learnings
- Migrate from legacy format
- Show statistics
- Manage platform-level curated learnings (admin)
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box
from pathlib import Path
from datetime import datetime
import json
import os

console = Console()


# =============================================================================
# CONTEXT & CONFIG
# =============================================================================

def get_memory_context():
    """Get memory context from environment or defaults"""
    return {
        "org_id": os.environ.get("CLAUDE_STUDIO_ORG_ID", "default"),
        "actor_id": os.environ.get("CLAUDE_STUDIO_ACTOR_ID", "default"),
        "backend": os.environ.get("MEMORY_BACKEND", "local"),
        "storage_path": os.environ.get("MEMORY_PATH", "artifacts/memory"),
    }


def get_manager(ctx_override: dict = None):
    """Get configured memory manager"""
    # Import here to avoid circular deps
    from core.memory.strands_memory import StrandsMemoryManager
    from core.memory.namespace_builder import NamespaceContext
    
    ctx = get_memory_context()
    if ctx_override:
        ctx.update(ctx_override)
    
    return StrandsMemoryManager(
        storage_path=ctx["storage_path"],
        org_id=ctx["org_id"],
        actor_id=ctx["actor_id"],
        backend=ctx["backend"],
    )


# =============================================================================
# MAIN GROUP
# =============================================================================

@click.group()
@click.option("--org", envvar="CLAUDE_STUDIO_ORG_ID", default="default", 
              help="Organization ID")
@click.option("--actor", envvar="CLAUDE_STUDIO_ACTOR_ID", default="default",
              help="Actor (user) ID")
@click.option("--backend", envvar="MEMORY_BACKEND", default="local",
              type=click.Choice(["local", "mem0", "agentcore"]),
              help="Memory backend")
@click.pass_context
def memory(ctx, org: str, actor: str, backend: str):
    """Memory management commands for multi-tenant learning system"""
    ctx.ensure_object(dict)
    ctx.obj["org_id"] = org
    ctx.obj["actor_id"] = actor
    ctx.obj["backend"] = backend


# =============================================================================
# STATS
# =============================================================================

@memory.command("stats")
@click.pass_context
def stats(ctx):
    """Show memory statistics across all namespace levels"""
    manager = get_manager(ctx.obj)
    
    stats = manager.get_stats()
    
    # Build stats panel
    stats_text = f"""[bold]Memory Statistics[/bold]

[cyan]Context[/cyan]
  Organization: {ctx.obj.get('org_id', 'default')}
  Actor: {ctx.obj.get('actor_id', 'default')}
  Backend: {ctx.obj.get('backend', 'local')}
  Session: {manager.session_id}

[cyan]Counts[/cyan]
  Total Namespaces: {stats['total_namespaces']}
  Total Records: {stats['total_records']}
"""
    
    console.print(Panel(stats_text, title="📊 Memory Stats", border_style="blue"))
    
    # Namespace tree
    if stats.get('namespaces'):
        tree = Tree("📁 [bold]Namespace Tree[/bold]")
        
        # Group by level
        platform_node = tree.add("[red]platform[/red] (curated)")
        org_node = tree.add(f"[yellow]org/{ctx.obj.get('org_id')}[/yellow]")
        
        for ns in sorted(stats['namespaces']):
            count = len(manager.store.list_records(ns))
            label = f"{ns} [dim]({count})[/dim]"
            
            if ns.startswith("/platform"):
                platform_node.add(label)
            elif "/actor/" in ns:
                # User level
                if "/sessions/" in ns:
                    org_node.add(f"[blue]{label}[/blue] (session)")
                else:
                    org_node.add(f"[green]{label}[/green] (user)")
            else:
                org_node.add(label)
        
        console.print(tree)


# =============================================================================
# LIST
# =============================================================================

@memory.command("list")
@click.option("--level", "-l", 
              type=click.Choice(["platform", "org", "user", "session", "all"]),
              default="all", help="Namespace level to list")
@click.option("--provider", "-p", help="Filter by provider")
@click.option("--category", "-c", 
              type=click.Choice(["avoid", "prefer", "tip", "pattern", "all"]),
              default="all", help="Filter by learning category")
@click.option("--namespace", "-n", help="Specific namespace to list")
@click.option("--limit", default=50, help="Max records to show")
@click.pass_context
def list_learnings(ctx, level: str, provider: str, category: str, namespace: str, limit: int):
    """List learnings from memory"""
    manager = get_manager(ctx.obj)
    
    if namespace:
        # Direct namespace query
        records = manager.store.list_records(namespace, limit=limit)
        _display_records(records, f"Namespace: {namespace}")
        return
    
    if provider:
        # Get provider learnings across levels
        include_levels = _parse_level(level)
        learnings = manager.get_provider_learnings(
            provider,
            include_platform=("platform" in include_levels),
            include_org=("org" in include_levels),
            include_user=("user" in include_levels),
            include_session=("session" in include_levels),
            categories=[category] if category != "all" else None,
        )
        _display_records(learnings[:limit], f"Provider: {provider} (level: {level})")
        return
    
    # List all namespaces with counts
    all_namespaces = manager.store.list_namespaces()
    
    table = Table(title="All Namespaces", box=box.ROUNDED)
    table.add_column("Level", style="bold", width=10)
    table.add_column("Namespace", style="cyan")
    table.add_column("Records", justify="right", width=8)
    table.add_column("Type", style="dim", width=15)
    
    for ns in sorted(all_namespaces):
        ns_level = _get_namespace_level(ns)
        ns_type = _get_namespace_type(ns)
        count = len(manager.store.list_records(ns))
        
        level_style = {
            "platform": "[red]PLATFORM[/red]",
            "org": "[yellow]ORG[/yellow]",
            "user": "[green]USER[/green]",
            "session": "[blue]SESSION[/blue]",
        }.get(ns_level, ns_level)
        
        table.add_row(level_style, ns, str(count), ns_type)
    
    console.print(table)


def _parse_level(level: str) -> set:
    """Parse level option to set of levels"""
    if level == "all":
        return {"platform", "org", "user", "session"}
    return {level}


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


def _get_namespace_type(namespace: str) -> str:
    """Get type from namespace path"""
    if "/learnings/global" in namespace:
        return "learnings (global)"
    elif "/learnings/provider" in namespace:
        return "learnings (provider)"
    elif "/preferences" in namespace:
        return "preferences"
    elif "/config" in namespace:
        return "config"
    elif "/runs/" in namespace:
        return "run history"
    elif "/shared" in namespace:
        return "shared"
    elif "/context" in namespace:
        return "session context"
    return "other"


def _display_records(records, title: str):
    """Display records in a table"""
    if not records:
        console.print(f"[yellow]No records found for {title}[/yellow]")
        return
    
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("ID", style="dim", width=14)
    table.add_column("Level", width=8)
    table.add_column("Category", width=10)
    table.add_column("Content", width=45, overflow="ellipsis")
    table.add_column("Conf", justify="right", width=5)
    table.add_column("Valid", justify="right", width=5)
    
    for record in records:
        content = record.content.get("content", record.text_content)[:45]
        category = record.content.get("category", "?")
        confidence = f"{record.confidence:.0%}"
        validations = str(record.times_validated)
        level = _get_namespace_level(record.namespace)
        
        # Color by category
        cat_colors = {
            "avoid": "[red]avoid[/red]",
            "prefer": "[green]prefer[/green]",
            "tip": "[blue]tip[/blue]",
            "pattern": "[magenta]pattern[/magenta]",
        }
        cat_display = cat_colors.get(category, category)
        
        # Color by level
        level_colors = {
            "platform": "[red]PLAT[/red]",
            "org": "[yellow]ORG[/yellow]",
            "user": "[green]USER[/green]",
            "session": "[blue]SESS[/blue]",
        }
        level_display = level_colors.get(level, level[:4])
        
        table.add_row(
            record.id[:14],
            level_display,
            cat_display,
            content,
            confidence,
            validations,
        )
    
    console.print(table)


# =============================================================================
# GUIDELINES
# =============================================================================

@memory.command("guidelines")
@click.argument("provider")
@click.option("--level", "-l",
              type=click.Choice(["platform", "org", "user", "session", "all"]),
              default="all", help="Include learnings from this level")
@click.option("--format", "-f", "output_format",
              type=click.Choice(["rich", "json", "prompt"]),
              default="rich", help="Output format")
@click.pass_context
def guidelines(ctx, provider: str, level: str, output_format: str):
    """Show formatted guidelines for a provider"""
    manager = get_manager(ctx.obj)
    
    include_levels = _parse_level(level)
    guidelines = manager.get_provider_guidelines(
        provider,
        include_platform=("platform" in include_levels),
        include_org=("org" in include_levels),
        include_user=("user" in include_levels),
        include_session=("session" in include_levels),
    )
    
    if output_format == "json":
        console.print_json(data=guidelines)
        return
    
    if output_format == "prompt":
        # Format for injection into Claude prompt
        prompt_text = _format_guidelines_for_prompt(provider, guidelines)
        console.print(prompt_text)
        return
    
    # Rich format
    console.print(Panel.fit(
        f"[bold]Provider Guidelines: {provider}[/bold]\n"
        f"[dim]Level: {level}[/dim]",
        title="📋 Guidelines"
    ))
    
    if guidelines.get("avoid"):
        console.print("\n[red bold]❌ MUST AVOID:[/red bold]")
        for item in guidelines["avoid"]:
            if isinstance(item, dict):
                console.print(f"  • {item['content']} [dim](conf: {item.get('confidence', 0):.0%})[/dim]")
            else:
                console.print(f"  • {item}")
    
    if guidelines.get("prefer"):
        console.print("\n[green bold]✓ PREFER:[/green bold]")
        for item in guidelines["prefer"]:
            if isinstance(item, dict):
                console.print(f"  • {item['content']}")
            else:
                console.print(f"  • {item}")
    
    if guidelines.get("tips"):
        console.print("\n[blue bold]💡 TIPS:[/blue bold]")
        for item in guidelines["tips"]:
            if isinstance(item, dict):
                console.print(f"  • {item['content']}")
            else:
                console.print(f"  • {item}")
    
    if not any(guidelines.values()):
        console.print("[yellow]No guidelines found for this provider[/yellow]")


def _format_guidelines_for_prompt(provider: str, guidelines: dict) -> str:
    """Format guidelines for injection into a Claude prompt"""
    lines = [f"## Provider Guidelines for {provider}", ""]
    
    if guidelines.get("avoid"):
        lines.append("### MUST AVOID (these cause failures):")
        for item in guidelines["avoid"][:10]:
            content = item["content"] if isinstance(item, dict) else item
            lines.append(f"- {content}")
        lines.append("")
    
    if guidelines.get("prefer"):
        lines.append("### PREFERRED (these work well):")
        for item in guidelines["prefer"][:10]:
            content = item["content"] if isinstance(item, dict) else item
            lines.append(f"- {content}")
        lines.append("")
    
    if guidelines.get("tips"):
        lines.append("### TIPS:")
        for item in guidelines["tips"][:8]:
            content = item["content"] if isinstance(item, dict) else item
            lines.append(f"- {content}")
    
    return "\n".join(lines)


# =============================================================================
# PROMOTE
# =============================================================================

@memory.command("promote")
@click.argument("record_id")
@click.option("--to", "to_level", 
              type=click.Choice(["user", "org", "platform"]), 
              required=True, help="Target level")
@click.option("--reason", "-r", default="manual", help="Promotion reason")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def promote(ctx, record_id: str, to_level: str, reason: str, force: bool):
    """Promote a learning to a higher namespace level"""
    manager = get_manager(ctx.obj)
    
    # Get the record first
    record = manager.store.get_record(record_id)
    if not record:
        console.print(f"[red]✗ Record not found: {record_id}[/red]")
        return
    
    current_level = _get_namespace_level(record.namespace)
    
    # Validate promotion path
    valid_promotions = {
        "session": ["user", "org", "platform"],
        "user": ["org", "platform"],
        "org": ["platform"],
        "platform": [],
    }
    
    if to_level not in valid_promotions.get(current_level, []):
        console.print(f"[red]✗ Cannot promote from {current_level} to {to_level}[/red]")
        console.print(f"[dim]Valid targets: {valid_promotions.get(current_level, [])}[/dim]")
        return
    
    # Warn for platform promotions
    if to_level == "platform" and not force:
        console.print("[yellow]⚠ Platform promotions affect ALL tenants![/yellow]")
        if not click.confirm("Are you sure?"):
            return
    
    # Show what we're promoting
    console.print(Panel(
        f"[bold]Record:[/bold] {record_id}\n"
        f"[bold]Content:[/bold] {record.content.get('content', '')[:60]}...\n"
        f"[bold]From:[/bold] {current_level} → [bold]To:[/bold] {to_level}\n"
        f"[bold]Current namespace:[/bold] {record.namespace}",
        title="📤 Promotion Preview"
    ))
    
    if not force and not click.confirm("Proceed with promotion?"):
        return
    
    try:
        new_record = manager.promote_learning(
            record_id=record_id,
            to_level=to_level,
            reason=reason,
        )
        
        if new_record:
            console.print(f"[green]✓ Promoted successfully![/green]")
            console.print(f"  New ID: [cyan]{new_record.id}[/cyan]")
            console.print(f"  New namespace: [dim]{new_record.namespace}[/dim]")
        else:
            console.print(f"[red]✗ Promotion failed[/red]")
            
    except PermissionError as e:
        console.print(f"[red]✗ Permission denied: {e}[/red]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")


# =============================================================================
# VALIDATE
# =============================================================================

@memory.command("validate")
@click.argument("text")
@click.option("--provider", "-p", default="luma", help="Provider to validate against")
@click.option("--level", "-l",
              type=click.Choice(["none", "session", "user", "org", "platform", "all"]),
              default="all", help="Validation level")
@click.option("--simplify", is_flag=True, help="Show simplified version")
@click.pass_context
def validate(ctx, text: str, provider: str, level: str, simplify: bool):
    """Validate a prompt against learned constraints"""
    from agents.validator import PromptValidator, ValidationLevel, PromptSimplifier
    
    manager = get_manager(ctx.obj)
    
    # Map level string to ValidationLevel
    level_map = {
        "none": ValidationLevel.NONE,
        "session": ValidationLevel.SESSION,
        "user": ValidationLevel.USER,
        "org": ValidationLevel.ORG,
        "platform": ValidationLevel.PLATFORM,
        "all": ValidationLevel.ALL,
    }
    
    validator = PromptValidator(manager, provider, level_map.get(level, ValidationLevel.ALL))
    
    # Show loaded constraints
    summary = validator.get_constraint_summary()
    console.print(f"[dim]Loaded {summary['avoid_count']} avoid, {summary['prefer_count']} prefer constraints[/dim]")
    console.print(f"[dim]Validation level: {level}[/dim]\n")
    
    # Validate
    result = validator.validate_text(text)
    
    if result.passed:
        console.print("[green]✓ PASSED[/green] - No constraint violations found")
    else:
        console.print(f"[red]✗ FAILED[/red] - {len(result.violations)} violation(s) found\n")
        
        for v in result.violations:
            severity_color = "red" if v.severity == "error" else "yellow"
            level_badge = f"[dim]({_get_namespace_level(v.source_namespace)})[/dim]" if hasattr(v, 'source_namespace') else ""
            console.print(f"  [{severity_color}]• {v.category.upper()}[/{severity_color}] {level_badge}: {v.constraint}")
            console.print(f"    [dim]Found: '{v.matched_text}'[/dim]")
            console.print(f"    [cyan]→ {v.suggestion}[/cyan]")
    
    if simplify and not result.passed:
        simplifier = PromptSimplifier()
        simplified = simplifier.simplify(text, result.violations)
        console.print(f"\n[bold]Simplified version:[/bold]")
        console.print(Panel(simplified, border_style="green"))


# =============================================================================
# CLEAR
# =============================================================================

@memory.command("clear")
@click.option("--level", "-l",
              type=click.Choice(["session", "user"]),
              required=True, help="Level to clear")
@click.option("--session", "-s", help="Specific session ID (for session level)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def clear(ctx, level: str, session: str, force: bool):
    """Clear learnings at a specific level"""
    manager = get_manager(ctx.obj)
    
    if level == "session":
        target_session = session or manager.session_id
        namespace_pattern = f"/org/{ctx.obj['org_id']}/actor/{ctx.obj['actor_id']}/sessions/{target_session}"
        desc = f"session {target_session}"
    else:  # user
        namespace_pattern = f"/org/{ctx.obj['org_id']}/actor/{ctx.obj['actor_id']}/learnings"
        desc = f"user {ctx.obj['actor_id']}"
    
    # Count records
    namespaces = [ns for ns in manager.store.list_namespaces() if ns.startswith(namespace_pattern)]
    total_records = sum(len(manager.store.list_records(ns)) for ns in namespaces)
    
    if total_records == 0:
        console.print(f"[yellow]No records found for {desc}[/yellow]")
        return
    
    console.print(f"[yellow]Will delete {total_records} records from {len(namespaces)} namespace(s)[/yellow]")
    
    if not force and not click.confirm(f"Clear all {level} learnings?"):
        return
    
    # Clear
    if level == "session":
        manager.clear_session_learnings(target_session)
    else:
        manager.clear_user_learnings()
    
    console.print(f"[green]✓ Cleared {desc} learnings[/green]")


# =============================================================================
# MIGRATE
# =============================================================================

@memory.command("migrate")
@click.argument("legacy_path", type=click.Path(exists=True))
@click.option("--to-level", "-l",
              type=click.Choice(["user", "org", "platform"]),
              default="org", help="Target level for migrated learnings")
@click.option("--dry-run", is_flag=True, help="Show what would be migrated")
@click.pass_context
def migrate(ctx, legacy_path: str, to_level: str, dry_run: bool):
    """Migrate from legacy long_term.json format"""
    manager = get_manager(ctx.obj)
    
    with open(legacy_path) as f:
        legacy = json.load(f)
    
    # Analyze what will be migrated
    stats = {
        "preferences": len(legacy.get("preferences", {})),
        "provider_learnings": 0,
        "run_history": len(legacy.get("production_history", [])),
    }
    
    for provider, knowledge in legacy.get("provider_knowledge", {}).items():
        stats["provider_learnings"] += len(knowledge.get("avoid_list", []))
        stats["provider_learnings"] += len(knowledge.get("prompt_tips", []))
        stats["provider_learnings"] += len(knowledge.get("known_strengths", []))
        stats["provider_learnings"] += len(knowledge.get("recent_learnings", []))
    
    console.print(Panel(
        f"[bold]Migration Preview[/bold]\n\n"
        f"Source: {legacy_path}\n"
        f"Target level: {to_level}\n\n"
        f"Preferences: {stats['preferences']}\n"
        f"Provider learnings: {stats['provider_learnings']}\n"
        f"Run history: {stats['run_history']}",
        title="📦 Migration"
    ))
    
    if dry_run:
        console.print("[yellow]Dry run - no changes made[/yellow]")
        return
    
    if not click.confirm("Proceed with migration?"):
        return
    
    # Do migration
    from core.memory.strands_memory import migrate_from_legacy_ltm
    
    with console.status("Migrating..."):
        counts = migrate_from_legacy_ltm(legacy_path, manager, to_level=to_level)
    
    console.print(f"[green]✓ Migration complete![/green]")
    console.print(f"  Preferences: {counts['preferences']}")
    console.print(f"  Provider learnings: {counts['provider_learnings']}")


# =============================================================================
# TREE (Debug)
# =============================================================================

@memory.command("tree")
@click.option("--provider", "-p", default="luma", help="Provider for examples")
@click.pass_context
def tree(ctx, provider: str):
    """Show the full namespace tree structure"""
    from core.memory.namespace_builder import MultiTenantNamespaceBuilder, NamespaceContext
    
    ns_ctx = NamespaceContext(
        org_id=ctx.obj.get("org_id", "default"),
        actor_id=ctx.obj.get("actor_id", "default"),
        session_id="current_session",
    )
    
    console.print(Panel.fit(
        f"Org: [cyan]{ns_ctx.org_id}[/cyan]\n"
        f"Actor: [cyan]{ns_ctx.actor_id}[/cyan]\n"
        f"Provider: [cyan]{provider}[/cyan]",
        title="🌳 Namespace Tree"
    ))
    
    ns = MultiTenantNamespaceBuilder
    
    tree = Tree("/")
    
    # Platform
    platform = tree.add("[red bold]platform[/red bold] (curated, cross-tenant)")
    platform.add(f"learnings/global")
    platform.add(f"learnings/provider/{provider}")
    platform.add("config")
    
    # Org
    org = tree.add(f"[yellow bold]org/{ns_ctx.org_id}[/yellow bold]")
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
    session = actor.add(f"[blue bold]sessions/{ns_ctx.session_id}[/blue bold]")
    session.add("learnings")
    session.add("context")
    
    console.print(tree)
    
    console.print("\n[bold]Retrieval Priority (high → low):[/bold]")
    for ns_info in ns.get_retrieval_namespaces(provider, ns_ctx):
        bar = "█" * int(ns_info['priority'] * 10)
        console.print(f"  [{ns_info['priority']:.2f}] {bar} {ns_info['namespace']}")


# =============================================================================
# EXPORT
# =============================================================================

@memory.command("export")
@click.option("--output", "-o", default="memory_export.json", help="Output file")
@click.option("--level", "-l",
              type=click.Choice(["all", "platform", "org", "user"]),
              default="user", help="Levels to export")
@click.pass_context
def export(ctx, output: str, level: str):
    """Export memory to JSON file"""
    manager = get_manager(ctx.obj)
    
    # Gather data based on level
    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "context": {
            "org_id": ctx.obj.get("org_id"),
            "actor_id": ctx.obj.get("actor_id"),
            "level": level,
        },
        "namespaces": {},
    }
    
    for ns in manager.store.list_namespaces():
        ns_level = _get_namespace_level(ns)
        
        # Filter by requested level
        if level == "all":
            include = True
        elif level == "platform":
            include = ns_level == "platform"
        elif level == "org":
            include = ns_level in ("platform", "org")
        else:  # user
            include = ns_level in ("platform", "org", "user", "session")
        
        if include:
            records = manager.store.list_records(ns)
            export_data["namespaces"][ns] = [r.to_dict() for r in records]
    
    with open(output, "w") as f:
        json.dump(export_data, f, indent=2, default=str)
    
    total_records = sum(len(r) for r in export_data["namespaces"].values())
    console.print(f"[green]✓ Exported {total_records} records to {output}[/green]")


# =============================================================================
# SEED (Admin - populate platform learnings)
# =============================================================================

@memory.command("seed")
@click.argument("seed_file", type=click.Path(exists=True))
@click.option("--level", "-l",
              type=click.Choice(["platform", "org"]),
              default="platform", help="Target level")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def seed(ctx, seed_file: str, level: str, force: bool):
    """Seed curated learnings from a JSON file (admin)"""
    manager = get_manager(ctx.obj)
    
    with open(seed_file) as f:
        seed_data = json.load(f)
    
    # Count items
    total_items = sum(len(items) for items in seed_data.values())
    
    console.print(Panel(
        f"[bold]Seed Preview[/bold]\n\n"
        f"Source: {seed_file}\n"
        f"Target level: [{'red' if level == 'platform' else 'yellow'}]{level}[/]\n"
        f"Total items: {total_items}",
        title="🌱 Seed Learnings"
    ))
    
    if level == "platform" and not force:
        console.print("[yellow]⚠ Platform seeds affect ALL tenants![/yellow]")
    
    if not force and not click.confirm("Proceed with seeding?"):
        return
    
    # Seed each provider
    seeded = 0
    for provider, learnings in seed_data.items():
        for learning in learnings:
            manager.record_provider_learning(
                provider=provider,
                learning_type=learning.get("category", "tip"),
                content=learning.get("content"),
                evidence=learning.get("evidence", []),
                severity=learning.get("severity", "medium"),
                promote_to_level=level,
            )
            seeded += 1
    
    console.print(f"[green]✓ Seeded {seeded} learnings to {level} level[/green]")


# =============================================================================
# REGISTER
# =============================================================================

def register_memory_commands(cli):
    """Register memory commands with main CLI"""
    cli.add_command(memory)


if __name__ == "__main__":
    memory()
