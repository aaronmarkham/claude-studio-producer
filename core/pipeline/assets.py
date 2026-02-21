"""Asset generation for video production.

Mock and live asset generation (DALL-E images, Luma videos, Wikimedia, Ken Burns).
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.models.structured_script import StructuredScript
from core.models.content_library import ContentLibrary, AssetType, AssetStatus
from core.content_librarian import ContentLibrarian

console = Console()

def _get_theme():
    from cli.theme import get_theme
    return get_theme()

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

    t = _get_theme()
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
                                prompt=search_query,
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
                                prompt=plan.dalle_prompt,
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
