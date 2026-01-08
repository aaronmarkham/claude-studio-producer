"""Theme command - List and preview CLI themes"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from cli.theme import THEMES, get_default_theme_name, Theme

console = Console()


def preview_theme(name: str, theme: Theme):
    """Show a preview of a theme's colors"""
    # Create sample output using the theme colors
    lines = Text()
    lines.append("Claude Studio Producer\n", style=theme.header)
    lines.append("├─────────────────────────────────────────────────────────────\n")
    lines.append("│ STAGE 1: Planning\n", style=theme.stage_header)
    lines.append("│\n")
    lines.append("│   ▶ ", style=theme.agent_name)
    lines.append("ProducerAgent\n", style=theme.agent_name)
    lines.append("│     └─ Analyzing request...\n")
    lines.append("│     ", style="")
    lines.append("✓ Selected: STANDARD tier ($2.00)\n", style=theme.success)
    lines.append("│\n")
    lines.append("│   ▶ ", style=theme.agent_name)
    lines.append("ScriptWriterAgent\n", style=theme.agent_name)
    lines.append("│     └─ ", style="")
    lines.append("✓ Created 3 scenes\n", style=theme.success)
    lines.append("├─────────────────────────────────────────────────────────────\n")
    lines.append("│ STAGE 2: Asset Generation ", style=theme.stage_header)
    lines.append("(Parallel)\n", style=theme.stage_parallel)
    lines.append("│\n")
    lines.append("│   ┌─ ", style="")
    lines.append("VideoGeneratorAgent\n", style=theme.agent_name)
    lines.append("│   │  Scene 1: ", style="")
    lines.append("●●●●●●●●●●●●●●●●●●●●", style=theme.progress_complete)
    lines.append(" 100% ", style="")
    lines.append("✓\n", style=theme.success)
    lines.append("│   │  Scene 2: ", style="")
    lines.append("●●●●●●●●●●", style=theme.progress_complete)
    lines.append("○○○○○○○○○○", style=theme.progress_incomplete)
    lines.append(" 50%\n", style="")
    lines.append("│   │  Scene 3: ", style="")
    lines.append("○○○○○○○○○○○○○○○○○○○○", style=theme.progress_incomplete)
    lines.append(" 0%\n", style="")
    lines.append("│   └─────────────────────────────────────────────────────────\n")
    lines.append("│\n")
    lines.append("│   ⚡ ", style=theme.parallel_indicator)
    lines.append("Strands ", style="")
    lines.append("parallel()\n", style=theme.strands_pattern)
    lines.append("└─────────────────────────────────────────────────────────────\n")

    is_default = name == get_default_theme_name()
    title = f" {name.upper()} "
    if is_default:
        title += "(current) "

    console.print(Panel(
        lines,
        title=title,
        border_style=theme.panel_border,
        box=box.ROUNDED,
        width=65
    ))


@click.command()
@click.argument("theme_name", required=False)
@click.option("--list", "-l", "list_themes", is_flag=True, help="List all available themes")
@click.option("--preview", "-p", is_flag=True, help="Preview a theme (or all themes)")
def themes_cmd(theme_name: str, list_themes: bool, preview: bool):
    """
    List and preview CLI color themes.

    \b
    Examples:
        # List all themes
        claude-studio themes --list

        # Preview all themes
        claude-studio themes --preview

        # Preview a specific theme
        claude-studio themes matrix --preview

        # Show theme info
        claude-studio themes matrix

    \b
    To use a theme:
        # Via environment variable
        export CLAUDE_STUDIO_THEME=matrix

        # Via command line option
        claude-studio produce -c "..." --theme matrix
    """
    current = get_default_theme_name()

    # List mode
    if list_themes:
        console.print("\n[bold]Available Themes[/bold]\n")
        table = Table(box=box.ROUNDED)
        table.add_column("Theme", style="cyan")
        table.add_column("Description")
        table.add_column("Current")

        descriptions = {
            "default": "Blue/cyan standard palette",
            "ocean": "Cool blue/cyan tones",
            "sunset": "Warm yellow/red tones",
            "matrix": "Green-on-black terminal style",
            "pro": "Minimal, muted professional",
            "neon": "Vibrant magenta/cyan accents",
            "mono": "Monochrome (accessibility)"
        }

        for name in THEMES:
            is_current = "✓" if name == current else ""
            table.add_row(name, descriptions.get(name, ""), is_current)

        console.print(table)
        console.print(f"\n[dim]Current theme: {current}[/dim]")
        console.print("[dim]Set via CLAUDE_STUDIO_THEME env var or --theme option[/dim]\n")
        return

    # Preview mode
    if preview:
        if theme_name:
            # Preview specific theme
            if theme_name not in THEMES:
                console.print(f"[red]Unknown theme: {theme_name}[/red]")
                console.print(f"Available: {', '.join(THEMES.keys())}")
                return
            preview_theme(theme_name, THEMES[theme_name])
        else:
            # Preview all themes
            console.print("\n[bold]Theme Previews[/bold]\n")
            for name, theme in THEMES.items():
                preview_theme(name, theme)
                console.print()
        return

    # Show specific theme info
    if theme_name:
        if theme_name not in THEMES:
            console.print(f"[red]Unknown theme: {theme_name}[/red]")
            console.print(f"Available: {', '.join(THEMES.keys())}")
            return

        theme = THEMES[theme_name]
        is_current = theme_name == current

        console.print(f"\n[bold]Theme: {theme_name}[/bold]" + (" (current)" if is_current else "") + "\n")

        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column("Property", style="dim")
        table.add_column("Value")
        table.add_column("Preview")

        # Show key properties
        props = [
            ("header", theme.header),
            ("agent_name", theme.agent_name),
            ("success", theme.success),
            ("warning", theme.warning),
            ("error", theme.error),
            ("panel_border", theme.panel_border),
            ("progress_complete", theme.progress_complete),
            ("progress_incomplete", theme.progress_incomplete),
            ("strands_pattern", theme.strands_pattern),
        ]

        for prop, value in props:
            sample = Text("Sample", style=value)
            table.add_row(prop, value, sample)

        console.print(table)
        console.print(f"\n[dim]Use --preview to see a full preview[/dim]\n")
        return

    # Default: list themes
    console.print("\n[bold]Available Themes[/bold]")
    console.print(f"Current: [cyan]{current}[/cyan]\n")
    console.print("  " + ", ".join(THEMES.keys()))
    console.print("\n[dim]Use --list for details or --preview to see previews[/dim]\n")
