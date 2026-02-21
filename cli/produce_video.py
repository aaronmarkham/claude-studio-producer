"""Produce Video command - Generate explainer videos from podcast scripts

Functions extracted to core/pipeline/ modules:
  display.py    — Rich console formatting
  figures.py    — KB figure matching and distribution
  audio.py      — Scene audio generation
  assets.py     — Mock and live asset generation
  video_stages.py — Data loading and conversion
"""

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

# Pipeline modules (extracted from this file)
from core.pipeline.display import (
    print_header, print_budget_tiers, print_scene_table,
    print_asset_summary, print_full_scene_list,
)
from core.pipeline.figures import (
    _match_scene_to_figure, distribute_figures_to_scenes, load_kb_figures,
)
from core.pipeline.audio import generate_scene_audio
from core.pipeline.assets import generate_mock_assets, generate_live_assets
from core.pipeline.video_stages import (
    load_training_trial, script_segments_to_aligned,
    reconstruct_aligned_segments,
)

console = Console()

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

    # Check if we have a structured script (Unified Production Architecture)
    structured_script = trial_data.get("structured_script") if (from_training or script_path) else None
    use_dop = structured_script is not None

    if use_dop:
        console.print(f"[{t.success}]Using Unified Production Architecture (DoP)[/]\n")

    # Convert to VideoScenes
    from core.video_production import segments_to_scenes, structured_script_to_scenes, create_visual_plan
    from core.video_production import SEGMENT_VISUAL_MAPPING

    console.print(f"\n[{t.label}]Converting segments to video scenes...[/]")
    if structured_script is not None:
        all_scenes = structured_script_to_scenes(structured_script, SEGMENT_VISUAL_MAPPING)
        console.print(f"[{t.success}]Created {len(all_scenes)} video scenes from structured script[/]\n")
    else:
        all_scenes = segments_to_scenes(aligned_segments, SEGMENT_VISUAL_MAPPING)
        console.print(f"[{t.success}]Created {len(all_scenes)} video scenes from aligned segments[/]\n")

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

                # Force figure_sync when segment explicitly references a figure/table
                # regardless of budget tier — explicit references should always show the figure
                if seg.figure_refs and kb_figure_paths and display_mode != "figure_sync":
                    for fig_num in seg.figure_refs:
                        fig_idx = fig_num - 1  # KB figures are 0-indexed
                        fig_key = f"fig_{fig_idx:03d}"
                        for kb_id, kb_path in kb_figure_paths.items():
                            if fig_key in kb_id:
                                display_mode = "figure_sync"
                                kb_figure_path = kb_path
                                break
                        if kb_figure_path:
                            break

                if display_mode == "dall_e":
                    # Generate DALL-E prompt from visual direction
                    dalle_prompt = f"{seg.visual_direction} {style_consistency['style_suffix']}"
                elif display_mode == "web_image":
                    # Build search query for Wikimedia Commons
                    # Priority: visual_direction > key_concepts > extracted nouns
                    if seg.visual_direction:
                        # DoP already wrote a good description of what to show
                        dalle_prompt = seg.visual_direction
                    elif seg.key_concepts:
                        dalle_prompt = " ".join(seg.key_concepts[:3])
                    else:
                        # Extract meaningful terms from segment text
                        # Filter out common words to get searchable noun phrases
                        import re as _re
                        stop_words = {
                            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                            'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                            'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                            'as', 'into', 'through', 'during', 'before', 'after', 'above',
                            'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
                            'it', 'its', 'this', 'that', 'these', 'those', 'you', 'your',
                            'we', 'our', 'they', 'their', 'he', 'she', 'his', 'her',
                            'what', 'which', 'who', 'whom', 'how', 'when', 'where', 'why',
                            'here', 'there', 'about', 'just', 'like', 'get', 'got',
                            'really', 'actually', 'probably', 'right', 'going', 'let',
                            'know', 'think', 'say', 'said', 'one', 'way', 'thing',
                            've', 've', 're', 's', 't', 'don', 'doesn', 'didn', 'won',
                        }
                        words = _re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[a-z]{4,}", seg.text)
                        # Prefer capitalized phrases (proper nouns, technical terms)
                        caps = [w for w in words if w[0].isupper()]
                        lower = [w for w in words if w[0].islower() and w.lower() not in stop_words]
                        terms = (caps[:4] + lower[:3])[:5]
                        dalle_prompt = " ".join(terms) if terms else seg.intent.value + " diagram"
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
