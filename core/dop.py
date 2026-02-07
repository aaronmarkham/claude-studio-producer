"""
Director of Photography (DoP) Module - Phase 4 of Unified Production Architecture

The DoP assigns visual display modes and generates visual direction hints for each
segment in a structured script. It bridges the gap between script content and visual
production by:

1. Analyzing segment intent, importance, and figure references
2. Respecting budget tier ratios for DALL-E image allocation
3. Reusing existing approved assets from the content library
4. Generating visual direction prompts for visual producers

This module is deterministic (no LLM calls) and can be integrated into both the
original agent pipeline and the transcript-led pipeline.
"""

from typing import Dict, List, Optional, Tuple

from core.models.content_library import (
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import (
    ScriptSegment,
    SegmentIntent,
    StructuredScript,
)

# Import budget tiers from video_production
from core.video_production import BUDGET_TIERS


def assign_visuals(
    script: StructuredScript,
    library: ContentLibrary,
    budget_tier: str = "medium",
) -> StructuredScript:
    """
    Assign visual display modes to all segments in a script.

    This is the main DoP function. It determines what image/video
    to show for each segment based on:
    1. Figure references (figure_sync mode) - always prioritized
    2. Budget tier ratios (how many get dall_e vs carry_forward)
    3. Segment importance scores
    4. Existing approved assets in the library

    Args:
        script: The structured script to annotate
        library: Content library to check for existing assets
        budget_tier: One of "micro", "low", "medium", "high", "full"

    Returns:
        The same script with display_mode and visual_direction populated
    """
    if budget_tier not in BUDGET_TIERS:
        raise ValueError(f"Invalid budget tier: {budget_tier}")

    tier_config = BUDGET_TIERS.get(budget_tier, BUDGET_TIERS["medium"])
    image_ratio = tier_config["image_ratio"]
    text_overlay_all = tier_config.get("text_overlay_all", False)

    # Phase 1: Assign figure_sync first (always prioritized)
    figure_sync_segments = []
    for seg in script.segments:
        if seg.figure_refs and seg.display_mode is None:
            _assign_figure_sync(seg, script, library)
            figure_sync_segments.append(seg.idx)

    # Phase 2: If micro tier, everything else is text_only
    if text_overlay_all:
        for seg in script.segments:
            if seg.display_mode is None:
                seg.display_mode = "text_only"
                seg.visual_direction = ""
        return script

    # Phase 3: Calculate DALL-E budget
    # image_ratio applies ONLY to DALL-E images, not including KB figures
    # This ensures consistent quality across different scene counts
    # E.g., medium tier: 27% of 100 = 27 DALL-E images (+ however many figure segments)
    total_segments = len(script.segments)
    if image_ratio > 0:
        # DALL-E budget is based on the total segment count, independently of figures
        dalle_budget_for_images = max(1, int(total_segments * image_ratio))
    else:
        dalle_budget_for_images = 0

    # Phase 4: Score and assign DALL-E to remaining segments by importance
    segments_needing_assignment = [s for s in script.segments if s.display_mode is None]

    # First, separate transitions (they always get text_only)
    transition_segments = [s for s in segments_needing_assignment if s.intent == SegmentIntent.TRANSITION]
    non_transition_segments = [s for s in segments_needing_assignment if s.intent != SegmentIntent.TRANSITION]

    # Assign transitions to text_only
    for seg in transition_segments:
        seg.display_mode = "text_only"

    # Now allocate DALL-E to non-transition segments
    if dalle_budget_for_images > 0 and non_transition_segments:
        # Sort by importance (descending)
        # Prioritize: approved assets first, then by importance score
        sorted_segments = sorted(
            non_transition_segments,
            key=lambda s: (
                library.has_approved_asset_for(s.idx, AssetType.IMAGE),  # Approved assets sort first
                s.importance_score
            ),
            reverse=True
        )

        dalle_assigned = 0
        for seg in sorted_segments:
            if dalle_assigned < dalle_budget_for_images:
                seg.display_mode = "dall_e"
                # Link to existing approved image if available
                existing = library.get_approved_for_segment(seg.idx, AssetType.IMAGE)
                if existing:
                    seg.visual_asset_id = existing.asset_id
                dalle_assigned += 1
            else:
                seg.display_mode = "carry_forward"
    else:
        # No DALL-E budget, assign carry_forward
        for seg in non_transition_segments:
            seg.display_mode = "carry_forward"

    # Phase 6: Generate visual direction for dall_e and figure_sync
    for seg in script.segments:
        if seg.display_mode in ["dall_e", "figure_sync"] and not seg.visual_direction:
            seg.visual_direction = _generate_visual_direction(seg, script, library)

    return script


def _assign_figure_sync(
    seg: ScriptSegment,
    script: StructuredScript,
    library: ContentLibrary
) -> None:
    """Assign figure_sync mode and link to library asset if available."""
    seg.display_mode = "figure_sync"

    # Try to find the figure in library
    for figure_num in seg.figure_refs:
        matching_figures = library.query(
            asset_type=AssetType.FIGURE,
            status=AssetStatus.APPROVED,
            figure_number=figure_num,
        )
        if matching_figures:
            seg.visual_asset_id = matching_figures[0].asset_id
            break


def _generate_visual_direction(
    seg: ScriptSegment,
    script: StructuredScript,
    library: ContentLibrary
) -> str:
    """
    Generate visual direction hints for DALL-E prompt generation.

    This provides guidance for the image generation prompt based on
    the segment's intent and content.
    """
    hints = []
    intent = seg.intent

    # Intent-based visual suggestions
    intent_directions = {
        SegmentIntent.INTRO: "Abstract visualization representing the research topic. Use minimalist design with focus on main theme. Should feel welcoming and professional.",
        SegmentIntent.BACKGROUND: "Conceptual illustration of foundational concepts or prior work. Use diagrams and connections to show relationships.",
        SegmentIntent.METHODOLOGY: "Technical architectural diagram or system flowchart. Show processes, components, and data flow. Use clean lines and clear hierarchy.",
        SegmentIntent.KEY_FINDING: "Data visualization or chart representation of main results. Use vivid accent colors to highlight findings. Make the insight visually apparent.",
        SegmentIntent.FIGURE_WALKTHROUGH: f"Frame or synchronize with Figure {seg.figure_refs[0] if seg.figure_refs else '?'}. Position for narration sync. May include annotations.",
        SegmentIntent.DATA_DISCUSSION: "Scientific data representation, charts, or measurement context. Use technical aesthetic with clear axis labels and metrics.",
        SegmentIntent.COMPARISON: "Side-by-side or contrast visualization showing relative performance or differences. Use comparison indicators.",
        SegmentIntent.TRANSITION: "Subtle, transitional imagery.",
        SegmentIntent.RECAP: "Summary visual that visually echoes or callbacks to earlier points.",
        SegmentIntent.OUTRO: "Closing visual with strong composition. Leave visual impression of conclusion.",
    }

    if intent in intent_directions:
        hints.append(intent_directions[intent])

    # Add key concepts if available
    if seg.key_concepts:
        concepts = ", ".join(seg.key_concepts[:3])
        hints.append(f"Key visual elements to represent: {concepts}")

    # Add figure context
    if seg.figure_refs and seg.display_mode == "figure_sync":
        for fig_num in seg.figure_refs:
            if fig_num in script.figure_inventory:
                fig_inv = script.figure_inventory[fig_num]
                if fig_inv.caption:
                    hints.append(f"Sync with Figure {fig_num}: {fig_inv.caption[:100]}")

    # Composition guidance based on importance
    if seg.importance_score >= 0.8:
        hints.append("High priority - ensure compelling and clear composition.")
    elif seg.importance_score <= 0.3:
        hints.append("Lower priority - simpler treatment acceptable.")

    # Ken Burns guidance
    if seg.importance_score >= 0.6 and seg.display_mode == "dall_e":
        hints.append("Suitable for Ken Burns slow zoom effect.")

    if not hints:
        hints.append("Create a professional visual representation of the narration content.")

    return " ".join(filter(None, hints))


def get_visual_plan_summary(script: StructuredScript) -> Dict[str, int]:
    """
    Get a summary of visual assignments for a script.

    Returns counts of each display mode.
    """
    summary = {
        "figure_sync": 0,
        "dall_e": 0,
        "carry_forward": 0,
        "text_only": 0,
        "unassigned": 0,
    }

    for seg in script.segments:
        mode = seg.display_mode or "unassigned"
        if mode in summary:
            summary[mode] += 1
        else:
            summary["unassigned"] += 1

    return summary


def estimate_visual_cost(script: StructuredScript, dalle_cost: float = 0.08) -> float:
    """
    Estimate the cost of generating visuals for a script.

    Args:
        script: Script with display modes assigned
        dalle_cost: Cost per DALL-E image (default $0.08 for HD)

    Returns:
        Estimated cost in USD
    """
    summary = get_visual_plan_summary(script)
    return summary["dall_e"] * dalle_cost


def get_generation_list(script: StructuredScript) -> List[int]:
    """
    Get list of segment indices that need DALL-E generation.

    Only includes segments with display_mode="dall_e".
    Figure segments use KB figures and don't need generation.
    """
    return [
        seg.idx for seg in script.segments
        if seg.display_mode == "dall_e"
    ]


def get_figure_sync_list(script: StructuredScript) -> List[Tuple[int, List[int]]]:
    """
    Get list of (segment_idx, figure_refs) for figure_sync segments.

    These segments need their KB figures loaded at display time.
    """
    return [
        (seg.idx, seg.figure_refs)
        for seg in script.segments
        if seg.display_mode == "figure_sync" and seg.figure_refs
    ]


def get_visual_generation_plan(
    script: StructuredScript,
    library: ContentLibrary,
    budget_tier: str = "medium",
) -> dict:
    """
    Generate a report on what visuals need to be generated for this script.

    This is useful for planning generation work after DoP assignment.
    """
    plan = {
        "total_segments": len(script.segments),
        "segments_needing_dalle": [],
        "segments_needing_figures": [],
        "estimated_cost": 0.0,
        "can_reuse": {},
        "tier": budget_tier,
    }

    DALLE_COST = 0.08

    for segment in script.segments:
        if segment.display_mode == "dall_e":
            existing = library.get_approved_for_segment(segment.idx, AssetType.IMAGE)
            if existing:
                plan["can_reuse"][segment.idx] = existing.asset_id
            else:
                plan["segments_needing_dalle"].append(segment.idx)
                plan["estimated_cost"] += DALLE_COST

        elif segment.display_mode == "figure_sync":
            existing = None
            for figure_num in segment.figure_refs:
                matching = library.query(
                    asset_type=AssetType.FIGURE,
                    status=AssetStatus.APPROVED,
                    figure_number=figure_num,
                )
                if matching:
                    existing = matching[0]
                    plan["can_reuse"][segment.idx] = existing.asset_id
                    break

            if not existing:
                plan["segments_needing_figures"].extend(segment.figure_refs)

    return plan
