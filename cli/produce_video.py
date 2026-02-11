"""Produce Video command - Generate explainer videos from podcast scripts"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich import box

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from cli.theme import get_theme

# Unified Production Architecture imports
from core.models.structured_script import StructuredScript
from core.models.content_library import ContentLibrary, AssetType, AssetStatus
from core.content_librarian import ContentLibrarian
from core.dop import assign_visuals, get_visual_plan_summary

console = Console()


def print_header(title: str, subtitle: str = ""):
    """Print header panel"""
    t = get_theme()
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
    t = get_theme()
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
    t = get_theme()
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
    t = get_theme()

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
    t = get_theme()

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


async def load_training_trial(trial_id: str) -> dict:
    """Load artifacts from a training trial"""
    base_path = Path("artifacts/training_output")

    # Find the trial directory
    trial_dir = None
    for d in base_path.iterdir():
        if d.is_dir() and trial_id in d.name:
            trial_dir = d
            break

    if not trial_dir:
        raise click.ClickException(f"Trial not found: {trial_id}")

    # Load script
    script_files = list(trial_dir.glob("*_script.txt"))
    if not script_files:
        raise click.ClickException(f"No script found in {trial_dir}")

    script_path = script_files[0]
    # Handle various encodings - some scripts may have special characters
    try:
        script_text = script_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        script_text = script_path.read_text(encoding='utf-8', errors='replace')

    # Get the base name for finding analysis
    base_name = script_path.stem.replace("_script", "")

    # Load analysis checkpoint (has aligned segments)
    analysis_path = base_path / "checkpoints" / f"{base_name}_analysis.json"
    if not analysis_path.exists():
        raise click.ClickException(f"Analysis checkpoint not found: {analysis_path}")

    with open(analysis_path, 'r', encoding='utf-8') as f:
        analysis_data = json.load(f)

    # Load knowledge graph checkpoint
    kg_path = base_path / "checkpoints" / f"{base_name}_knowledge_graph.json"
    knowledge_graph = None
    if kg_path.exists():
        with open(kg_path, 'r', encoding='utf-8') as f:
            knowledge_graph = json.load(f)

    # Load structured script if available (new Unified Production Architecture)
    structured_script = None
    structured_script_files = list(trial_dir.glob("*_structured_script.json"))
    if structured_script_files:
        try:
            structured_script = StructuredScript.load(structured_script_files[0])
        except Exception as e:
            # Fall back to legacy mode if structured script can't be loaded
            pass

    return {
        "trial_dir": trial_dir,
        "script_text": script_text,
        "base_name": base_name,
        "aligned_segments": analysis_data.get("aligned_segments", []),
        "structure_profile": analysis_data.get("structure_profile"),
        "style_profile": analysis_data.get("style_profile"),
        "knowledge_graph": knowledge_graph,
        "structured_script": structured_script,  # New: StructuredScript if available
    }


def script_segments_to_aligned(structured_script: StructuredScript):
    """
    Bridge: Convert StructuredScript segments to AlignedSegment objects.

    This enables --script mode by creating AlignedSegments from a parsed script
    without requiring training data. The AlignedSegments feed into segments_to_scenes()
    for the existing video production pipeline.
    """
    from core.training.models import (
        AlignedSegment, TranscriptSegment, SegmentType
    )
    from core.models.structured_script import SegmentIntent

    # Map SegmentIntent → SegmentType (best-effort mapping)
    INTENT_TO_TYPE = {
        SegmentIntent.INTRO: SegmentType.INTRO,
        SegmentIntent.OUTRO: SegmentType.CONCLUSION,
        SegmentIntent.TRANSITION: SegmentType.TRANSITION,
        SegmentIntent.RECAP: SegmentType.CONCLUSION,
        SegmentIntent.CONTEXT: SegmentType.BACKGROUND,
        SegmentIntent.EXPLANATION: SegmentType.METHODOLOGY,
        SegmentIntent.DEFINITION: SegmentType.BACKGROUND,
        SegmentIntent.NARRATIVE: SegmentType.BACKGROUND,
        SegmentIntent.CLAIM: SegmentType.KEY_FINDING,
        SegmentIntent.EVIDENCE: SegmentType.KEY_FINDING,
        SegmentIntent.DATA_WALKTHROUGH: SegmentType.KEY_FINDING,
        SegmentIntent.FIGURE_REFERENCE: SegmentType.FIGURE_DISCUSSION,
        SegmentIntent.ANALYSIS: SegmentType.IMPLICATION,
        SegmentIntent.COMPARISON: SegmentType.METHODOLOGY,
        SegmentIntent.COUNTERPOINT: SegmentType.LIMITATION,
        SegmentIntent.SYNTHESIS: SegmentType.IMPLICATION,
        SegmentIntent.COMMENTARY: SegmentType.TANGENT,
        SegmentIntent.QUESTION: SegmentType.TANGENT,
        SegmentIntent.SPECULATION: SegmentType.IMPLICATION,
    }

    aligned = []
    cumulative_time = 0.0

    for seg in structured_script.segments:
        duration = seg.estimated_duration_sec or (len(seg.text.split()) / 150 * 60)
        seg_type = INTENT_TO_TYPE.get(seg.intent, SegmentType.BACKGROUND)

        transcript_seg = TranscriptSegment(
            segment_id=f"seg_{seg.idx:03d}",
            text=seg.text,
            start_time=cumulative_time,
            end_time=cumulative_time + duration,
            duration=duration,
            segment_type=seg_type.value,
        )

        aligned.append(AlignedSegment(
            segment_id=f"seg_{seg.idx:03d}",
            transcript_segment=transcript_seg,
            segment_type=seg_type,
            key_concepts=seg.key_concepts,
            referenced_figures=[f"figure_{f}" for f in seg.figure_refs],
        ))

        cumulative_time += duration

    return aligned


def reconstruct_aligned_segments(segment_dicts: list):
    """Reconstruct AlignedSegment objects from JSON dicts"""
    from core.training.models import (
        AlignedSegment, TranscriptSegment, SegmentType
    )

    segments = []
    for sd in segment_dicts:
        # Reconstruct TranscriptSegment
        ts_data = sd.get("transcript_segment", {})
        transcript_seg = TranscriptSegment(
            segment_id=ts_data.get("segment_id", ""),
            text=ts_data.get("text", ""),
            start_time=ts_data.get("start_time", 0.0),
            end_time=ts_data.get("end_time", 0.0),
            duration=ts_data.get("duration", 0.0),
            segment_type=ts_data.get("segment_type"),
            linked_atoms=ts_data.get("linked_atoms", [])
        )

        # Parse segment type
        seg_type_str = sd.get("segment_type", "background")
        try:
            seg_type = SegmentType(seg_type_str.lower())
        except ValueError:
            seg_type = SegmentType.BACKGROUND

        segments.append(AlignedSegment(
            segment_id=sd.get("segment_id", ""),
            transcript_segment=transcript_seg,
            primary_atoms=sd.get("primary_atoms", []),
            referenced_figures=sd.get("referenced_figures", []),
            segment_type=seg_type,
            key_concepts=sd.get("key_concepts", []),
            technical_terms=sd.get("technical_terms", []),
            analogies_used=sd.get("analogies_used", []),
            questions_asked=sd.get("questions_asked", []),
            words_per_minute=sd.get("words_per_minute", 0.0),
            density_score=sd.get("density_score", 0.0)
        ))

    return segments


def _match_scene_to_figure(scene, kb_figure_paths: dict, knowledge_graph) -> Optional[str]:
    """
    Match a scene to a KB figure by keyword matching.

    Searches figure atoms in the knowledge graph for matches with scene concepts.
    Returns the path to the best matching figure, or None.
    """
    if not knowledge_graph or not kb_figure_paths:
        return None

    # Build search terms from scene
    search_terms = set()
    for term in scene.key_concepts + scene.technical_terms:
        search_terms.add(term.lower())
        for word in term.lower().split():
            if len(word) > 3:
                search_terms.add(word)

    if not search_terms:
        return None

    # Get atoms dict
    atoms = getattr(knowledge_graph, 'atoms', {})

    best_match_id = None
    best_score = 0

    for atom_id, atom in atoms.items():
        # Check if it's a figure atom
        atom_type = getattr(atom, 'atom_type', None)
        if atom_type is None and isinstance(atom, dict):
            atom_type = atom.get('atom_type')

        type_str = atom_type.value if hasattr(atom_type, 'value') else str(atom_type)
        if type_str != 'figure':
            continue

        # Get caption for matching
        caption = getattr(atom, 'caption', None)
        if caption is None and isinstance(atom, dict):
            caption = atom.get('caption')
        if not caption:
            continue

        # Score by keyword match
        caption_lower = caption.lower()
        score = sum(1 for term in search_terms if term in caption_lower)

        if score > best_score:
            best_score = score
            best_match_id = atom_id

    # Need at least 2 matching terms and the figure must exist in KB
    if best_score >= 2 and best_match_id:
        # Try to find the figure file - atom IDs might differ between training and KB
        # Try exact match first
        if best_match_id in kb_figure_paths:
            return kb_figure_paths[best_match_id]

        # Try matching by figure number suffix (e.g., fig_005)
        suffix = best_match_id.split('_')[-1] if '_' in best_match_id else None
        if suffix:
            for kb_atom_id, path in kb_figure_paths.items():
                if kb_atom_id.endswith(f"_{suffix}"):
                    return path

    return None


def distribute_figures_to_scenes(
    scenes: list,
    visual_plans: list,
    kb_figure_paths: dict,
    allocation: dict = None
) -> int:
    """
    Distribute KB figures to scenes when keyword matching fails.

    Assigns figures to high-importance primary scenes in order.
    Returns count of figures assigned.
    """
    if not kb_figure_paths:
        return 0

    # Sort figures by their index for consistent ordering
    sorted_figures = sorted(kb_figure_paths.items(), key=lambda x: x[0])

    # Find primary scenes (scenes that will generate DALL-E) and score them
    from core.video_production import score_scene_importance

    scene_scores = []
    for i, (scene, plan) in enumerate(zip(scenes, visual_plans)):
        # Skip scenes that already have a figure
        if getattr(plan, 'kb_figure_path', None):
            continue

        # Skip non-primary scenes if budget allocation exists
        if allocation:
            budget_mode = getattr(plan, 'budget_mode', None)
            if budget_mode in ['text_only', 'shared']:
                continue

        # Skip scenes with empty DALL-E prompt (won't be rendered)
        if not plan.dalle_prompt:
            continue

        score = score_scene_importance(scene)
        scene_scores.append((i, scene, plan, score))

    # Sort by importance score (highest first)
    scene_scores.sort(key=lambda x: x[3], reverse=True)

    # Assign figures to top scenes
    figures_assigned = 0
    figure_idx = 0

    for scene_idx, scene, plan, score in scene_scores:
        if figure_idx >= len(sorted_figures):
            break

        # Assign figure to this scene
        fig_id, fig_path = sorted_figures[figure_idx]
        plan.kb_figure_path = fig_path
        figure_idx += 1
        figures_assigned += 1

    return figures_assigned


async def generate_scene_audio(
    scenes: list,
    output_dir: Path,
    console,
    voice_id: str = "pFZP5JQG7iQjIQuC4Bku",  # Lily voice
    live: bool = False,
    script_text: str = None,
    structured_script: "StructuredScript" = None,
    content_library: "ContentLibrary" = None,
) -> dict:
    """
    Generate audio for each scene using ElevenLabs (scene-by-scene to avoid length limits).

    Contract (UNIFIED_PRODUCTION_ARCHITECTURE.md):
    - READS: StructuredScript.segments[].text
    - WRITES: Audio files + registers them in ContentLibrary
    - WRITES: actual_duration_sec back to each segment

    When structured_script is provided (Unified Production Architecture):
    - Iterates over segments[].text (not flat script split by \\n\\n)
    - Uses segment.idx as audio ID for proper alignment
    - Writes actual_duration_sec back to each segment
    - Registers assets in ContentLibrary immediately

    Legacy mode (script_text provided):
    - Splits text by \\n\\n to get paragraphs
    - Uses paragraph index as audio ID

    Returns dict mapping audio_id -> audio_path
    """
    from core.providers.audio.elevenlabs import ElevenLabsProvider
    from core.secrets import get_api_key

    t = get_theme()
    audio_paths = {}

    if not live:
        console.print(f"[{t.dimmed}]Mock mode: Skipping audio generation[/]")
        return audio_paths

    # Check API key
    api_key = get_api_key("ELEVENLABS_API_KEY")
    if not api_key:
        console.print(f"[{t.error}]ELEVENLABS_API_KEY not set - skipping audio[/]")
        return audio_paths

    try:
        audio_provider = ElevenLabsProvider()
    except Exception as e:
        console.print(f"[{t.error}]Failed to initialize ElevenLabs: {e}[/]")
        return audio_paths

    # Create audio directory
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # Prepare librarian for asset registration (Unified Production Architecture)
    librarian = None
    if content_library is not None:
        from core.content_librarian import ContentLibrarian
        librarian = ContentLibrarian(content_library)

    # Priority 1: Use StructuredScript segments (Unified Production Architecture)
    # Priority 2: Use script_text split by paragraphs (legacy)
    # Priority 3: Use scene transcript segments (original transcription)
    audio_items = []  # List of (audio_id, text, segment_idx_or_none)

    if structured_script is not None:
        console.print(f"\n[{t.label}]Generating audio from StructuredScript ({len(structured_script.segments)} segments)...[/]")
        for seg in structured_script.segments:
            if seg.text and len(seg.text.strip()) >= 5:
                audio_items.append((f"audio_{seg.idx:03d}", seg.text, seg.idx))
    elif script_text:
        # Legacy: Split script into paragraphs (double newlines are natural breaks)
        paragraphs = [p.strip() for p in script_text.split('\n\n') if p.strip()]
        console.print(f"\n[{t.label}]Generating audio from script text ({len(paragraphs)} paragraphs)...[/]")
        audio_items = [(f"audio_{i:03d}", para, i) for i, para in enumerate(paragraphs)]
    else:
        console.print(f"\n[{t.label}]Generating scene-by-scene audio...[/]")
        for scene in scenes:
            text = scene.transcript_segment if isinstance(scene.transcript_segment, str) else ""
            if hasattr(scene.transcript_segment, 'text'):
                text = scene.transcript_segment.text
            if text and len(text.strip()) >= 5:
                audio_items.append((scene.scene_id, text, None))

    total_chars = 0
    total_cost = 0.0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console
    ) as progress:
        task = progress.add_task("Generating audio...", total=len(audio_items))

        for audio_id, text, segment_idx in audio_items:
            if not text or len(text.strip()) < 5:
                progress.advance(task)
                continue

            progress.update(task, description=f"Audio: {audio_id[:15]}...")

            try:
                result = await audio_provider.generate_speech(
                    text=text,
                    voice_id=voice_id
                )

                if result.success and result.audio_data:
                    audio_path = audio_dir / f"{audio_id}.mp3"
                    audio_path.write_bytes(result.audio_data)
                    audio_paths[audio_id] = str(audio_path)
                    total_chars += len(text)
                    total_cost += audio_provider.estimate_cost(text)

                    # Get actual audio duration (contract: write actual_duration_sec back)
                    actual_duration = None
                    try:
                        from mutagen.mp3 import MP3
                        audio_info = MP3(str(audio_path))
                        actual_duration = audio_info.info.length
                    except Exception:
                        # Fallback: estimate from text length (~150 wpm)
                        word_count = len(text.split())
                        actual_duration = (word_count / 150) * 60

                    # Write actual_duration_sec back to StructuredScript segment
                    if structured_script is not None and segment_idx is not None:
                        seg = structured_script.get_segment(segment_idx)
                        if seg:
                            seg.actual_duration_sec = actual_duration
                            seg.audio_file = str(audio_path)

                    # Register audio asset in ContentLibrary immediately
                    if librarian is not None and segment_idx is not None:
                        from core.models.content_library import AssetRecord, AssetType, AssetSource, AssetStatus
                        asset = AssetRecord(
                            asset_id=f"aud_{segment_idx:04d}",
                            asset_type=AssetType.AUDIO,
                            source=AssetSource.ELEVENLABS,
                            status=AssetStatus.DRAFT,
                            segment_idx=segment_idx,
                            path=str(audio_path),
                            duration_sec=actual_duration,
                        )
                        librarian.library.register(asset)

            except Exception as e:
                console.print(f"[{t.warning}]Audio failed for {audio_id}: {e}[/]")

            progress.advance(task)

    console.print(f"[{t.success}]Generated {len(audio_paths)} audio clips[/]")
    console.print(f"[{t.dimmed}]Total characters: {total_chars} | Est. cost: ${total_cost:.3f}[/]")

    return audio_paths


async def generate_mock_assets(visual_plans: list, output_dir: Path) -> list:
    """Generate mock assets (placeholder files)"""
    from core.models.video_production import SceneAssets

    assets = []
    for plan in visual_plans:
        # Create mock image path
        image_path = output_dir / f"{plan.scene_id}_concept.png"
        video_path = None

        if plan.animate_with_luma:
            video_path = output_dir / f"{plan.scene_id}_animated.mp4"

        assets.append(SceneAssets(
            scene_id=plan.scene_id,
            image_path=str(image_path),
            video_path=str(video_path) if video_path else None,
            display_start=plan.ken_burns.get("display_start", 0.0) if plan.ken_burns else 0.0,
            display_end=plan.ken_burns.get("display_end", 5.0) if plan.ken_burns else 5.0,
            visual_plan=plan
        ))

    return assets


async def generate_live_assets(
    visual_plans: list,
    output_dir: Path,
    console,
    structured_script: "StructuredScript" = None,
    content_library: "ContentLibrary" = None,
) -> list:
    """
    Generate real assets using DALL-E for images.

    Contract (UNIFIED_PRODUCTION_ARCHITECTURE.md):
    - READS: StructuredScript (with DoP annotations), ContentLibrary
    - WRITES: Image/video files + registers them in ContentLibrary

    When structured_script and content_library are provided (Unified Production Architecture):
    - Calls get_visual_generation_plan() to skip segments with approved assets
    - Registers assets immediately after generation
    - Updates segment.visual_asset_id

    Legacy mode (visual_plans only):
    - Uses SceneVisualPlan objects directly
    - No approved-asset skipping
    """
    from core.models.video_production import SceneAssets
    from core.providers.image.dalle import DalleProvider
    from core.providers.image.wikimedia import WikimediaProvider
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    import shutil

    t = get_theme()
    assets = []

    # Initialize image providers
    dalle = None
    wikimedia = WikimediaProvider()

    try:
        dalle = DalleProvider()
    except ValueError as e:
        console.print(f"[{t.dimmed}]DALL-E not available: {e}[/]")
        console.print(f"[{t.dimmed}]Web image and KB figure modes still active[/]")

    # Prepare librarian for asset registration (Unified Production Architecture)
    librarian = None
    segments_to_skip = set()  # Segment indices with approved assets
    if content_library is not None and structured_script is not None:
        from core.content_librarian import ContentLibrarian
        from core.dop import get_visual_generation_plan
        librarian = ContentLibrarian(content_library)

        # Check for approved assets to skip regeneration (contract requirement)
        gen_plan = get_visual_generation_plan(structured_script, content_library)
        reusable = gen_plan.get("can_reuse", {})
        if reusable:
            segments_to_skip = set(reusable.keys())
            console.print(f"[{t.dimmed}]Skipping {len(segments_to_skip)} segments with approved assets[/]")

    # Count scenes needing generation by type
    scenes_needing_dalle = []
    scenes_needing_web_image = []
    scenes_with_kb_figures = []
    scenes_shared = []

    for plan in visual_plans:
        # Extract segment index from scene_id (format: scene_NNN)
        seg_idx = None
        if plan.scene_id.startswith("scene_"):
            try:
                seg_idx = int(plan.scene_id.split("_")[1])
            except (IndexError, ValueError):
                pass

        # Skip if segment has approved asset
        if seg_idx is not None and seg_idx in segments_to_skip:
            scenes_shared.append(plan)
            continue

        budget_mode = getattr(plan, 'budget_mode', None)
        kb_figure = getattr(plan, 'kb_figure_path', None)

        if budget_mode == 'shared' or budget_mode == 'text_only':
            scenes_shared.append(plan)
        elif kb_figure:
            scenes_with_kb_figures.append(plan)
        elif budget_mode == 'web_image':
            scenes_needing_web_image.append(plan)
        elif plan.dalle_prompt and budget_mode != 'web_image':
            scenes_needing_dalle.append(plan)
        else:
            scenes_shared.append(plan)

    console.print(f"\n[{t.label}]Asset generation plan:[/]")
    console.print(f"  [green]KB figures to copy:[/] {len(scenes_with_kb_figures)}")
    console.print(f"  [cyan]Web images to source:[/] {len(scenes_needing_web_image)} (Wikimedia Commons)")
    console.print(f"  [yellow]DALL-E images to generate:[/] {len(scenes_needing_dalle)}")
    console.print(f"  [dim]Shared/text-only (no generation):[/] {len(scenes_shared)}")
    console.print()

    # Create images subdirectory
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    total_cost = 0.0

    # Copy KB figures
    if scenes_with_kb_figures:
        console.print(f"[{t.label}]Copying KB figures...[/]")
        for plan in scenes_with_kb_figures:
            src = Path(plan.kb_figure_path)
            dst = images_dir / f"{plan.scene_id}.png"
            if src.exists():
                shutil.copy2(src, dst)
                assets.append(SceneAssets(
                    scene_id=plan.scene_id,
                    image_path=str(dst),
                    video_path=None,
                    visual_plan=plan
                ))

                # Register figure asset immediately (Unified Production Architecture)
                if librarian is not None:
                    seg_idx = None
                    if plan.scene_id.startswith("scene_"):
                        try:
                            seg_idx = int(plan.scene_id.split("_")[1])
                        except (IndexError, ValueError):
                            pass
                    if seg_idx is not None:
                        from core.models.content_library import AssetRecord, AssetType, AssetSource, AssetStatus
                        asset = AssetRecord(
                            asset_id=f"fig_{seg_idx:04d}",
                            asset_type=AssetType.FIGURE,
                            source=AssetSource.KB_EXTRACTION,
                            status=AssetStatus.DRAFT,
                            segment_idx=seg_idx,
                            path=str(dst),
                        )
                        librarian.library.register(asset)

                        # Update segment's visual_asset_id
                        if structured_script is not None:
                            seg = structured_script.get_segment(seg_idx)
                            if seg:
                                seg.visual_asset_id = asset.asset_id

        console.print(f"[{t.success}]Copied {len(scenes_with_kb_figures)} KB figures[/]")

    # Source web images from Wikimedia Commons
    if scenes_needing_web_image:
        console.print(f"\n[{t.label}]Sourcing web images from Wikimedia Commons...[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Searching...", total=len(scenes_needing_web_image))

            for plan in scenes_needing_web_image:
                search_query = plan.dalle_prompt  # We stored the search query here
                progress.update(task, description=f"Searching: {search_query[:40]}...")

                result = await wikimedia.generate_image(
                    prompt=search_query,
                    output_dir=str(images_dir),
                    prefer_diagrams=True,
                )

                if result.success and result.image_path:
                    # Rename to standard scene naming
                    src = Path(result.image_path)
                    dst = images_dir / f"{plan.scene_id}.png"
                    if src != dst:
                        shutil.move(str(src), str(dst))
                    image_path = str(dst)

                    assets.append(SceneAssets(
                        scene_id=plan.scene_id,
                        image_path=image_path,
                        video_path=None,
                        visual_plan=plan
                    ))

                    # Register web image asset (Unified Production Architecture)
                    if librarian is not None:
                        seg_idx = None
                        if plan.scene_id.startswith("scene_"):
                            try:
                                seg_idx = int(plan.scene_id.split("_")[1])
                            except (IndexError, ValueError):
                                pass
                        if seg_idx is not None:
                            from core.models.content_library import AssetRecord, AssetType, AssetSource, AssetStatus
                            asset = AssetRecord(
                                asset_id=f"web_{seg_idx:04d}",
                                asset_type=AssetType.IMAGE,
                                source=AssetSource.WEB,
                                status=AssetStatus.DRAFT,
                                segment_idx=seg_idx,
                                path=image_path,
                                generation_prompt=search_query,
                            )
                            librarian.library.register(asset)

                            if structured_script is not None:
                                seg = structured_script.get_segment(seg_idx)
                                if seg:
                                    seg.visual_asset_id = asset.asset_id

                    console.print(f"  [{t.dimmed}]{plan.scene_id}: {result.provider_metadata.get('title', '?')[:50]} ({result.provider_metadata.get('license', '?')})[/]")
                else:
                    console.print(f"  [{t.dimmed}]{plan.scene_id}: no image found, will use carry-forward[/]")

                progress.advance(task)

        web_count = sum(1 for a in assets if a.scene_id in {p.scene_id for p in scenes_needing_web_image})
        console.print(f"[{t.success}]Sourced {web_count} web images (cost: $0.00)[/]")

    # Generate DALL-E images
    if scenes_needing_dalle and dalle is not None:
        console.print(f"\n[{t.label}]Generating DALL-E images...[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Generating...", total=len(scenes_needing_dalle))

            for plan in scenes_needing_dalle:
                progress.update(task, description=f"Generating {plan.scene_id[:20]}...")

                # Generate image
                result = await dalle.generate_image(
                    prompt=plan.dalle_prompt,
                    size="1792x1024",  # Landscape HD
                    quality="hd",
                    style=plan.dalle_style or "natural",
                    download=True
                )

                if result.success:
                    # Move to output directory
                    if result.image_path:
                        src = Path(result.image_path)
                        dst = images_dir / f"{plan.scene_id}.png"
                        shutil.move(str(src), str(dst))
                        image_path = str(dst)
                    else:
                        # Download from URL if not already downloaded
                        import aiohttp
                        dst = images_dir / f"{plan.scene_id}.png"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(result.image_url) as resp:
                                if resp.status == 200:
                                    dst.write_bytes(await resp.read())
                        image_path = str(dst)

                    total_cost += result.cost or 0.08
                    assets.append(SceneAssets(
                        scene_id=plan.scene_id,
                        image_path=image_path,
                        video_path=None,
                        visual_plan=plan
                    ))

                    # Register image asset immediately (Unified Production Architecture)
                    if librarian is not None:
                        seg_idx = None
                        if plan.scene_id.startswith("scene_"):
                            try:
                                seg_idx = int(plan.scene_id.split("_")[1])
                            except (IndexError, ValueError):
                                pass
                        if seg_idx is not None:
                            from core.models.content_library import AssetRecord, AssetType, AssetSource, AssetStatus
                            asset = AssetRecord(
                                asset_id=f"img_{seg_idx:04d}",
                                asset_type=AssetType.IMAGE,
                                source=AssetSource.DALLE,
                                status=AssetStatus.DRAFT,
                                segment_idx=seg_idx,
                                path=image_path,
                                generation_prompt=plan.dalle_prompt,
                            )
                            librarian.library.register(asset)

                            # Update segment's visual_asset_id
                            if structured_script is not None:
                                seg = structured_script.get_segment(seg_idx)
                                if seg:
                                    seg.visual_asset_id = asset.asset_id

                else:
                    console.print(f"[{t.error}]Failed to generate {plan.scene_id}: {result.error_message}[/]")

                progress.advance(task)

        console.print(f"[{t.success}]Generated {len(scenes_needing_dalle)} DALL-E images[/]")
        console.print(f"[{t.dimmed}]Total DALL-E cost: ${total_cost:.2f}[/]")

    # Add placeholder entries for shared scenes (they'll use primary's image)
    for plan in scenes_shared:
        assets.append(SceneAssets(
            scene_id=plan.scene_id,
            image_path=None,  # Will be resolved at render time
            video_path=None,
            visual_plan=plan
        ))

    return assets


def load_kb_figures(project_name: str) -> dict:
    """Load figure paths from a KB project."""
    from cli.kb import _resolve_project, _load_project

    project_dir = _resolve_project(project_name)
    if not project_dir:
        raise click.ClickException(f"KB project not found: {project_name}")

    project = _load_project(project_dir)

    # Build figure path mapping: atom_id -> file path
    figure_paths = {}
    sources_dir = project_dir / "sources"

    if sources_dir.exists():
        for source_dir in sources_dir.iterdir():
            if source_dir.is_dir():
                figures_dir = source_dir / "figures"
                if figures_dir.exists():
                    for fig_file in figures_dir.glob("*.png"):
                        atom_id = fig_file.stem  # filename without extension
                        figure_paths[atom_id] = str(fig_file)

    return {
        "project": project,
        "project_dir": project_dir,
        "figure_paths": figure_paths
    }


async def _produce_video_async(
    from_training: Optional[str],
    script_path: Optional[str],
    output_path: str,
    live: bool,
    style: str,
    kb_project: Optional[str] = None,
    budget_tier: Optional[str] = None,
    show_tiers_only: bool = False,
    scene_limit: Optional[int] = None,
    scene_start: int = 0,
    generate_audio: bool = True,
    voice_id: str = "pFZP5JQG7iQjIQuC4Bku"
):
    """Main async production function"""
    t = get_theme()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print_header("Transcript-Led Video Production", f"Run ID: {run_id}")

    # Load KB figures if specified
    kb_data = None
    if kb_project:
        console.print(f"[{t.label}]Loading KB project:[/] {kb_project}")
        kb_data = load_kb_figures(kb_project)
        console.print(f"[{t.success}]Found {len(kb_data['figure_paths'])} figures in KB[/]")

    # Load input data
    if from_training:
        console.print(f"[{t.label}]Loading training trial:[/] {from_training}")
        trial_data = await load_training_trial(from_training)
        aligned_segment_dicts = trial_data["aligned_segments"]
        console.print(f"[{t.success}]Loaded {len(aligned_segment_dicts)} aligned segments[/]")
        console.print()
    elif script_path:
        # --script mode: parse script file directly (no training required)
        script_file = Path(script_path)
        if not script_file.exists():
            raise click.ClickException(f"Script file not found: {script_path}")

        console.print(f"[{t.label}]Loading script file:[/] {script_file.name}")
        script_text = script_file.read_text(encoding="utf-8")

        # Build StructuredScript from flat text
        structured_script_obj = StructuredScript.from_script_text(
            script_text=script_text,
            trial_id=run_id,
        )
        console.print(f"[{t.success}]Parsed {len(structured_script_obj.segments)} segments from script[/]")

        # Convert to AlignedSegments for the video pipeline
        aligned_segments_list = script_segments_to_aligned(structured_script_obj)
        aligned_segment_dicts = [
            {
                "segment_id": a.segment_id,
                "transcript_segment": {
                    "segment_id": a.transcript_segment.segment_id,
                    "text": a.transcript_segment.text,
                    "start_time": a.transcript_segment.start_time,
                    "end_time": a.transcript_segment.end_time,
                    "duration": a.transcript_segment.duration,
                },
                "segment_type": a.segment_type.value,
                "key_concepts": a.key_concepts,
                "referenced_figures": a.referenced_figures,
            }
            for a in aligned_segments_list
        ]
        # Store structured script in trial_data-like dict for downstream use
        trial_data = {
            "aligned_segments": aligned_segment_dicts,
            "structured_script": structured_script_obj,
        }
        console.print(f"[{t.success}]Loaded {len(aligned_segment_dicts)} aligned segments[/]")
        console.print()
    else:
        raise click.ClickException("Provide --from-training or --script")

    # Reconstruct AlignedSegment objects
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Reconstructing segments...", total=None)
        aligned_segments = reconstruct_aligned_segments(aligned_segment_dicts)
        progress.update(task, description=f"[{t.success}]Reconstructed {len(aligned_segments)} segments")

    # Reconstruct knowledge graph if available
    from core.models.knowledge import KnowledgeGraph
    knowledge_graph = None
    if trial_data.get("knowledge_graph"):
        try:
            knowledge_graph = KnowledgeGraph.from_dict(trial_data["knowledge_graph"])
            console.print(f"[{t.success}]Loaded knowledge graph with {len(knowledge_graph.atoms)} atoms[/]")
        except Exception as e:
            console.print(f"[{t.warning}]Could not load knowledge graph: {e}[/]")

    # Convert to VideoScenes
    from core.video_production import segments_to_scenes, create_visual_plan
    from core.video_production import SEGMENT_VISUAL_MAPPING

    console.print(f"\n[{t.label}]Converting segments to video scenes...[/]")
    all_scenes = segments_to_scenes(aligned_segments, SEGMENT_VISUAL_MAPPING)
    console.print(f"[{t.success}]Created {len(all_scenes)} video scenes[/]\n")

    # Apply scene range if specified (for incremental production)
    if scene_start > 0 or scene_limit:
        end_idx = scene_start + scene_limit if scene_limit else len(all_scenes)
        scenes = all_scenes[scene_start:end_idx]
        console.print(f"[{t.label}]Processing scenes {scene_start+1}-{min(end_idx, len(all_scenes))} of {len(all_scenes)}[/]\n")
    else:
        scenes = all_scenes

    print_scene_table(scenes)

    # Show budget tier comparison (for full set, not slice)
    print_budget_tiers(all_scenes)

    # If --show-tiers flag is set, exit here
    if show_tiers_only:
        console.print(f"[{t.dimmed}]Use --budget <tier> to produce video with selected budget[/]")
        return

    # Check if we have a structured script (Unified Production Architecture)
    structured_script = trial_data.get("structured_script") if (from_training or script_path) else None
    use_dop = structured_script is not None

    if use_dop:
        console.print(f"[{t.success}]Using Unified Production Architecture (DoP)[/]\n")

    # Get budget allocation if tier specified
    allocation = None
    content_library = None  # Will be created if using DoP
    if budget_tier:
        from core.video_production import estimate_tier_costs, select_scenes_for_generation
        estimates = estimate_tier_costs(scenes)
        est = estimates[budget_tier]
        console.print(f"[{t.label}]Selected budget tier:[/] [bold]{budget_tier.upper()}[/]")
        console.print(f"[{t.dimmed}]  {est['dalle_images']} images, {est['luma_animations']} animations, est. ${est['total_cost']:.2f}[/]\n")

        # If using DoP, assign visuals through the DoP module
        if use_dop:
            # Create content library for this run
            content_library = ContentLibrary(project_id=run_id)

            # Register KB figures if available
            if kb_data and kb_data.get("project_dir"):
                librarian = ContentLibrarian(content_library)
                kb_path = kb_data["project_dir"]
                registered_figures = librarian.register_kb_figures(str(kb_path), structured_script)
                if registered_figures:
                    console.print(f"[{t.success}]Registered {len(registered_figures)} KB figures in content library[/]")

            # Use DoP to assign visual modes based on budget tier
            structured_script = assign_visuals(structured_script, content_library, budget_tier)
            dop_summary = get_visual_plan_summary(structured_script)

            console.print(f"[{t.label}]DoP visual assignment:[/]")
            console.print(f"[{t.dimmed}]  Figure sync: {dop_summary['figure_sync']} (KB figures)[/]")
            console.print(f"[{t.dimmed}]  Web image: {dop_summary['web_image']} (Wikimedia Commons)[/]")
            console.print(f"[{t.dimmed}]  DALL-E: {dop_summary['dall_e']}[/]")
            console.print(f"[{t.dimmed}]  Carry forward: {dop_summary['carry_forward']}[/]")
            console.print(f"[{t.dimmed}]  Text only: {dop_summary['text_only']}[/]")
            console.print()
        else:
            # Legacy: Get scene allocation for this tier
            allocation = select_scenes_for_generation(scenes, budget_tier)
            console.print(f"[{t.label}]Scene allocation:[/]")
            console.print(f"[{t.dimmed}]  Image groups: {allocation['group_count']} (shared across {len(scenes)} scenes)[/]")
            console.print(f"[{t.dimmed}]  Luma animations: {len(allocation['luma'])}[/]")
            console.print(f"[{t.dimmed}]  Ken Burns effects: {len(allocation['ken_burns'])}[/]")
            console.print(f"[{t.dimmed}]  Text-only scenes: {len(allocation['text_only'])}[/]")
            console.print()

    # Create visual plans
    console.print(f"[{t.label}]Creating visual plans...[/]")

    style_consistency = {
        "style_suffix": "Style: clean technical illustration, dark background (#1a1a2e), vibrant accent colors.",
        "dalle_style": "natural"
    }

    # Get KB figure paths if available
    kb_figure_paths = kb_data["figure_paths"] if kb_data else {}

    visual_plans = []
    figures_matched = 0

    # Use DoP-based visual planning if structured script is available
    if use_dop and structured_script:
        console.print(f"[{t.dimmed}]Using DoP visual assignments from structured script[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Planning visuals...", total=len(structured_script.segments))

            for seg in structured_script.segments:
                # Create visual plan from segment's DoP assignment
                from core.models.video_production import VisualPlan as SceneVisualPlan

                # Map display_mode to visual plan settings
                display_mode = seg.display_mode or "carry_forward"
                dalle_prompt = ""
                animate_with_luma = False
                ken_burns = None
                kb_figure_path = None

                if display_mode == "dall_e":
                    # Generate DALL-E prompt from visual direction
                    dalle_prompt = f"{seg.visual_direction} {style_consistency['style_suffix']}"
                elif display_mode == "web_image":
                    # Build search query from key concepts + segment text
                    search_parts = []
                    if seg.key_concepts:
                        search_parts.extend(seg.key_concepts[:3])
                    if not search_parts:
                        # Fall back to first few words of segment text
                        words = seg.text.split()[:8]
                        search_parts.append(" ".join(words))
                    dalle_prompt = " ".join(search_parts)  # Reuse dalle_prompt field for search query
                elif display_mode == "figure_sync":
                    # Use KB figure
                    figures_matched += 1
                    # Find figure path from asset
                    if seg.visual_asset_id and content_library is not None:
                        asset = content_library.get(seg.visual_asset_id)
                        if asset and asset.path:
                            kb_figure_path = asset.path
                    # Also check kb_figure_paths by figure number
                    if not kb_figure_path and seg.figure_refs and kb_figure_paths:
                        for fig_num in seg.figure_refs:
                            # KB figures use fig_{N-1} naming (0-indexed)
                            fig_idx = fig_num - 1
                            fig_key = f"fig_{fig_idx:03d}"
                            for kb_id, kb_path in kb_figure_paths.items():
                                if fig_key in kb_id:
                                    kb_figure_path = kb_path
                                    break
                            if kb_figure_path:
                                break

                # Ken Burns for non-animated scenes with images
                if display_mode in ["dall_e", "web_image", "figure_sync"]:
                    ken_burns = {"enabled": True, "direction": "slow_zoom_in", "duration_match": "scene_duration"}

                plan = SceneVisualPlan(
                    scene_id=f"scene_{seg.idx:03d}",
                    dalle_prompt=dalle_prompt,
                    dalle_style=style_consistency.get("dalle_style", "natural"),
                    dalle_settings={},
                    animate_with_luma=animate_with_luma,
                    luma_prompt=None,
                    luma_settings={},
                    transition_in="fade",
                    transition_out="fade",
                    ken_burns=ken_burns,
                    on_screen_text=None,
                    text_position="lower_third"
                )
                plan.budget_mode = display_mode
                plan.kb_figure_path = kb_figure_path

                visual_plans.append(plan)
                progress.advance(task)

        console.print()

    else:
        # Legacy visual planning (without DoP)
        # Build lookup sets for budget-aware planning
        text_only_ids = set(allocation["text_only"]) if allocation else set()
        luma_ids = set(allocation["luma"]) if allocation else set()
        ken_burns_ids = set(allocation["ken_burns"]) if allocation else set()

        # Build group membership: scene_id -> group_index (for image sharing)
        scene_to_group = {}
        group_primary_scene = {}  # group_index -> primary scene_id (gets DALL-E generation)
        if allocation and allocation.get("generate"):
            for group_idx, group in enumerate(allocation["generate"]):
                # First scene in group is primary (gets DALL-E generation)
                primary_id = group[0].scene_id
                group_primary_scene[group_idx] = primary_id
                for scene in group:
                    scene_to_group[scene.scene_id] = group_idx

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Planning visuals...", total=len(scenes))

            for scene in scenes:
                plan = create_visual_plan(scene, knowledge_graph, style_consistency)

                # Apply budget tier constraints
                if allocation:
                    if scene.scene_id in text_only_ids:
                        # Text-only: no DALL-E, no animation
                        plan.dalle_prompt = ""
                        plan.animate_with_luma = False
                        plan.luma_prompt = None
                        plan.ken_burns = None
                        plan.budget_mode = "text_only"
                    elif scene.scene_id in scene_to_group:
                        group_idx = scene_to_group[scene.scene_id]
                        primary_id = group_primary_scene[group_idx]

                        if scene.scene_id == primary_id:
                            # Primary scene: generates the DALL-E image for the group
                            plan.budget_mode = "primary"
                            plan.group_id = group_idx
                        else:
                            # Secondary scene: shares image with primary
                            plan.dalle_prompt = ""  # Don't generate, reuse primary's image
                            plan.budget_mode = "shared"
                            plan.group_id = group_idx
                            plan.shares_image_with = primary_id

                        # Apply Luma/Ken Burns based on allocation
                        if scene.scene_id in luma_ids:
                            plan.animate_with_luma = True
                        else:
                            plan.animate_with_luma = False
                            plan.luma_prompt = None

                        if scene.scene_id in ken_burns_ids and not plan.animate_with_luma:
                            plan.ken_burns = {"enabled": True, "direction": "slow_zoom_in", "duration_match": "scene_duration"}
                        elif scene.scene_id not in luma_ids:
                            plan.ken_burns = None

                # Try to match scene to KB figures by keyword
                matched_figure = None
                if kb_figure_paths:
                    matched_figure = _match_scene_to_figure(scene, kb_figure_paths, knowledge_graph)
                    if matched_figure:
                        figures_matched += 1

                # Store the matched figure path
                plan.kb_figure_path = matched_figure

                visual_plans.append(plan)
                progress.advance(task)

        console.print()

    # If keyword matching found few figures, use fallback distribution
    kb_figure_count = len(kb_data["figure_paths"]) if kb_data else 0
    if kb_figure_paths and figures_matched < min(5, kb_figure_count):
        console.print(f"[{t.dimmed}]Keyword matching found only {figures_matched} figures, using fallback distribution...[/]")
        fallback_assigned = distribute_figures_to_scenes(scenes, visual_plans, kb_figure_paths, allocation)
        figures_matched += fallback_assigned
        console.print(f"[{t.success}]Assigned {fallback_assigned} figures to high-importance scenes[/]\n")

    # Print comprehensive asset summary
    print_asset_summary(visual_plans, kb_figure_count)

    # Print full scene list with asset sources
    print_full_scene_list(visual_plans, scenes)

    # Create output directory
    output_dir = Path("artifacts") / "video_production" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save visual plans
    plans_output = output_dir / "visual_plans.json"
    plans_data = []
    for plan in visual_plans:
        plans_data.append({
            "scene_id": plan.scene_id,
            "dalle_prompt": plan.dalle_prompt,
            "dalle_style": plan.dalle_style,
            "dalle_settings": plan.dalle_settings,
            "animate_with_luma": plan.animate_with_luma,
            "luma_prompt": plan.luma_prompt,
            "luma_settings": plan.luma_settings,
            "transition_in": plan.transition_in,
            "transition_out": plan.transition_out,
            "ken_burns": plan.ken_burns,
            "on_screen_text": plan.on_screen_text,
            "text_position": plan.text_position,
            "kb_figure_path": getattr(plan, 'kb_figure_path', None)
        })

    with open(plans_output, 'w', encoding='utf-8') as f:
        json.dump(plans_data, f, indent=2)

    console.print(f"[{t.success}]Saved visual plans to:[/] {plans_output}")

    # Generate assets (mock or live)
    if live:
        console.print(f"\n[{t.label}]Live mode: Generating real assets...[/]")
        assets = await generate_live_assets(
            visual_plans,
            output_dir,
            console,
            # Pass StructuredScript and ContentLibrary for Unified Production Architecture
            structured_script=structured_script if use_dop else None,
            content_library=content_library if use_dop else None,
        )
        console.print(f"[{t.success}]Generated {len(assets)} assets[/]")
    else:
        console.print(f"\n[{t.label}]Mock mode: Generating placeholder assets...[/]")
        assets = await generate_mock_assets(visual_plans, output_dir)
        console.print(f"[{t.success}]Created {len(assets)} mock asset entries[/]")

    # Generate audio from generated script (not original transcription)
    # The script_text contains the NEW content, aligned_segments has the original
    # Note: We slice script paragraphs to match scene range for --limit/--start
    audio_paths = {}
    script_text = trial_data.get("script_text") if from_training else None

    # If using scene limits, slice the script paragraphs proportionally
    if script_text and (scene_start > 0 or scene_limit):
        paragraphs = [p.strip() for p in script_text.split('\n\n') if p.strip()]
        total_scenes = len(all_scenes)
        total_paragraphs = len(paragraphs)

        # Map scene range to paragraph range (proportionally)
        para_start = int(scene_start * total_paragraphs / total_scenes) if total_scenes > 0 else 0
        para_end = para_start + len(scenes)  # Match scene count
        para_end = min(para_end, total_paragraphs)

        script_text = '\n\n'.join(paragraphs[para_start:para_end])
        console.print(f"[{t.dimmed}]Audio: paragraphs {para_start+1}-{para_end} of {total_paragraphs} (matching scene range)[/]")

    if generate_audio:
        audio_paths = await generate_scene_audio(
            scenes=scenes,
            output_dir=output_dir,
            console=console,
            voice_id=voice_id,
            live=live,
            script_text=script_text,
            # Pass StructuredScript and ContentLibrary for Unified Production Architecture
            structured_script=structured_script if use_dop else None,
            content_library=content_library if use_dop else None,
        )

    # Save asset manifest (for both live and mock)
    manifest_path = output_dir / "asset_manifest.json"
    manifest_data = {
        "run_id": run_id,
        "mode": "live" if live else "mock",
        "total_scenes": len(assets),
        "animated_scenes": sum(1 for a in assets if a.video_path),
        "audio_clips": len(audio_paths),
        "assets": [
            {
                "scene_id": a.scene_id,
                "image_path": a.image_path,
                "video_path": a.video_path,
                "audio_path": audio_paths.get(a.scene_id),
                "display_start": getattr(a, 'display_start', 0.0),
                "display_end": getattr(a, 'display_end', 5.0)
            }
            for a in assets
        ]
    }
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)

    console.print(f"[{t.success}]Saved asset manifest to:[/] {manifest_path}")

    # Save content library and updated script (Unified Production Architecture)
    # Note: Assets are registered immediately during generation:
    # - Audio assets: registered in generate_scene_audio()
    # - Image/Figure assets: registered in generate_live_assets()
    if use_dop and structured_script:
        # Ensure we have a librarian instance
        if content_library is None:
            content_library = ContentLibrary(project_id=run_id)
        librarian = ContentLibrarian(content_library)

        # Save content library for future reuse
        library_path = output_dir / "content_library.json"
        librarian.save(library_path)
        console.print(f"[{t.success}]Saved content library to:[/] {library_path}")

        # Save updated StructuredScript with asset IDs and durations
        script_path = output_dir / f"{structured_script.script_id}_structured_script.json"
        structured_script.save(script_path)
        console.print(f"[{t.success}]Updated structured script:[/] {script_path}")

    # Final summary
    console.print()
    summary = Panel(
        Text.from_markup(
            f"[bold]Production Complete[/]\n\n"
            f"Output directory: [cyan]{output_dir}[/]\n"
            f"Visual plans: [green]{len(visual_plans)}[/]\n"
            f"Animated scenes: [yellow]{sum(1 for p in visual_plans if p.animate_with_luma)}[/]\n"
            f"Audio clips: [cyan]{len(audio_paths)}[/]\n"
            f"Mode: [{'green' if not live else 'yellow'}]{'Mock' if not live else 'Live'}[/]"
        ),
        title="Summary",
        border_style=t.success
    )
    console.print(summary)


@click.command("produce-video")
@click.option(
    "--from-training", "-t",
    type=str,
    help="Use output from a training trial (e.g., 'trial_000_20260201_192220')"
)
@click.option(
    "--script", "-s",
    type=click.Path(exists=True),
    help="Path to podcast script file"
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    default="output.mp4",
    help="Output video path"
)
@click.option(
    "--live/--mock",
    default=False,
    help="Use real APIs (live) or mock generation"
)
@click.option(
    "--style",
    type=click.Choice(["technical", "educational", "documentary"]),
    default="technical",
    help="Visual style preset"
)
@click.option(
    "--kb",
    type=str,
    help="Knowledge base project name (for figure access)"
)
@click.option(
    "--budget", "-b",
    type=click.Choice(["micro", "low", "medium", "high", "full"]),
    default=None,
    help="Budget tier (controls image/animation count). Use --show-tiers to see costs."
)
@click.option(
    "--show-tiers",
    is_flag=True,
    help="Show cost comparison for all budget tiers, then exit"
)
@click.option(
    "--limit", "-l",
    type=int,
    default=None,
    help="Limit to N scenes (for incremental production)"
)
@click.option(
    "--start",
    type=int,
    default=0,
    help="Start from scene index (0-based, for incremental production)"
)
@click.option(
    "--audio/--no-audio",
    default=True,
    help="Generate audio narration for each scene (default: enabled)"
)
@click.option(
    "--voice",
    type=str,
    default="lily",
    help="ElevenLabs voice (lily, rachel, adam, or voice_id)"
)
def produce_video_cmd(from_training, script, output, live, style, kb, budget, show_tiers, limit, start, audio, voice):
    """Produce an explainer video from a podcast script.

    \b
    Input modes:
      --from-training  Use a training trial's script and segments
      --script         Use an existing script file (no training required)

    \b
    Budget tiers (use --show-tiers to see detailed costs):
      micro   Text overlays only, no image generation ($0)
      low     ~15 hero images for key moments ($1-2)
      medium  ~40 consolidated images with Ken Burns ($3-5)
      high    ~80 images with selective Luma animation ($8-12)
      full    All scenes get unique visuals ($15+)

    \b
    Examples:
      claude-studio produce-video -t trial_000 --show-tiers
      claude-studio produce-video -t trial_000 --budget low --mock
      claude-studio produce-video -t trial_000 --budget medium --kb uav-positioning --live
    """
    if not from_training and not script:
        raise click.UsageError("Provide --from-training or --script")

    # Map voice names to IDs
    voice_map = {
        "lily": "pFZP5JQG7iQjIQuC4Bku",
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "adam": "pNInz6obpgDQGcFmaJgB"
    }
    voice_id = voice_map.get(voice.lower(), voice) if voice else voice_map["lily"]

    asyncio.run(_produce_video_async(
        from_training=from_training,
        script_path=script,
        output_path=output,
        live=live,
        style=style,
        kb_project=kb,
        budget_tier=budget,
        show_tiers_only=show_tiers,
        scene_limit=limit,
        scene_start=start,
        generate_audio=audio,
        voice_id=voice_id
    ))
