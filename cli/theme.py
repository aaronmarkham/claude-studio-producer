"""CLI theming system for color customization"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class Theme:
    """CLI color theme configuration"""

    # Primary elements
    header: str = "bold blue"
    agent_name: str = "bold cyan"
    success: str = "bold green"
    warning: str = "yellow"
    error: str = "bold red"

    # Panels/boxes
    panel_border: str = "blue"
    pilot_border: str = "magenta"
    pilot_selected: str = "green"
    scene_border: str = "cyan"
    prompt_border: str = "yellow"
    quality_border: str = "green"
    edit_border: str = "cyan"
    edit_selected: str = "green"

    # Progress bars
    progress_complete: str = "green"
    progress_incomplete: str = "dim white"
    progress_active: str = "cyan"

    # Content
    label: str = "cyan"
    value: str = "white"
    dimmed: str = "dim"
    highlight: str = "bold yellow"

    # Strands/orchestration
    strands_pattern: str = "bold magenta"
    parallel_indicator: str = "yellow"
    sequential_indicator: str = "dim"

    # Status
    approved: str = "bold green"
    rejected: str = "bold red"
    pending: str = "yellow"

    # Stage headers
    stage_header: str = "bold"
    stage_sequential: str = "dim"
    stage_parallel: str = "yellow"


# Preset themes
THEMES = {
    "default": Theme(),

    "ocean": Theme(
        header="bold cyan",
        agent_name="bold blue",
        panel_border="cyan",
        pilot_border="blue",
        pilot_selected="cyan",
        scene_border="blue",
        prompt_border="cyan",
        quality_border="cyan",
        edit_border="blue",
        edit_selected="cyan",
        progress_complete="cyan",
        progress_active="blue",
        strands_pattern="bold blue",
        parallel_indicator="cyan",
        label="blue",
    ),

    "sunset": Theme(
        header="bold yellow",
        agent_name="bold red",
        panel_border="yellow",
        pilot_border="red",
        pilot_selected="yellow",
        scene_border="yellow",
        prompt_border="bright_red",
        quality_border="yellow",
        edit_border="red",
        edit_selected="yellow",
        progress_complete="yellow",
        progress_active="red",
        strands_pattern="bold red",
        parallel_indicator="bright_red",
        highlight="bold bright_red",
        label="yellow",
    ),

    "matrix": Theme(
        header="bold green",
        agent_name="bold green",
        panel_border="green",
        pilot_border="green",
        pilot_selected="bright_green",
        scene_border="green",
        prompt_border="green",
        quality_border="green",
        edit_border="green",
        edit_selected="bright_green",
        progress_complete="green",
        progress_incomplete="dim green",
        progress_active="bright_green",
        strands_pattern="bold green",
        parallel_indicator="bright_green",
        sequential_indicator="dim green",
        label="green",
        value="bright_green",
        dimmed="dim green",
        approved="bold bright_green",
    ),

    "pro": Theme(
        header="bold white",
        agent_name="bold cyan",
        panel_border="dim white",
        pilot_border="dim white",
        pilot_selected="cyan",
        scene_border="dim white",
        prompt_border="dim yellow",
        quality_border="dim green",
        edit_border="dim white",
        edit_selected="cyan",
        progress_complete="cyan",
        progress_active="white",
        strands_pattern="bold magenta",
        label="bold white",
        value="white",
    ),

    "neon": Theme(
        header="bold magenta",
        agent_name="bold cyan",
        panel_border="magenta",
        pilot_border="cyan",
        pilot_selected="bright_magenta",
        scene_border="magenta",
        prompt_border="cyan",
        quality_border="bright_green",
        edit_border="cyan",
        edit_selected="bright_magenta",
        progress_complete="bright_magenta",
        progress_active="cyan",
        strands_pattern="bold cyan",
        parallel_indicator="bright_magenta",
        highlight="bold bright_yellow",
        label="magenta",
    ),

    "mono": Theme(
        header="bold white",
        agent_name="bold white",
        success="bold white",
        warning="white",
        error="bold white",
        panel_border="white",
        pilot_border="white",
        pilot_selected="bold white",
        scene_border="white",
        prompt_border="white",
        quality_border="white",
        edit_border="white",
        edit_selected="bold white",
        progress_complete="white",
        progress_incomplete="dim white",
        progress_active="bold white",
        label="bold white",
        value="white",
        dimmed="dim white",
        highlight="bold white",
        strands_pattern="bold white",
        parallel_indicator="white",
        sequential_indicator="dim white",
        approved="bold white",
        rejected="dim white",
        pending="white",
    ),
}

# Active theme (can be changed at runtime)
_current_theme: Theme = THEMES["default"]


def get_theme() -> Theme:
    """Get the current active theme"""
    return _current_theme


def set_theme(name: str) -> None:
    """Set the active theme by name"""
    global _current_theme
    if name not in THEMES:
        raise ValueError(f"Unknown theme: {name}. Available: {list(THEMES.keys())}")
    _current_theme = THEMES[name]


def list_themes() -> List[str]:
    """List available theme names"""
    return list(THEMES.keys())


def get_default_theme_name() -> str:
    """Get default theme name from environment or 'default'"""
    return os.getenv("CLAUDE_STUDIO_THEME", "default")
