"""Display utilities for video production pipeline.

Rich console formatting: headers, tables, budgets, asset summaries.
"""

from collections import Counter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


console = Console()

def _get_theme():
    from cli.theme import get_theme
    return get_theme()

def print_header(title: str, subtitle: str = ""):
    """Print header panel"""
    t = _get_theme()
    header_text = Text()
    header_text.append("🎬 ", style="bold")
    header_text.append(title, style=t.header)
    if subtitle:
        header_text.append("\n   ", style=t.dimmed)
        header_text.append(subtitle, style="white")

    console.print(Panel(
        header_text,
        border_style=t.panel_border,
        box=box.DOUBLE,
        padding=(0, 2)
    ))
    console.print()


def print_budget_tiers(scenes: list):
    """Print cost comparison for all budget tiers"""
    t = _get_theme()
    from core.video_production import estimate_tier_costs, BUDGET_TIERS

    estimates = estimate_tier_costs(scenes)

    table = Table(
        title="Budget Tier Comparison",
        box=box.ROUNDED,
        border_style=t.panel_border,
        show_header=True
    )
    table.add_column("Tier", style="bold", width=10)
    table.add_column("Description", width=35)
    table.add_column("Images", justify="right", width=8)
    table.add_column("Luma", justify="right", width=6)
    table.add_column("Ken Burns", justify="right", width=10)
    table.add_column("Text Only", justify="right", width=10)
    table.add_column("Est. Cost", justify="right", style="bold", width=10)

    tier_order = ["micro", "low", "medium", "high", "full"]
    for tier_name in tier_order:
        est = estimates[tier_name]
        cost_style = "green" if est["total_cost"] < 3 else "yellow" if est["total_cost"] < 10 else "red"
        table.add_row(
            tier_name.upper(),
            est["description"],
            str(est["dalle_images"]),
            str(est["luma_animations"]) if est["luma_animations"] > 0 else "-",
            str(est["ken_burns"]) if est["ken_burns"] > 0 else "-",
            str(est["text_only"]) if est["text_only"] > 0 else "-",
            f"[{cost_style}]${est['total_cost']:.2f}[/]"
        )

    console.print(table)
    console.print()

    # Show recommendation
    total_scenes = len(scenes)
    if total_scenes <= 30:
        recommended = "medium"
    elif total_scenes <= 60:
        recommended = "low"
    else:
        recommended = "low"

    console.print(f"[{t.label}]Recommendation:[/] For {total_scenes} scenes, consider [bold]{recommended.upper()}[/] tier")
    console.print(f"[{t.dimmed}]  Use --budget {recommended} to apply this tier[/]")
    console.print()


def print_scene_table(scenes: list):
    """Print summary table of scenes by type"""
    t = _get_theme()
    from collections import Counter

    # Count scenes by type
    type_counts = Counter()
    type_animated = Counter()
    type_duration = {}

    for scene in scenes:
        seg_type = scene.segment_type.value if hasattr(scene.segment_type, 'value') else str(scene.segment_type)
        type_counts[seg_type] += 1
        if scene.animation_candidate:
            type_animated[seg_type] += 1
        duration = scene.end_time - scene.start_time
        type_duration[seg_type] = type_duration.get(seg_type, 0) + duration

    table = Table(
        title=f"Scene Summary ({len(scenes)} total)",
        box=box.ROUNDED,
        border_style=t.panel_border
    )
    table.add_column("Segment Type", style=t.label, width=20)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Animated", justify="right", width=10)
    table.add_column("Total Duration", justify="right", width=14)

    for seg_type in sorted(type_counts.keys()):
        count = type_counts[seg_type]
        animated = type_animated.get(seg_type, 0)
        duration = type_duration.get(seg_type, 0)
        table.add_row(
            seg_type,
            str(count),
            f"{animated}" if animated > 0 else "-",
            f"{duration:.1f}s"
        )

    # Total row
    table.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{len(scenes)}[/]",
        f"[bold]{sum(type_animated.values())}[/]",
        f"[bold]{sum(type_duration.values()):.1f}s[/]"
    )

    console.print(table)
    console.print()


def print_asset_summary(visual_plans: list, kb_figure_count: int = 0):
    """Print comprehensive asset generation summary with cost estimates"""
    t = _get_theme()

    # Count assets (respecting budget mode)
    total = len(visual_plans)

    # Count scenes that actually need DALL-E generation
    # - Has a non-empty dalle_prompt AND
    # - Not in text_only, shared, or web_image mode
    dalle_needed = []
    web_image_needed = []
    for p in visual_plans:
        budget_mode = getattr(p, 'budget_mode', None)
        if budget_mode == "text_only" or budget_mode == "shared":
            continue  # No generation needed
        if budget_mode == "web_image":
            web_image_needed.append(p)
            continue  # Wikimedia, not DALL-E
        if not p.dalle_prompt:
            continue  # Empty prompt means no generation
        dalle_needed.append(p)

    # Count by animation type
    luma_scenes = [p for p in visual_plans if p.animate_with_luma]
    ken_burns_scenes = [p for p in visual_plans if p.ken_burns and p.ken_burns.get("enabled")]
    kb_matched = [p for p in dalle_needed if getattr(p, 'kb_figure_path', None)]

    # Count text-only and shared scenes
    text_only_count = len([p for p in visual_plans if getattr(p, 'budget_mode', None) == "text_only"])
    shared_count = len([p for p in visual_plans if getattr(p, 'budget_mode', None) == "shared"])

    # Cost estimates (approximate)
    # DALL-E 3 HD 1792x1024: ~$0.08 per image
    # Luma AI: ~$0.05 per second, avg 5s = $0.25 per video
    dalle_cost_per_image = 0.08
    luma_cost_per_video = 0.25

    # Calculate what needs to be generated
    dalle_to_generate = len(dalle_needed) - len(kb_matched)  # Scenes without KB figures need DALL-E
    luma_to_generate = len(luma_scenes)

    # Build summary table
    table = Table(
        title="Asset Generation Plan",
        box=box.ROUNDED,
        border_style=t.panel_border,
        show_header=True
    )
    table.add_column("Asset Type", style=t.label, width=25)
    table.add_column("From PDF", justify="right", width=12)
    table.add_column("To Generate", justify="right", width=12)
    table.add_column("Est. Cost", justify="right", width=12)

    # KB/PDF figures row
    table.add_row(
        "PDF Figures (seeds)",
        f"[green]{len(kb_matched)}[/]" if kb_matched else "0",
        "-",
        "[green]$0.00[/]"
    )

    # Web images row (Wikimedia Commons - free)
    if web_image_needed:
        table.add_row(
            "Web Images (Wikimedia)",
            "-",
            str(len(web_image_needed)),
            "[green]$0.00[/]"
        )

    # DALL-E images row
    dalle_cost = dalle_to_generate * dalle_cost_per_image
    table.add_row(
        "DALL-E Images",
        "-",
        str(dalle_to_generate),
        f"${dalle_cost:.2f}"
    )

    # Luma animations row
    luma_cost = luma_to_generate * luma_cost_per_video
    # Count how many Luma scenes use KB figures as seeds
    luma_with_kb_seed = len([p for p in luma_scenes if getattr(p, 'kb_figure_path', None)])
    luma_note = f"{luma_to_generate}"
    if luma_with_kb_seed > 0:
        luma_note += f" ({luma_with_kb_seed} w/PDF seed)"
    table.add_row(
        "Luma Animations",
        "-",
        luma_note,
        f"${luma_cost:.2f}"
    )

    # Ken Burns (free, just FFmpeg)
    table.add_row(
        "Ken Burns Effects",
        "-",
        str(len(ken_burns_scenes)),
        "[green]$0.00[/]"
    )

    # Shared images (reuse another scene's image - free)
    if shared_count > 0:
        table.add_row(
            "Shared Images",
            "-",
            f"[cyan]{shared_count}[/]",
            "[green]$0.00[/]"
        )

    # Text-only scenes (no image generation)
    if text_only_count > 0:
        table.add_row(
            "Text Overlay Only",
            "-",
            f"[dim]{text_only_count}[/]",
            "[green]$0.00[/]"
        )

    # Total row
    total_cost = dalle_cost + luma_cost
    generated_assets = dalle_to_generate + luma_to_generate
    table.add_row(
        "[bold]TOTAL[/]",
        f"[bold green]{len(kb_matched)}[/]",
        f"[bold]{generated_assets}[/]",
        f"[bold]${total_cost:.2f}[/]"
    )

    console.print(table)

    # Show budget mode summary if applicable
    if text_only_count > 0 or shared_count > 0:
        console.print(f"\n[{t.dimmed}]Budget optimization: {shared_count} scenes share images, {text_only_count} use text overlays[/]")

    # Show KB figure availability
    if kb_figure_count > 0:
        console.print(f"\n[{t.dimmed}]KB figures available: {kb_figure_count} | Matched to scenes: {len(kb_matched)}[/]")
        if len(kb_matched) < kb_figure_count:
            console.print(f"[{t.dimmed}]({kb_figure_count - len(kb_matched)} KB figures not matched - try lowering match threshold)[/]")

    console.print()


def print_full_scene_list(visual_plans: list, scenes: list = None):
    """Print complete scene list with asset sources"""
    t = _get_theme()

    table = Table(
        title="Complete Scene List",
        box=box.SIMPLE,
        border_style=t.panel_border,
        show_lines=False,
        padding=(0, 1)
    )
    table.add_column("#", style=t.dimmed, width=4)
    table.add_column("Title", width=30)
    table.add_column("Type", style=t.label, width=14)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Visual Source", width=14)
    table.add_column("Animation", width=12)

    fallback_count = 0
    for i, plan in enumerate(visual_plans):
        # Get scene info if available
        title = "-"
        duration = "-"
        seg_type = "-"
        if scenes and i < len(scenes):
            scene = scenes[i]
            # Mark fallback titles with warning color
            if getattr(scene, 'title_is_fallback', False):
                title = f"[yellow]*[/]{scene.title[:26]}..." if len(scene.title) > 26 else f"[yellow]*[/]{scene.title}"
                fallback_count += 1
            else:
                title = scene.title[:28] + "..." if len(scene.title) > 28 else scene.title
            dur = scene.end_time - scene.start_time
            duration = f"{dur:.1f}s"
            # Get segment type (e.g., intro, background, methodology)
            seg_type = scene.segment_type.value if hasattr(scene.segment_type, 'value') else str(scene.segment_type)

        # Determine visual source based on budget allocation
        budget_mode = getattr(plan, 'budget_mode', None)
        if getattr(plan, 'kb_figure_path', None):
            source = "[green]PDF Figure[/]"
        elif budget_mode == "text_only":
            source = "[dim]text only[/]"
        elif budget_mode == "shared":
            # Show which primary scene this shares with
            shares_with = getattr(plan, 'shares_image_with', '?')
            source = f"[dim]shared[/]"
        elif budget_mode == "web_image":
            source = "[cyan]Wikimedia[/]"
        elif budget_mode == "carry_forward":
            source = "[dim]carry fwd[/]"
        elif budget_mode == "primary":
            source = "[yellow]DALL-E[/]"
        else:
            source = "[yellow]DALL-E[/]"

        # Animation type
        if plan.animate_with_luma:
            if getattr(plan, 'kb_figure_path', None):
                anim = "[cyan]Luma+seed[/]"
            else:
                anim = "[cyan]Luma[/]"
        elif plan.ken_burns and plan.ken_burns.get("enabled"):
            anim = "Ken Burns"
        else:
            anim = "-"

        table.add_row(
            str(i + 1),
            title,
            seg_type,
            duration,
            source,
            anim
        )

    console.print(table)

    # Show warning if there are fallback titles (data quality issue)
    if fallback_count > 0:
        console.print(f"[yellow]* {fallback_count} scene(s) have fallback titles (missing key_concepts in training data)[/]")
        console.print(f"[{t.dimmed}]  To re-run training:[/]")
        console.print(f"[{t.dimmed}]    1. Delete checkpoint: del artifacts\\training_output\\checkpoints\\<name>_analysis.json[/]")
        console.print(f"[{t.dimmed}]    2. Re-run: claude-studio training run[/]")

    console.print()
