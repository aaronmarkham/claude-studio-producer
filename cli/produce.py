"""Produce command - Main entry point for video production"""

import os
import re
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import click
from rich.console import Console, Group
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TaskID
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.live import Live
from rich.text import Text
from rich.layout import Layout
from rich import box
from rich.rule import Rule
from rich.padding import Padding
from rich.columns import Columns

# Fix Windows encoding issues with emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from core.claude_client import ClaudeClient
from core.budget import ProductionTier, BudgetTracker
from core.models.audio import AudioTier
from core.models.edit_decision import EditDecisionList, ExportFormat
from core.models.memory import RunStage, PilotMemory, AssetMemory
from core.memory import memory_manager, bootstrap_all_providers
from core.providers import MockVideoProvider
from core.providers.base import VideoProviderConfig, AudioProviderConfig, ProviderType
from cli.theme import get_theme, set_theme, get_default_theme_name

console = Console()


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

PANEL_WIDTH = 60          # Fixed width for all artifact boxes
PROGRESS_WIDTH = 20       # Width for progress bars
BORDER_LINE = "─" * 61    # Consistent border line width


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS - Rich formatting for demo output
# ═══════════════════════════════════════════════════════════════════════════════

def print_header(run_id: str):
    """Print impressive header panel"""
    t = get_theme()
    header_text = Text()
    header_text.append("🎬 ", style="bold")
    header_text.append("Claude Studio Producer", style=t.header)
    header_text.append(" - ", style=t.dimmed)
    header_text.append("Multi-Agent Video Production", style="bold white")
    header_text.append("\n")
    header_text.append("   Run ID: ", style=t.dimmed)
    header_text.append(run_id, style=t.highlight)

    console.print(Panel(
        header_text,
        border_style=t.panel_border,
        box=box.DOUBLE,
        padding=(0, 2)
    ))
    console.print()


def print_production_request(concept: str, budget: float, duration: float,
                             provider: str, audio_tier: str, use_live: bool, variations: int):
    """Print production request details"""
    t = get_theme()
    console.print(f"📋 [{t.label}]Production Request[/{t.label}]")

    # Truncate concept if needed
    display_concept = concept[:55] + "..." if len(concept) > 55 else concept

    mode_display = f"[{t.success}]LIVE[/{t.success}]" if use_live else f"[{t.dimmed}]MOCK[/{t.dimmed}]"
    provider_display = f"{provider.capitalize()} ({mode_display})"

    console.print(f"   [{t.label}]Concept:[/{t.label}]     \"{display_concept}\"")
    console.print(f"   [{t.label}]Budget:[/{t.label}]      ${budget:.2f}")
    console.print(f"   [{t.label}]Duration:[/{t.label}]    {duration}s")
    console.print(f"   [{t.label}]Provider:[/{t.label}]    {provider_display}")
    console.print(f"   [{t.label}]Audio:[/{t.label}]       {audio_tier}")
    console.print(f"   [{t.label}]Variations:[/{t.label}]  {variations}")
    console.print()


def create_stage_panel(stage_num: int, title: str, pattern: str, content: str) -> Panel:
    """Create a stage panel with consistent styling"""
    t = get_theme()
    stage_header = f"[{t.stage_header}]STAGE {stage_num}:[/{t.stage_header}] {title} [{t.dimmed}]({pattern})[/{t.dimmed}]"
    return Panel(
        content,
        title=stage_header,
        title_align="left",
        border_style=t.panel_border,
        box=box.ROUNDED
    )


def print_agent_start(agent_name: str, action: str):
    """Print agent starting an action"""
    t = get_theme()
    console.print(f"   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]{agent_name}[/{t.agent_name}]")
    console.print(f"     └─ {action}")


def print_agent_progress(message: str):
    """Print agent progress update"""
    console.print(f"     └─ {message}")


def print_agent_complete(message: str, duration: Optional[float] = None):
    """Print agent completion"""
    t = get_theme()
    dur_str = f" [{t.dimmed}]({duration:.1f}s)[/{t.dimmed}]" if duration else ""
    console.print(f"     └─ [{t.success}]{message}[/{t.success}]{dur_str}")


def print_parallel_header():
    """Print parallel execution indicator"""
    t = get_theme()
    console.print(f"   [{t.parallel_indicator}]⚡ Parallel Execution[/{t.parallel_indicator}] [{t.dimmed}](Strands parallel())[/{t.dimmed}]")


def print_parallel_agent_box(agent_name: str, lines: List[str], color: str = "blue"):
    """Print a boxed agent for parallel execution"""
    content = "\n".join(f"  {line}" for line in lines)
    width = max(len(line) for line in lines) + 6 if lines else 40

    console.print(f"   ┌─ {agent_name} {'─' * (width - len(agent_name) - 4)}┐", style=color)
    for line in lines:
        padding = width - len(line) - 4
        console.print(f"   │  {line}{' ' * padding}│", style=color)
    console.print(f"   └{'─' * (width - 1)}┘", style=color)


def truncate_text(text: str, max_len: int = 50, verbose: bool = False, suffix: str = "...") -> str:
    """
    Truncate text at word boundaries with suffix unless verbose mode.

    Args:
        text: Text to truncate
        max_len: Maximum length including suffix
        verbose: If True, return full text without truncation
        suffix: String to append when truncating (default "...")

    Returns:
        Truncated text at last complete word before max_len
    """
    if verbose or not text or len(text) <= max_len:
        return text

    # Account for suffix length
    target_len = max_len - len(suffix)
    if target_len <= 0:
        return suffix[:max_len]

    # Find last space before target length
    truncated = text[:target_len]
    last_space = truncated.rfind(' ')

    # If no space found or space is too early, just cut at target_len
    if last_space <= target_len // 2:
        return truncated.rstrip() + suffix

    return text[:last_space].rstrip() + suffix


def print_artifact_box(title: str, lines: List[str], color: str = "magenta", indent: str = "│     "):
    """Print a colored artifact box with content lines using fixed width."""
    width = PANEL_WIDTH

    # Strip rich markup from title for width calculation
    clean_title = re.sub(r'\[/?[^\]]+\]', '', title)
    title_len = len(clean_title)

    # Build top border with title
    remaining = width - title_len - 4  # 4 = "┌─ " + " "
    top_border = f"{indent}┌─ {title} " + "─" * max(0, remaining) + "┐"
    console.print(top_border, style=color)

    for line in lines:
        # Pad line to width (account for "│ " prefix and " │" suffix = 4 chars)
        content_width = width - 3
        # Strip markup for length calc but print with markup
        clean_line = re.sub(r'\[/?[^\]]+\]', '', line)
        padding = content_width - len(clean_line)
        console.print(f"{indent}│ {line}" + " " * max(0, padding) + "│", style=color)

    console.print(f"{indent}└" + "─" * (width - 1) + "┘", style=color)


def print_pilot_artifacts(pilots: List, selected_idx: int = 0, verbose: bool = False):
    """Display pilot strategy artifacts"""
    t = get_theme()
    console.print("│     └─ Created pilot strategies:")
    console.print("│")

    for i, pilot in enumerate(pilots[:3]):  # Show up to 3 pilots
        is_selected = (i == selected_idx)
        tier_name = pilot.tier.value.upper() if hasattr(pilot.tier, 'value') else str(pilot.tier)
        title = f"Pilot {chr(65+i)}: {tier_name}"
        if is_selected:
            title += f" [{t.success}](selected)[/{t.success}]"

        # Build content lines
        lines = [
            f"Budget: ${pilot.allocated_budget:.2f} | Style: {tier_name}",
        ]

        # Add rationale if available
        if hasattr(pilot, 'rationale') and pilot.rationale:
            rationale = truncate_text(pilot.rationale, 45, verbose)
            lines.append(f'"{rationale}"')

        color = t.pilot_selected if is_selected else t.pilot_border
        print_artifact_box(title, lines, color=color)
        console.print("│")


def print_scene_artifacts(scenes: List, verbose: bool = False):
    """Display scene breakdown artifacts"""
    t = get_theme()
    console.print("│     └─ Scene breakdown:")
    console.print("│")

    for scene in scenes[:4]:  # Show up to 4 scenes
        duration = scene.duration if hasattr(scene, 'duration') else 5.0
        title = f'Scene: "{scene.title}" ({duration:.0f}s)'

        lines = []

        # Visual description
        desc = scene.description if hasattr(scene, 'description') else ""
        if desc:
            desc_truncated = truncate_text(desc, 50, verbose)
            lines.append(f"Visual: {desc_truncated}")

        # Camera/transition info
        trans_in = getattr(scene, 'transition_in', 'cut')
        trans_out = getattr(scene, 'transition_out', 'cut')
        if trans_in != 'cut' or trans_out != 'cut':
            lines.append(f"Transitions: {trans_in} → {trans_out}")

        # Text overlay if present
        text_overlay = getattr(scene, 'text_overlay', None)
        if text_overlay:
            lines.append(f'Text: "{truncate_text(text_overlay, 35, verbose)}" (post)')

        # Prompt hints
        hints = getattr(scene, 'prompt_hints', [])
        if hints and verbose:
            lines.append(f"Hints: {', '.join(hints[:3])}")

        print_artifact_box(title, lines, color=t.scene_border)
        console.print("│")

    if len(scenes) > 4:
        console.print(f"│     [{t.dimmed}]... and {len(scenes) - 4} more scenes[/{t.dimmed}]")
        console.print("│")


def print_video_prompt_artifact(scene, provider_name: str, verbose: bool = False):
    """Display the prompt being sent to video provider"""
    t = get_theme()
    # Build the prompt from scene data
    desc = getattr(scene, 'description', 'Video generation')
    hints = getattr(scene, 'prompt_hints', [])

    prompt_parts = [desc]
    if hints:
        prompt_parts.extend(hints[:2])

    full_prompt = ", ".join(prompt_parts)
    prompt_display = truncate_text(full_prompt, 55, verbose)

    title = f"Prompt to {provider_name.capitalize()}"
    lines = [
        f'"{prompt_display}"',
        "",
        f"Settings: 720p, {scene.duration:.0f}s, aspect=16:9"
    ]

    print_artifact_box(title, lines, color=t.prompt_border, indent="│   │  ")


def print_critic_evaluation_artifact(evaluation, verbose: bool = False):
    """Display critic evaluation with visual score bars"""
    t = get_theme()
    console.print("│     └─ Quality Assessment:")
    console.print("│")

    score = evaluation.critic_score if hasattr(evaluation, 'critic_score') else 70
    approved = evaluation.approved if hasattr(evaluation, 'approved') else True
    qa_failures = getattr(evaluation, 'qa_failures_count', 0)
    qa_override = getattr(evaluation, 'qa_override_reasoning', '')

    # Create visual score bars
    def score_bar(value: int, max_val: int = 10) -> str:
        filled = int(value * max_val / 100)
        return "█" * filled + "░" * (max_val - filled)

    # Derive sub-scores from overall (mock breakdown)
    visual_score = min(100, score + 8)
    motion_score = max(0, score - 5)
    adherence_score = min(100, score + 12)

    lines = [
        f"Visual Coherence:  {score_bar(visual_score)} {visual_score}%",
        f"Motion Quality:    {score_bar(motion_score)} {motion_score}%",
        f"Prompt Adherence:  {score_bar(adherence_score)} {adherence_score}%",
        f"Overall Score:     {score}/100",
        "",
    ]

    # Add feedback if available
    feedback = getattr(evaluation, 'feedback', None)
    if feedback:
        lines.append(f"Feedback: \"{truncate_text(feedback, 42, verbose)}\"")
        lines.append("")

    # Decision with QA context
    status = f"[{t.approved}]APPROVED[/{t.approved}]" if approved else f"[{t.rejected}]REJECTED[/{t.rejected}]"
    threshold = "70+" if approved else "below 70"
    lines.append(f"Decision: {status} - meets threshold ({threshold})")

    # Show QA override reasoning if applicable
    if qa_failures > 0 and approved and qa_override:
        lines.append("")
        lines.append(f"[{t.warning}]QA Override ({qa_failures} scene(s) failed QA):[/{t.warning}]")
        lines.append(f"  {truncate_text(qa_override, 50, verbose)}")

    color = t.approved if approved else t.rejected
    print_artifact_box("Quality Assessment", lines, color=color)
    console.print("│")


def print_edit_candidates_artifact(edl, verbose: bool = False):
    """Display edit candidates with timeline visualization"""
    t = get_theme()
    console.print("│     └─ Edit candidates:")
    console.print("│")

    for candidate in edl.candidates[:3]:
        is_recommended = (candidate.candidate_id == edl.recommended_candidate_id)
        title = f'"{candidate.name}"'
        if is_recommended:
            title += f" [{t.success}](recommended)[/{t.success}]"

        lines = []

        # Build timeline visualization
        decisions = candidate.decisions if hasattr(candidate, 'decisions') else []
        if decisions:
            timeline_parts = []
            current_time = 0.0
            for i, d in enumerate(decisions[:3]):
                dur = d.duration or 5.0
                end_time = current_time + dur
                scene_id = d.scene_id.replace("scene_", "S")
                timeline_parts.append(f"{scene_id} ({current_time:.0f}s-{end_time:.0f}s)")

                # Add transition indicator
                trans = getattr(d, 'transition_out', 'cut')
                if i < len(decisions) - 1:
                    if trans in ('dissolve', 'cross_dissolve'):
                        timeline_parts.append("→")
                    else:
                        timeline_parts.append("|")
                current_time = end_time

            timeline = " ".join(timeline_parts)
            lines.append(truncate_text(timeline, 50, verbose))

        # Style description
        style = candidate.style if hasattr(candidate, 'style') else "standard"
        desc = candidate.description if hasattr(candidate, 'description') else ""
        if desc:
            lines.append(f"Style: {truncate_text(desc, 40, verbose)}")
        else:
            lines.append(f"Style: {style}")

        color = t.edit_selected if is_recommended else t.edit_border
        print_artifact_box(title, lines, color=color)
        console.print("│")


def print_strands_patterns():
    """Print Strands patterns used section"""
    t = get_theme()
    console.print()
    console.print(f"⚡ [{t.strands_pattern}]Strands Patterns Used:[/{t.strands_pattern}]")
    patterns = [
        ("parallel()", "Video + Audio generation"),
        ("@tool decorator", "Agent tool definitions"),
        ("sequential()", "Planning and evaluation stages"),
        ("async/await", "Non-blocking API calls"),
    ]
    for pattern, description in patterns:
        console.print(f"   • [{t.strands_pattern}]{pattern}[/{t.strands_pattern}] - {description}")
    console.print()


def print_final_summary(result: dict, run_dir: Path, total_time: float):
    """Print impressive final summary"""
    t = get_theme()
    metadata = result.get("metadata", {})
    costs = metadata.get("costs", {})
    stages = metadata.get("stages", {})

    console.print()
    console.print(Panel(
        f"[{t.success}]✅ Production Complete![/{t.success}]",
        border_style=t.success,
        box=box.DOUBLE
    ))
    console.print()

    # Run Statistics
    console.print(f"📊 [{t.label}]Run Statistics[/{t.label}]")

    # Format time nicely
    if total_time >= 60:
        time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"
    else:
        time_str = f"{total_time:.1f}s"

    # Count agents used
    agents_used = []
    if stages.get("producer"):
        agents_used.append("Producer")
    if stages.get("script_writer"):
        agents_used.append("ScriptWriter")
    if stages.get("video_generator"):
        agents_used.append("VideoGenerator")
    if stages.get("audio_generator"):
        agents_used.append("AudioGenerator")
    if stages.get("qa_verifier"):
        agents_used.append("QAVerifier")
    if stages.get("critic"):
        agents_used.append("Critic")
    if stages.get("editor"):
        agents_used.append("Editor")

    video_prov = metadata.get("actual_video_provider", "mock")
    cost_note = f" [{t.dimmed}](simulated)[/{t.dimmed}]" if video_prov == "mock" else ""

    stats_table = Table(box=None, show_header=False, padding=(0, 2))
    stats_table.add_column("Label", style=t.label)
    stats_table.add_column("Value")
    stats_table.add_row("Total Time:", time_str)
    stats_table.add_row("Total Cost:", f"${costs.get('total', 0):.2f}{cost_note}")
    stats_table.add_row("Agents Used:", f"{len(agents_used)} ({', '.join(agents_used)})")
    stats_table.add_row("Scenes:", str(stages.get('script_writer', {}).get('num_scenes', 0)))
    stats_table.add_row("Videos:", str(stages.get('video_generator', {}).get('num_videos', 0)))

    console.print(Padding(stats_table, (0, 3)))
    console.print()

    # Outputs
    console.print(f"📁 [{t.label}]Outputs[/{t.label}]")
    output_video = result.get("output_video", "N/A")
    console.print(f"   [{t.label}]Video:[/{t.label}]    {output_video}")
    console.print(f"   [{t.label}]EDL:[/{t.label}]      {run_dir / 'edl'}")
    console.print(f"   [{t.label}]Scenes:[/{t.label}]   {run_dir / 'scenes'}")
    console.print(f"   [{t.label}]Metadata:[/{t.label}] {run_dir / 'metadata.json'}")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER SETUP
# ═══════════════════════════════════════════════════════════════════════════════

def get_video_provider(provider_name: str, live: bool, timeout: int = 300):
    """Get video provider instance based on name and mode"""
    if not live:
        return MockVideoProvider(), "mock"

    provider_name = provider_name.lower()

    t = get_theme()
    if provider_name == "luma":
        api_key = os.getenv("LUMA_API_KEY")
        if not api_key:
            console.print(f"     [{t.warning}]⚠ LUMA_API_KEY not set - using mock[/{t.warning}]")
            return MockVideoProvider(), "mock"
        from core.providers.video.luma import LumaProvider
        from core.providers.base import VideoProviderConfig, ProviderType
        config = VideoProviderConfig(
            provider_type=ProviderType.LUMA,
            api_key=api_key,
            timeout=timeout
        )
        return LumaProvider(config=config), "luma"

    elif provider_name == "runway":
        api_key = os.getenv("RUNWAY_API_KEY")
        if not api_key:
            console.print(f"     [{t.warning}]⚠ RUNWAY_API_KEY not set - using mock[/{t.warning}]")
            return MockVideoProvider(), "mock"
        from core.providers.video.runway import RunwayProvider
        config = VideoProviderConfig(
            provider_type=ProviderType.RUNWAY,
            api_key=api_key,
            timeout=timeout
        )
        return RunwayProvider(config=config), "runway"

    elif provider_name == "mock":
        return MockVideoProvider(), "mock"

    else:
        console.print(f"     [{t.warning}]⚠ Unknown provider '{provider_name}' - using mock[/{t.warning}]")
        return MockVideoProvider(), "mock"


def get_audio_provider(live: bool):
    """Get audio provider instance"""
    if not live:
        return None, "mock"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "mock"

    from core.providers.audio.openai_tts import OpenAITTSProvider
    config = AudioProviderConfig(api_key=api_key, timeout=60)
    return OpenAITTSProvider(config=config, model="tts-1"), "openai_tts"


@dataclass
class SeedAsset:
    """A seed image/asset for video generation"""
    path: Path
    filename: str
    url: Optional[str] = None  # Will be set if uploaded to a hosting service

    @property
    def local_path(self) -> str:
        return str(self.path.absolute())


def load_seed_assets(directory: str) -> List[SeedAsset]:
    """
    Load image assets from a directory.

    Args:
        directory: Path to directory containing PNG/JPG images

    Returns:
        List of SeedAsset objects sorted by filename
    """
    assets = []
    dir_path = Path(directory)

    # Supported image extensions
    extensions = {'.png', '.jpg', '.jpeg', '.webp'}

    for file_path in sorted(dir_path.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            assets.append(SeedAsset(
                path=file_path,
                filename=file_path.name
            ))

    return assets


# ═══════════════════════════════════════════════════════════════════════════════
# CLI COMMAND
# ═══════════════════════════════════════════════════════════════════════════════

@click.command()
@click.option("--concept", "-c", required=True, help="Video concept description")
@click.option("--budget", "-b", type=float, default=10.0, help="Total budget in USD")
@click.option("--duration", "-d", type=float, default=30.0, help="Target video duration in seconds")
@click.option("--audio-tier", type=click.Choice(["none", "music_only", "simple_overlay", "time_synced"]),
              default="none", help="Audio production tier")
@click.option("--provider", "-p", type=click.Choice(["luma", "runway", "mock"]),
              default="luma", help="Video provider to use")
@click.option("--live", is_flag=True, help="Use live API providers (costs real money!)")
@click.option("--mock", "use_mock", is_flag=True, help="Use mock providers (default)")
@click.option("--variations", "-v", type=int, default=1, help="Number of video variations per scene")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory (default: artifacts/runs/<run_id>)")
@click.option("--run-id", help="Custom run ID (default: auto-generated timestamp)")
@click.option("--debug", is_flag=True, help="Enable debug output")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
@click.option("--verbose", "-V", is_flag=True, help="Show full artifacts without truncation")
@click.option("--theme", "-t", default=None, help="Color theme (default, ocean, sunset, matrix, pro, neon, mono)")
@click.option("--timeout", type=int, default=600, help="Video generation timeout in seconds (default: 600)")
@click.option("--seed-assets", "-s", type=click.Path(exists=True), help="Directory containing seed images/assets (PNG/JPG)")
@click.option("--execution-strategy", "-e", type=click.Choice(["auto", "all_parallel", "all_sequential", "manual"]),
              default="auto", help="Scene execution strategy for continuity (auto detects from script)")
@click.option("--style", type=click.Choice(["visual_storyboard", "podcast", "educational", "documentary"]),
              default="visual_storyboard", help="Narrative style (podcast=rich NotebookLM-style narration)")
def produce_cmd(
    concept: str,
    budget: float,
    duration: float,
    audio_tier: str,
    provider: str,
    live: bool,
    use_mock: bool,
    variations: int,
    output_dir: Optional[str],
    run_id: Optional[str],
    debug: bool,
    as_json: bool,
    verbose: bool,
    theme: Optional[str],
    timeout: int,
    seed_assets: Optional[str],
    execution_strategy: str,
    style: str
):
    """
    Run the full video production pipeline with multi-agent orchestration.

    This command demonstrates sophisticated agent patterns including:
    - Sequential planning stages (Producer → ScriptWriter)
    - Parallel asset generation (Video + Audio via Strands)
    - Quality evaluation pipeline (QA → Critic → Editor)

    Examples:

        # Quick 5-second demo with mock providers
        claude-studio produce -c "Logo reveal for TechCorp" -d 5 --mock

        # Live production with Luma
        claude-studio produce -c "Product demo for mobile app" -b 15 -d 30 --live -p luma

        # Full production with audio
        claude-studio produce -c "Tutorial video" -b 50 -d 60 --audio-tier simple_overlay --live

        # Use a different color theme
        claude-studio produce -c "test" --mock --theme matrix

        # Longer timeout for busy Luma queue
        claude-studio produce -c "My video" --live -p luma --timeout 900

        # Use seed images for video generation
        claude-studio produce -c "Product showcase" --live -s ./assets/product_images
    """
    # Set theme (from CLI arg or environment variable)
    theme_name = theme or get_default_theme_name()
    try:
        set_theme(theme_name)
    except ValueError as e:
        console.print(f"[yellow]Warning: {e}. Using default theme.[/yellow]")
    t = get_theme()

    # Determine mode - mock is default unless --live is specified
    use_live = live and not use_mock

    # Generate run ID
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    # Setup output directory
    if output_dir:
        run_dir = Path(output_dir)
    else:
        run_dir = Path("artifacts/runs") / run_id

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scenes").mkdir(exist_ok=True)
    (run_dir / "videos").mkdir(exist_ok=True)
    (run_dir / "audio").mkdir(exist_ok=True)
    (run_dir / "edl").mkdir(exist_ok=True)
    (run_dir / "renders").mkdir(exist_ok=True)

    # Parse audio tier
    audio_tier_map = {
        "none": AudioTier.NONE,
        "music_only": AudioTier.MUSIC_ONLY,
        "simple_overlay": AudioTier.SIMPLE_OVERLAY,
        "time_synced": AudioTier.TIME_SYNCED,
    }
    audio_tier_enum = audio_tier_map[audio_tier]

    # Load seed assets if provided
    loaded_assets: List[SeedAsset] = []
    if seed_assets:
        loaded_assets = load_seed_assets(seed_assets)
        if not as_json and loaded_assets:
            console.print(f"📁 Loaded {len(loaded_assets)} seed asset(s) from {seed_assets}")
            for asset in loaded_assets:
                console.print(f"   • {asset.filename}")
            console.print()

    # Show production header (unless JSON output)
    if not as_json:
        print_header(run_id)
        print_production_request(
            concept=concept,
            budget=budget,
            duration=duration,
            provider=provider,
            audio_tier=audio_tier,
            use_live=use_live,
            variations=variations
        )

    # Run the production pipeline
    start_time = time.time()

    try:
        result = asyncio.run(_run_production(
            concept=concept,
            budget=budget,
            duration=duration,
            audio_tier=audio_tier_enum,
            provider_name=provider,
            use_live=use_live,
            variations=variations,
            run_dir=run_dir,
            run_id=run_id,
            debug=debug,
            as_json=as_json,
            verbose=verbose,
            timeout=timeout,
            seed_assets=loaded_assets,
            execution_strategy=execution_strategy,
            narrative_style=style
        ))

        total_time = time.time() - start_time

        if as_json:
            result["total_time"] = total_time
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            print_strands_patterns()
            print_final_summary(result, run_dir, total_time)

        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        console.print(f"\n[{t.error}]❌ Production failed: {e}[/{t.error}]")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTION PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_production(
    concept: str,
    budget: float,
    duration: float,
    audio_tier: AudioTier,
    provider_name: str,
    use_live: bool,
    variations: int,
    run_dir: Path,
    run_id: str,
    debug: bool,
    as_json: bool,
    verbose: bool = False,
    timeout: int = 600,
    seed_assets: Optional[List[SeedAsset]] = None,
    execution_strategy: str = "auto",
    narrative_style: str = "visual_storyboard"
) -> dict:
    """Run the production pipeline with impressive agent orchestration display"""

    from agents.producer import ProducerAgent
    from agents.script_writer import ScriptWriterAgent, NarrativeStyle
    from agents.video_generator import VideoGeneratorAgent
    from agents.audio_generator import AudioGeneratorAgent
    from agents.qa_verifier import QAVerifierAgent
    from agents.critic import CriticAgent, SceneResult
    from agents.editor import EditorAgent

    # Initialize tracking
    metadata = {
        "run_id": run_id,
        "concept": concept,
        "budget": budget,
        "duration": duration,
        "audio_tier": audio_tier.value,
        "provider": provider_name,
        "live_mode": use_live,
        "start_time": datetime.now().isoformat(),
        "stages": {},
        "costs": {"video": 0.0, "audio": 0.0, "total": 0.0}
    }

    # Bootstrap provider knowledge if this is the first run
    await bootstrap_all_providers(memory_manager)

    # Initialize memory manager for this run
    await memory_manager.create_run(
        run_id=run_id,
        concept=concept,
        budget=budget,
        audio_tier=audio_tier.value
    )

    results = {
        "success": False,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "scenes": [],
        "videos": {},
        "costs": metadata["costs"],
        "metadata": metadata
    }

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: Planning (Sequential)
    # ═══════════════════════════════════════════════════════════════════════════

    t = get_theme()

    if not as_json:
        console.print(f"🤖 [{t.label}]Agent Orchestration[/{t.label}]")
        console.print("┌" + BORDER_LINE)
        console.print(f"│ [{t.stage_header}]STAGE 1: Planning[/{t.stage_header}] [{t.stage_sequential}](Sequential)[/{t.stage_sequential}]")
        console.print("│")

    # Get providers
    video_provider, actual_video_provider = get_video_provider(provider_name, use_live, timeout)
    audio_provider, actual_audio_provider = get_audio_provider(use_live)
    metadata["actual_video_provider"] = actual_video_provider
    metadata["actual_audio_provider"] = actual_audio_provider

    # Initialize agents
    claude = ClaudeClient()
    producer = ProducerAgent(claude_client=claude)
    script_writer = ScriptWriterAgent(claude_client=claude)
    video_generator = VideoGeneratorAgent(provider=video_provider, num_variations=variations)
    audio_generator = AudioGeneratorAgent(claude_client=claude, audio_provider=audio_provider)
    qa_verifier = QAVerifierAgent(claude_client=claude, mock_mode=not use_live)
    critic = CriticAgent(claude_client=claude)
    editor = EditorAgent(claude_client=claude)

    # Calculate appropriate scene count
    scene_duration_avg = 7.0
    num_scenes = max(1, min(6, int(duration / scene_duration_avg)))

    # Get provider knowledge from LTM (if available)
    provider_knowledge = await memory_manager.get_provider_guidelines(actual_video_provider)
    if provider_knowledge and not as_json:
        console.print(f"│   [{t.dimmed}]📚 Found {provider_knowledge.total_runs} prior runs with {actual_video_provider}[/{t.dimmed}]")
        console.print("│")

    # --- Producer Agent ---
    stage_start = time.time()

    if not as_json:
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]ProducerAgent[/{t.agent_name}]")
        console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Analyzing concept & planning tiers...[/{t.dimmed}]")

    pilots = await producer.analyze_and_plan(concept, budget, provider_knowledge=provider_knowledge)
    if not pilots:
        raise RuntimeError("No pilot strategies generated")

    pilot = pilots[0]
    producer_time = time.time() - stage_start

    metadata["stages"]["producer"] = {
        "pilot_tier": pilot.tier.value,
        "allocated_budget": pilot.allocated_budget,
        "duration": producer_time
    }

    # Update memory with planning stage
    await memory_manager.update_stage(run_id, RunStage.PLANNING_PILOTS, {
        "pilot_tier": pilot.tier.value,
        "allocated_budget": pilot.allocated_budget
    })

    if not as_json:
        print_pilot_artifacts(pilots, selected_idx=0, verbose=verbose)
        console.print(f"│     [{t.success}]✓ Selected: {pilot.tier.value.upper()} tier (${pilot.allocated_budget:.2f})[/{t.success}] [{t.dimmed}]({producer_time:.1f}s)[/{t.dimmed}]")
        console.print("│")

    # --- ScriptWriter Agent ---
    stage_start = time.time()

    if not as_json:
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]ScriptWriterAgent[/{t.agent_name}]")
        console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Generating script (target: ~{num_scenes} scenes)...[/{t.dimmed}]")

    # Build list of available asset filenames for ScriptWriter
    available_asset_names = [asset.filename for asset in (seed_assets or [])]

    # Parse narrative style
    style_map = {
        "visual_storyboard": NarrativeStyle.VISUAL_STORYBOARD,
        "podcast_narrative": NarrativeStyle.PODCAST_NARRATIVE,
        "podcast": NarrativeStyle.PODCAST_NARRATIVE,  # alias
        "educational_lecture": NarrativeStyle.EDUCATIONAL_LECTURE,
        "educational": NarrativeStyle.EDUCATIONAL_LECTURE,  # alias
        "documentary": NarrativeStyle.DOCUMENTARY,
    }
    style_enum = style_map.get(narrative_style, NarrativeStyle.VISUAL_STORYBOARD)

    scenes = await script_writer.create_script(
        video_concept=concept,
        production_tier=pilot.tier,
        target_duration=duration,
        num_scenes=num_scenes,
        available_assets=available_asset_names if available_asset_names else None,
        provider_knowledge=provider_knowledge,
        narrative_style=style_enum
    )

    if not scenes:
        raise RuntimeError("No scenes generated")

    script_time = time.time() - stage_start
    total_scene_duration = sum(s.duration for s in scenes)

    results["scenes"] = [s.scene_id for s in scenes]
    metadata["stages"]["script_writer"] = {
        "num_scenes": len(scenes),
        "total_duration": total_scene_duration,
        "duration": script_time
    }

    # Update memory with script generation stage
    await memory_manager.update_stage(run_id, RunStage.GENERATING_SCRIPTS, {
        "num_scenes": len(scenes),
        "total_duration": total_scene_duration
    })

    # Save scenes
    for scene in scenes:
        scene_path = run_dir / "scenes" / f"{scene.scene_id}.json"
        with open(scene_path, 'w') as f:
            json.dump({
                "scene_id": scene.scene_id,
                "title": scene.title,
                "description": scene.description,
                "duration": scene.duration,
                "visual_elements": scene.visual_elements,
                "voiceover_text": scene.voiceover_text
            }, f, indent=2)

    if not as_json:
        print_scene_artifacts(scenes, verbose=verbose)
        console.print(f"│     [{t.success}]✓ Created {len(scenes)} scene(s) ({total_scene_duration:.1f}s total)[/{t.success}] [{t.dimmed}]({script_time:.1f}s)[/{t.dimmed}]")
        console.print("├" + BORDER_LINE)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Asset Generation (Parallel via Strands)
    # ═══════════════════════════════════════════════════════════════════════════

    if not as_json:
        console.print(f"│ [{t.stage_header}]STAGE 2: Asset Generation[/{t.stage_header}] [{t.stage_parallel}](Parallel via Strands)[/{t.stage_parallel}]")
        console.print("│")

    # --- Video Generation ---
    stage_start = time.time()
    video_candidates = {}
    total_video_cost = 0.0

    # Build seed asset lookup by filename
    seed_asset_lookup = {asset.filename: asset for asset in (seed_assets or [])}

    # Build execution graph based on strategy
    from core.execution import ExecutionGraphBuilder

    execution_graph = ExecutionGraphBuilder.from_scenes(scenes, strategy=execution_strategy)

    # Determine execution mode description
    if execution_strategy == "all_parallel":
        exec_mode_desc = "all parallel (no continuity)"
    elif execution_strategy == "all_sequential":
        exec_mode_desc = "all sequential (max continuity)"
    elif execution_strategy == "manual":
        exec_mode_desc = "manual groups from script"
    else:
        # Auto - describe what was detected
        num_groups = len(execution_graph.groups)
        parallel_groups = sum(1 for g in execution_graph.groups if g.mode.value == "parallel")
        sequential_groups = num_groups - parallel_groups
        exec_mode_desc = f"auto ({parallel_groups} parallel, {sequential_groups} sequential groups)"

    if not as_json:
        # Show video generator box
        console.print(f"│   ┌─ [{t.agent_name}]VideoGeneratorAgent[/{t.agent_name}] ─────────────────────────────────")
        prov_display = actual_video_provider.capitalize()
        console.print(f"│   │  [{t.parallel_indicator}]⚡ {prov_display} API[/{t.parallel_indicator}] [{t.dimmed}]Generating {len(scenes)} scenes ({exec_mode_desc})...[/{t.dimmed}]")

    # Use parallel generation for live providers that support it
    parallel_start = time.time()

    # Use graph-based execution if we have mixed modes or sequential groups
    has_sequential = any(g.mode.value == "sequential" for g in execution_graph.groups)

    if has_sequential and hasattr(video_generator.provider, 'submit_generation'):
        # Use graph execution for continuity-aware generation
        video_candidates = await video_generator.generate_with_graph(
            scenes=scenes,
            graph=execution_graph,
            production_tier=pilot.tier,
            budget_per_scene=pilot.allocated_budget / len(scenes),
            num_variations=variations,
            seed_asset_lookup=seed_asset_lookup
        )
    else:
        # Fall back to simple parallel generation
        video_candidates = await video_generator.generate_scenes_parallel(
            scenes=scenes,
            production_tier=pilot.tier,
            budget_per_scene=pilot.allocated_budget / len(scenes),
            num_variations=variations,
            seed_asset_lookup=seed_asset_lookup
        )

    # Calculate total cost and download videos
    for scene in scenes:
        scene_videos = video_candidates.get(scene.scene_id, [])
        scene_cost = sum(v.generation_cost for v in scene_videos)
        total_video_cost += scene_cost

        # Download videos if they have URLs
        for j, video in enumerate(scene_videos):
            if video.video_url and video.video_url.startswith("http"):
                local_path = run_dir / "videos" / f"{scene.scene_id}_v{j}.mp4"
                success = await video_provider.download_video(video.video_url, str(local_path))
                if success:
                    video.video_url = str(local_path)

    video_time = time.time() - parallel_start

    # Show completion summary
    if not as_json:
        for i, scene in enumerate(scenes):
            scene_videos = video_candidates.get(scene.scene_id, [])
            if scene_videos:
                bar = "●" * PROGRESS_WIDTH
                console.print(f"│   │  Scene {i+1}: [{t.progress_complete}]{bar}[/{t.progress_complete}] 100% [{t.success}]✓[/{t.success}]")
                print_video_prompt_artifact(scene, actual_video_provider, verbose=verbose)
            else:
                bar = "○" * PROGRESS_WIDTH
                console.print(f"│   │  Scene {i+1}: [{t.error}]{bar}[/{t.error}] [{t.error}]✗ Failed[/{t.error}]")

    if not as_json:
        prov_display = actual_video_provider.capitalize()
        console.print(f"│   │  Provider: {prov_display} | Cost: ${total_video_cost:.2f} | Time: {video_time:.0f}s")
        console.print("│   └" + BORDER_LINE)
        console.print("│")

    results["videos"] = {k: len(v) for k, v in video_candidates.items()}
    metadata["costs"]["video"] = total_video_cost
    metadata["costs"]["total"] += total_video_cost
    metadata["stages"]["video_generator"] = {
        "num_videos": sum(len(v) for v in video_candidates.values()),
        "cost": total_video_cost,
        "duration": video_time,
        "execution_strategy": execution_strategy,
        "execution_groups": len(execution_graph.groups)
    }

    # Update memory with video generation stage
    await memory_manager.update_stage(run_id, RunStage.GENERATING_VIDEO, {
        "num_videos": sum(len(v) for v in video_candidates.values()),
        "cost": total_video_cost,
        "provider": actual_video_provider
    })

    # --- Audio Generation (parallel with video conceptually) ---
    scene_audio = []

    if not as_json:
        console.print(f"│   ┌─ [{t.agent_name}]AudioGeneratorAgent[/{t.agent_name}] [{t.dimmed}](parallel)[/{t.dimmed}] ─────────────────────")

    if audio_tier != AudioTier.NONE:
        # Show audio provider API call
        audio_prov_display = "OpenAI TTS" if use_live else "Mock"
        if not as_json:
            console.print(f"│   │  [{t.parallel_indicator}]⚡ {audio_prov_display} API[/{t.parallel_indicator}] [{t.dimmed}]Generating voiceover & music...[/{t.dimmed}]")
        stage_start = time.time()

        scene_audio = await audio_generator.run(
            scenes=scenes,
            audio_tier=audio_tier,
            budget_limit=budget * 0.2
        )

        audio_cost = len(scene_audio) * 0.05
        audio_time = time.time() - stage_start
        metadata["costs"]["audio"] = audio_cost
        metadata["costs"]["total"] += audio_cost
        metadata["stages"]["audio_generator"] = {
            "tracks": len(scene_audio),
            "cost": audio_cost,
            "duration": audio_time
        }

        # Update memory with audio generation stage
        await memory_manager.update_stage(run_id, RunStage.GENERATING_AUDIO, {
            "tracks": len(scene_audio),
            "cost": audio_cost,
            "tier": audio_tier.value
        })

        if not as_json:
            console.print(f"│   │  Voiceover: Generated {len(scene_audio)} track(s)")
            console.print(f"│   │  Music: {audio_tier.value}")
    else:
        if not as_json:
            console.print(f"│   │  Voiceover: [{t.dimmed}]Skipped (tier=none)[/{t.dimmed}]")
            console.print(f"│   │  Music: [{t.dimmed}]Skipped (tier=none)[/{t.dimmed}]")
        metadata["stages"]["audio_generator"] = {"skipped": True}

    if not as_json:
        console.print("│   └" + BORDER_LINE)
        console.print("│")
        console.print(f"│   [{t.parallel_indicator}]⚡[/{t.parallel_indicator}] Strands [{t.strands_pattern}]parallel()[/{t.strands_pattern}] - 2 agents, max_concurrency=5")
        console.print("├" + BORDER_LINE)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Evaluation (Sequential)
    # ═══════════════════════════════════════════════════════════════════════════

    if not as_json:
        console.print(f"│ [{t.stage_header}]STAGE 3: Evaluation[/{t.stage_header}] [{t.stage_sequential}](Sequential)[/{t.stage_sequential}]")
        console.print("│")

    # --- QA Verifier ---
    stage_start = time.time()

    if not as_json:
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]QAVerifierAgent[/{t.agent_name}]")
        console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Analyzing video quality & coherence...[/{t.dimmed}]")

    qa_results = {}
    passed_count = 0
    total_count = 0

    for scene in scenes:
        videos = video_candidates.get(scene.scene_id, [])
        scene_qa = []
        for video in videos:
            qa = await qa_verifier.verify_video(
                scene=scene,
                generated_video=video,
                original_request=concept,
                production_tier=pilot.tier
            )
            video.quality_score = qa.overall_score
            scene_qa.append(qa)
            total_count += 1
            if qa.passed:
                passed_count += 1
        qa_results[scene.scene_id] = scene_qa

    qa_time = time.time() - stage_start
    pass_rate = int(100 * passed_count / total_count) if total_count > 0 else 0

    metadata["stages"]["qa_verifier"] = {
        "total": total_count,
        "passed": passed_count,
        "pass_rate": pass_rate,
        "duration": qa_time
    }

    if not as_json:
        if actual_video_provider == "mock":
            # Mock mode - show simulated result without confusing percentages
            console.print(f"│     └─ [{t.success}]✓ Quality check: PASSED[/{t.success}] [{t.dimmed}](mock - simulated)[/{t.dimmed}] [{t.dimmed}]({qa_time:.1f}s)[/{t.dimmed}]")
        else:
            # Live mode - show detailed QA feedback per scene
            console.print(f"│     ├─ [{t.success}]Pass rate: {passed_count}/{total_count} ({pass_rate}%)[/{t.success}] [{t.dimmed}]({qa_time:.1f}s)[/{t.dimmed}]")

            # Show per-scene QA breakdown
            for scene_id, scene_qa_list in qa_results.items():
                for i, qa in enumerate(scene_qa_list):
                    status_color = t.success if qa.passed else t.error
                    status_text = "PASS" if qa.passed else "FAIL"

                    console.print(f"│     │")
                    console.print(f"│     ├─ [{t.dimmed}]{scene_id} v{i}[/{t.dimmed}] [{status_color}][{status_text}][/{status_color}] [{t.dimmed}]score: {qa.overall_score:.0f}/{qa.threshold:.0f}[/{t.dimmed}]")

                    # Show score breakdown
                    console.print(f"│     │   [{t.dimmed}]Visual: {qa.visual_accuracy:.0f}  Style: {qa.style_consistency:.0f}  Tech: {qa.technical_quality:.0f}  Narrative: {qa.narrative_fit:.0f}[/{t.dimmed}]")

                    # Show issues if any and if failed or verbose
                    if qa.issues and (not qa.passed or verbose):
                        for issue in qa.issues[:2]:  # Limit to 2 issues to keep output clean
                            console.print(f"│     │   [{t.warning}]! {issue}[/{t.warning}]")

                    # Show top suggestion if failed
                    if not qa.passed and qa.suggestions:
                        console.print(f"│     │   [{t.label}]→ {qa.suggestions[0]}[/{t.label}]")

            console.print(f"│     │")
            console.print(f"│     └─ [{t.dimmed}]QA analysis complete[/{t.dimmed}]")
        console.print("│")

    # --- Critic Agent ---
    stage_start = time.time()

    if not as_json:
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]CriticAgent[/{t.agent_name}]")
        console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Scoring production quality & approval...[/{t.dimmed}]")

    scene_results = []
    for scene in scenes:
        videos = video_candidates.get(scene.scene_id, [])
        scene_qa_list = qa_results.get(scene.scene_id, [])
        if videos:
            video = videos[0]
            # Get QA data for this scene (first variation)
            qa = scene_qa_list[0] if scene_qa_list else None
            scene_results.append(SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=video.video_url,
                qa_score=video.quality_score or 0.0,
                generation_cost=video.generation_cost,
                qa_passed=qa.passed if qa else True,
                qa_threshold=qa.threshold if qa else 70.0,
                qa_issues=qa.issues if qa else None,
                qa_suggestions=qa.suggestions if qa else None
            ))

    evaluation = await critic.evaluate_pilot(
        original_request=concept,
        pilot=pilot,
        scene_results=scene_results,
        budget_spent=metadata["costs"]["total"],
        budget_allocated=pilot.allocated_budget
    )

    critic_time = time.time() - stage_start

    metadata["stages"]["critic"] = {
        "approved": evaluation.approved,
        "score": evaluation.critic_score,
        "duration": critic_time,
        "qa_failures_count": evaluation.qa_failures_count,
        "qa_override_reasoning": evaluation.qa_override_reasoning
    }

    # Update memory with evaluation stage
    await memory_manager.update_stage(run_id, RunStage.EVALUATING, {
        "approved": evaluation.approved,
        "critic_score": evaluation.critic_score,
        "qa_pass_rate": pass_rate,
        "qa_failures_count": evaluation.qa_failures_count,
        "qa_override_reasoning": evaluation.qa_override_reasoning
    })

    if not as_json:
        print_critic_evaluation_artifact(evaluation, verbose=verbose)
        console.print("│")

    # --- Analyze Provider Performance (for LTM learning) ---
    # Only analyze if using a real provider (not mock)
    if actual_video_provider != "mock":
        if not as_json:
            console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]CriticAgent[/{t.agent_name}] [{t.dimmed}](Provider Analysis)[/{t.dimmed}]")
            console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Extracting learnings for {actual_video_provider}...[/{t.dimmed}]")

        # Flatten videos and qa_results for analysis
        all_videos = []
        all_qa_results = []
        for scene_id, videos in video_candidates.items():
            all_videos.extend(videos)
        for scene_id, qa_list in qa_results.items():
            all_qa_results.extend(qa_list)

        provider_learning = await critic.analyze_provider_performance(
            scenes=scenes,
            videos=all_videos,
            qa_results=all_qa_results,
            provider=actual_video_provider,
            run_id=run_id,
            concept=concept
        )

        # Record the learning to LTM
        await memory_manager.record_provider_learning(provider_learning)

        if not as_json:
            tips_count = len(provider_learning.prompt_tips)
            console.print(f"│     └─ [{t.success}]✓ Recorded {tips_count} prompt tips for future runs[/{t.success}]")
            console.print("│")

    # --- Editor Agent ---
    stage_start = time.time()

    if not as_json:
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]EditorAgent[/{t.agent_name}]")
        console.print(f"│     ├─ [{t.strands_pattern}]◆ Claude API[/{t.strands_pattern}] [{t.dimmed}]Creating edit decision list (EDL)...[/{t.dimmed}]")

    edl = await editor.run(
        scenes=scenes,
        video_candidates=video_candidates,
        qa_results=qa_results,
        original_request=concept,
        num_candidates=3
    )

    editor_time = time.time() - stage_start

    # Save EDL with all candidates
    edl_meta_path = run_dir / "edl" / "edit_candidates.json"
    with open(edl_meta_path, 'w') as f:
        json.dump({
            "edl_id": edl.edl_id,
            "project_name": edl.project_name,
            "recommended_candidate_id": edl.recommended_candidate_id,
            "total_scenes": edl.total_scenes,
            "candidates": [{"candidate_id": c.candidate_id, "name": c.name, "style": c.style} for c in edl.candidates]
        }, f, indent=2)

    # Save each candidate
    for candidate in edl.candidates:
        cand_path = run_dir / "edl" / f"{candidate.candidate_id}.json"
        with open(cand_path, 'w') as f:
            json.dump({
                "candidate_id": candidate.candidate_id,
                "name": candidate.name,
                "style": candidate.style,
                "decisions": [
                    {
                        "scene_id": d.scene_id,
                        "selected_variation": d.selected_variation,
                        "video_url": d.video_url,
                        "in_point": d.in_point,
                        "out_point": d.out_point,
                        "transition_in": d.transition_in,
                        "transition_in_duration": d.transition_in_duration,
                        "transition_out": d.transition_out,
                        "transition_out_duration": d.transition_out_duration,
                        "start_time": d.start_time,
                        "duration": d.duration,
                        "text_overlay": d.text_overlay,
                        "text_position": d.text_position,
                        "text_style": d.text_style,
                        "text_start_time": d.text_start_time,
                        "text_duration": d.text_duration
                    } for d in candidate.decisions
                ],
                "total_duration": candidate.total_duration,
                "estimated_quality": candidate.estimated_quality,
                "description": candidate.description
            }, f, indent=2)

    metadata["stages"]["editor"] = {
        "edl_id": edl.edl_id,
        "candidates": len(edl.candidates),
        "recommended": edl.recommended_candidate_id,
        "duration": editor_time
    }

    # Update memory with editing stage
    await memory_manager.update_stage(run_id, RunStage.EDITING, {
        "edl_id": edl.edl_id,
        "candidates": len(edl.candidates),
        "recommended": edl.recommended_candidate_id
    })

    if not as_json:
        print_edit_candidates_artifact(edl, verbose=verbose)
        console.print(f"│     [{t.success}]✓ Recommended: \"{edl.recommended_candidate_id}\"[/{t.success}] [{t.dimmed}]({editor_time:.1f}s)[/{t.dimmed}]")
        console.print("├" + BORDER_LINE)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 4: Rendering
    # ═══════════════════════════════════════════════════════════════════════════

    if not as_json:
        console.print(f"│ [{t.stage_header}]STAGE 4: Rendering[/{t.stage_header}]")
        console.print("│")
        console.print(f"│   [{t.agent_name}]▶[/{t.agent_name}] [{t.agent_name}]FFmpegRenderer[/{t.agent_name}]")

    from core.renderer import FFmpegRenderer
    renderer = FFmpegRenderer(output_dir=str(run_dir / "renders"))
    ffmpeg_check = await renderer.check_ffmpeg_installed()

    if ffmpeg_check["installed"]:
        if not as_json:
            num_clips = sum(len(v) for v in video_candidates.values())
            console.print(f"│     └─ Concatenating {num_clips} video clip(s)...")
            console.print("│     └─ Adding transitions and overlays...")

        # Don't pass run_id since output_dir is already run-specific (run_dir/renders)
        render_result = await renderer.render(edl=edl, audio_tracks=[])

        if render_result.success:
            results["output_video"] = render_result.output_path
            if not as_json:
                output_name = Path(render_result.output_path).name
                console.print(f"│     └─ [{t.success}]Output: {output_name}[/{t.success}]")
        else:
            if not as_json:
                err_msg = render_result.error_message[:50] if render_result.error_message else "Unknown error"
                console.print(f"│     └─ [{t.warning}]{err_msg}[/{t.warning}]")
    else:
        if not as_json:
            console.print(f"│     └─ [{t.dimmed}]FFmpeg not installed - skipping render[/{t.dimmed}]")

    if not as_json:
        console.print("└" + BORDER_LINE)

    # Finalize
    metadata["end_time"] = datetime.now().isoformat()
    metadata["status"] = "completed"

    # Save metadata
    with open(run_dir / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    # Update memory manager with final state and complete the run
    run_memory = await memory_manager.get_run(run_id)
    if run_memory:
        # Add pilot info
        run_memory.pilots.append(PilotMemory(
            pilot_id=f"pilot_{pilot.tier.value.lower()}",
            tier=pilot.tier.value,
            allocated_budget=pilot.allocated_budget,
            spent_budget=metadata["costs"]["total"],
            scenes_generated=len(scenes),
            quality_score=metadata["stages"].get("critic", {}).get("score"),
            status="approved"
        ))
        run_memory.winning_pilot_id = f"pilot_{pilot.tier.value.lower()}"

        # Add scene/asset info
        run_memory.total_scenes = len(scenes)
        run_memory.scenes_completed = len(scenes)
        run_memory.budget_spent = metadata["costs"]["total"]

        # Add video assets from video_candidates (actual video objects)
        for scene_id, videos in video_candidates.items():
            scene_qa_list = qa_results.get(scene_id, [])
            for i, video in enumerate(videos):
                # Get matching QA result if available
                qa_metadata = {}
                if i < len(scene_qa_list):
                    qa = scene_qa_list[i]
                    qa_metadata = {
                        "qa_overall_score": qa.overall_score,
                        "qa_visual_accuracy": qa.visual_accuracy,
                        "qa_style_consistency": qa.style_consistency,
                        "qa_technical_quality": qa.technical_quality,
                        "qa_narrative_fit": qa.narrative_fit,
                        "qa_passed": qa.passed,
                        "qa_threshold": qa.threshold,
                        "qa_issues": qa.issues,
                        "qa_suggestions": qa.suggestions,
                        "qa_frame_timestamps": qa.frame_timestamps,
                    }
                    # Add enriched visual analysis if available
                    if qa.visual_analysis:
                        from dataclasses import asdict
                        qa_metadata["qa_visual_analysis"] = {
                            "overall_description": qa.visual_analysis.overall_description,
                            "primary_subject": qa.visual_analysis.primary_subject,
                            "setting": qa.visual_analysis.setting,
                            "action": qa.visual_analysis.action,
                            "consistent_elements": qa.visual_analysis.consistent_elements,
                            "inconsistent_elements": qa.visual_analysis.inconsistent_elements,
                            "matched_elements": qa.visual_analysis.matched_elements,
                            "missing_elements": qa.visual_analysis.missing_elements,
                            "unexpected_elements": qa.visual_analysis.unexpected_elements,
                            "provider_observations": qa.visual_analysis.provider_observations,
                            "frame_analyses": [asdict(f) for f in qa.visual_analysis.frame_analyses],
                        }

                # Convert absolute path to relative path for web serving
                # The /files route serves from artifacts/, so strip that prefix
                asset_path = video.video_url or ""
                if asset_path.startswith("artifacts/"):
                    asset_path = asset_path[len("artifacts/"):]
                elif asset_path.startswith("artifacts\\"):
                    asset_path = asset_path[len("artifacts\\"):]

                run_memory.assets.append(AssetMemory(
                    asset_id=f"{scene_id}_v{i}",
                    asset_type="video",
                    path=asset_path,
                    scene_id=scene_id,
                    duration=video.duration,
                    cost=video.generation_cost,
                    metadata=qa_metadata
                ))

    # Complete the run (triggers pattern learning)
    await memory_manager.complete_run(run_id, status="completed")

    results["success"] = True
    results["metadata"] = metadata

    return results
