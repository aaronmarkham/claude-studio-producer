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

    # Count assets
    total = len(visual_plans)
    luma_scenes = [p for p in visual_plans if p.animate_with_luma]
    ken_burns_scenes = [p for p in visual_plans if p.ken_burns and p.ken_burns.get("enabled")]
    kb_matched = [p for p in visual_plans if getattr(p, 'kb_figure_path', None)]

    # Cost estimates (approximate)
    # DALL-E 3 HD 1792x1024: ~$0.08 per image
    # Luma AI: ~$0.05 per second, avg 5s = $0.25 per video
    dalle_cost_per_image = 0.08
    luma_cost_per_video = 0.25

    # Calculate what needs to be generated
    dalle_to_generate = total - len(kb_matched)  # Scenes without KB figures need DALL-E
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

    # Total row
    total_cost = dalle_cost + luma_cost
    table.add_row(
        "[bold]TOTAL[/]",
        f"[bold green]{len(kb_matched)}[/]",
        f"[bold]{dalle_to_generate + luma_to_generate}[/]",
        f"[bold]${total_cost:.2f}[/]"
    )

    console.print(table)

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

        # Determine visual source
        if getattr(plan, 'kb_figure_path', None):
            source = "[green]PDF Figure[/]"
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

    return {
        "trial_dir": trial_dir,
        "script_text": script_text,
        "base_name": base_name,
        "aligned_segments": analysis_data.get("aligned_segments", []),
        "structure_profile": analysis_data.get("structure_profile"),
        "style_profile": analysis_data.get("style_profile"),
        "knowledge_graph": knowledge_graph
    }


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
    kb_project: Optional[str] = None
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
    else:
        raise click.ClickException("Currently only --from-training mode is supported")

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
    scenes = segments_to_scenes(aligned_segments, SEGMENT_VISUAL_MAPPING)
    console.print(f"[{t.success}]Created {len(scenes)} video scenes[/]\n")

    print_scene_table(scenes)

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

    # Print comprehensive asset summary
    kb_figure_count = len(kb_data["figure_paths"]) if kb_data else 0
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
        console.print(f"\n[{t.warning}]Live mode: Would generate DALL-E images and Luma animations[/]")
        console.print(f"[{t.dimmed}](Not implemented yet - use --mock for now)[/]")
    else:
        console.print(f"\n[{t.label}]Mock mode: Generating placeholder assets...[/]")
        assets = await generate_mock_assets(visual_plans, output_dir)
        console.print(f"[{t.success}]Created {len(assets)} mock asset entries[/]")

        # Save asset manifest
        manifest_path = output_dir / "asset_manifest.json"
        manifest_data = {
            "run_id": run_id,
            "total_scenes": len(assets),
            "animated_scenes": sum(1 for a in assets if a.video_path),
            "assets": [
                {
                    "scene_id": a.scene_id,
                    "image_path": a.image_path,
                    "video_path": a.video_path,
                    "display_start": a.display_start,
                    "display_end": a.display_end
                }
                for a in assets
            ]
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2)

        console.print(f"[{t.success}]Saved asset manifest to:[/] {manifest_path}")

    # Final summary
    console.print()
    summary = Panel(
        Text.from_markup(
            f"[bold]Production Complete[/]\n\n"
            f"Output directory: [cyan]{output_dir}[/]\n"
            f"Visual plans: [green]{len(visual_plans)}[/]\n"
            f"Animated scenes: [yellow]{sum(1 for p in visual_plans if p.animate_with_luma)}[/]\n"
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
def produce_video_cmd(from_training, script, output, live, style, kb):
    """Produce an explainer video from a podcast script.

    \b
    Input modes:
      --from-training  Use a training trial's script and segments
      --script         Use an existing script file (coming soon)

    \b
    Examples:
      claude-studio produce-video --from-training trial_000_20260201_192220 --mock
      claude-studio produce-video -t trial_000 --kb uav-positioning --live
    """
    if not from_training and not script:
        raise click.UsageError("Provide --from-training or --script")

    asyncio.run(_produce_video_async(
        from_training=from_training,
        script_path=script,
        output_path=output,
        live=live,
        style=style,
        kb_project=kb
    ))
