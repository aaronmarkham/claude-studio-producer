"""
Core video production functions for transcript-led video generation.

This module provides the bridge between the podcast training pipeline
(AlignedSegment analysis) and visual production (DALL-E + Luma).
"""

from typing import Dict, List, Optional, Any

from core.training.models import AlignedSegment, SegmentType
from core.models.document import DocumentGraph
from core.models.video_production import VideoScene, VisualPlan


# Segment type to visual style mapping
# Maps each SegmentType to its visual production parameters
SEGMENT_VISUAL_MAPPING: Dict[str, Dict[str, Any]] = {
    "INTRO": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,  # Usually static title card
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Opening visual with topic representation"
    },

    "BACKGROUND": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": False,
        "visual_complexity": "medium",
        "ken_burns": True,
        "template": "Prior work or foundational concept diagram"
    },

    "PROBLEM_STATEMENT": {
        "dalle_style": "technical diagram",
        "animation_candidate": True,  # Show problem emerging
        "visual_complexity": "medium",
        "ken_burns": False,
        "template": "Visual showing the gap or challenge"
    },

    "METHODOLOGY": {
        "dalle_style": "architectural diagram",
        "animation_candidate": True,  # Process flow
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "System architecture or process flow"
    },

    "KEY_FINDING": {
        "dalle_style": "data visualization",
        "animation_candidate": True,  # Data revealing itself
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "Chart, graph, or result visualization"
    },

    "FIGURE_DISCUSSION": {
        "dalle_style": "technical diagram",
        "animation_candidate": True,  # Annotate figure
        "visual_complexity": "high",
        "ken_burns": False,
        "template": "Recreation of paper figure with annotations"
    },

    "IMPLICATION": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": True,  # Ripple effects
        "visual_complexity": "medium",
        "ken_burns": True,
        "template": "Real-world application or impact"
    },

    "LIMITATION": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Visual metaphor for constraint"
    },

    "CONCLUSION": {
        "dalle_style": "abstract visualization",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Summary visual or callback to intro"
    },

    "TANGENT": {
        "dalle_style": "conceptual illustration",
        "animation_candidate": False,
        "visual_complexity": "low",
        "ken_burns": True,
        "template": "Related concept visualization"
    },

    "TRANSITION": {
        "dalle_style": None,  # No new visual, use transition effect
        "animation_candidate": False,
        "visual_complexity": "none",
        "ken_burns": False,
        "template": None
    }
}


def segments_to_scenes(
    aligned_segments: List[AlignedSegment],
    visual_mapping: Optional[Dict[str, Dict[str, Any]]] = None
) -> List[VideoScene]:
    """
    Convert podcast segments to video scenes.

    Groups AlignedSegments into VideoScenes suitable for visual production.

    Grouping rules:
    - TRANSITION segments don't create new scenes (just transition effects)
    - Adjacent segments of same type may be merged if <15s apart
    - Each scene targets 15-60 seconds

    Args:
        aligned_segments: List of AlignedSegment from training pipeline
        visual_mapping: Optional custom mapping (defaults to SEGMENT_VISUAL_MAPPING)

    Returns:
        List of VideoScene objects ready for visual planning
    """
    if visual_mapping is None:
        visual_mapping = SEGMENT_VISUAL_MAPPING

    scenes = []

    for seg in aligned_segments:
        # Skip transition segments - they become transition effects, not scenes
        if seg.segment_type == SegmentType.TRANSITION:
            continue

        # Get visual mapping for this segment type
        seg_type_str = seg.segment_type.value.upper()
        mapping = visual_mapping.get(seg_type_str, visual_mapping.get("BACKGROUND", {}))

        # Create scene from segment
        # Generate title from key_concepts, or fallback to transcript snippet
        title_is_fallback = False
        if seg.key_concepts:
            title = seg.key_concepts[0]
        else:
            # Extract first few words from transcript as fallback title
            title_is_fallback = True
            text = seg.transcript_segment.text.strip()
            words = text.split()[:6]  # First 6 words
            title = " ".join(words)
            if len(title) > 35:
                title = title[:32] + "..."
            elif not title:
                title = f"Segment {len(scenes) + 1}"

        scene = VideoScene(
            scene_id=f"scene_{len(scenes):03d}",
            title=title,
            title_is_fallback=title_is_fallback,
            concept=_summarize_segment(seg),
            transcript_segment=seg.transcript_segment.text,
            start_time=seg.transcript_segment.start_time,
            end_time=seg.transcript_segment.end_time,
            segment_type=seg.segment_type,
            key_concepts=seg.key_concepts,
            technical_terms=seg.technical_terms,
            referenced_figures=seg.referenced_figures,
            visual_complexity=mapping.get("visual_complexity", "medium"),
            animation_candidate=mapping.get("animation_candidate", False),
            ken_burns_enabled=mapping.get("ken_burns", False)
        )

        scenes.append(scene)

    # Optionally merge short scenes (not implemented here for simplicity)
    # return _merge_short_scenes(scenes, min_duration=15.0)

    return scenes


def _find_relevant_figure(
    knowledge_graph,
    concepts: List[str],
    technical_terms: List[str]
) -> str:
    """
    Search knowledge graph for figures relevant to the given concepts.

    Uses keyword matching between concepts/terms and figure captions.

    Args:
        knowledge_graph: KnowledgeGraph or DocumentGraph with atoms
        concepts: List of key concepts from the segment
        technical_terms: List of technical terms from the segment

    Returns:
        Figure context string for DALL-E prompt, or empty string if no match
    """
    if not knowledge_graph:
        return ""

    # Get atoms dict (works for both KnowledgeGraph and DocumentGraph)
    atoms = getattr(knowledge_graph, 'atoms', {})
    if not atoms:
        return ""

    # Build search terms (lowercase for matching)
    search_terms = set()
    for term in concepts + technical_terms:
        # Add the term and its words
        search_terms.add(term.lower())
        for word in term.lower().split():
            if len(word) > 3:  # Skip short words
                search_terms.add(word)

    # Search figure atoms for matches
    best_match = None
    best_score = 0

    for atom in atoms.values():
        # Check if it's a figure atom
        atom_type = getattr(atom, 'atom_type', None)
        if atom_type is None:
            atom_type = atom.get('atom_type') if isinstance(atom, dict) else None

        # Handle both enum and string atom types
        type_str = atom_type.value if hasattr(atom_type, 'value') else str(atom_type)
        if type_str != 'figure':
            continue

        # Get caption
        caption = getattr(atom, 'caption', None)
        if caption is None and isinstance(atom, dict):
            caption = atom.get('caption')
        if not caption:
            continue

        # Score by matching search terms in caption
        caption_lower = caption.lower()
        score = sum(1 for term in search_terms if term in caption_lower)

        if score > best_score:
            best_score = score
            best_match = caption

    if best_match and best_score >= 2:  # Require at least 2 matching terms
        # Truncate long captions
        if len(best_match) > 150:
            best_match = best_match[:147] + "..."
        return f"Inspired by paper figure: {best_match}. "

    return ""


def generate_dalle_prompt_from_atoms(
    segment: AlignedSegment,
    knowledge_graph: DocumentGraph,
    visual_mapping: Optional[Dict[str, Dict[str, Any]]] = None
) -> str:
    """
    Generate a DALL-E prompt from segment content and linked atoms.

    Uses the segment's key concepts, technical terms, and referenced figures
    to build a precise visual prompt for DALL-E image generation.

    Args:
        segment: AlignedSegment with content analysis
        knowledge_graph: DocumentGraph with paper atoms
        visual_mapping: Optional custom mapping (defaults to SEGMENT_VISUAL_MAPPING)

    Returns:
        DALL-E prompt string
    """
    if visual_mapping is None:
        visual_mapping = SEGMENT_VISUAL_MAPPING

    # Get the base style for this segment type
    seg_type_str = segment.segment_type.value.upper()
    mapping = visual_mapping.get(seg_type_str, visual_mapping.get("BACKGROUND", {}))
    base_style = mapping.get("dalle_style", "conceptual illustration")

    # Skip if this segment type has no visual
    if base_style is None:
        return ""

    # Get the key concepts to visualize (top 3)
    concepts = segment.key_concepts[:3]

    # Check for referenced figures in the paper
    figure_context = ""
    if segment.referenced_figures and knowledge_graph:
        for fig_id in segment.referenced_figures:
            # Handle both DocumentGraph (has get_atom) and KnowledgeGraph (has atoms dict)
            if hasattr(knowledge_graph, 'get_atom'):
                atom = knowledge_graph.get_atom(fig_id)
            else:
                atom = knowledge_graph.atoms.get(fig_id)
            if atom and getattr(atom, 'caption', None):
                figure_context = f"Based on scientific figure: {atom.caption}. "
                break

    # Fallback: Search for relevant figures by keyword matching if no explicit refs
    if not figure_context and knowledge_graph and concepts:
        figure_context = _find_relevant_figure(knowledge_graph, concepts, segment.technical_terms)

    # Build the prompt
    prompt_parts = [
        f"Create a {base_style} illustration.",
        figure_context,
        f"Main concepts: {', '.join(concepts)}." if concepts else "",
        f"Technical terms to represent: {', '.join(segment.technical_terms[:3])}." if segment.technical_terms else "",
        "Style: clean, dark background, vibrant accent colors.",
        "Composition: centered with negative space for text overlay.",
        "Aesthetic: modern technical illustration, not photorealistic."
    ]

    # Filter out empty parts and join
    return " ".join(filter(None, prompt_parts))


def create_visual_plan(
    scene: VideoScene,
    knowledge_graph: Optional[DocumentGraph] = None,
    style_consistency: Optional[Dict[str, Any]] = None
) -> VisualPlan:
    """
    Create visual plan using scene metadata and knowledge graph.

    Determines DALL-E prompt, Luma animation settings, transitions, and Ken Burns effects.

    Args:
        scene: VideoScene to create plan for
        knowledge_graph: Optional DocumentGraph for atom context
        style_consistency: Optional style settings established in scene 0

    Returns:
        VisualPlan with complete visual generation configuration
    """
    if style_consistency is None:
        style_consistency = {}

    # Convert VideoScene back to a segment-like structure for prompt generation
    # (VideoScene wraps AlignedSegment data)
    seg_type_str = scene.segment_type.value.upper()
    mapping = SEGMENT_VISUAL_MAPPING.get(seg_type_str, SEGMENT_VISUAL_MAPPING.get("BACKGROUND", {}))

    # Generate DALL-E prompt
    # We need to create a minimal AlignedSegment-like object for the prompt function
    from core.training.models import TranscriptSegment
    pseudo_segment = AlignedSegment(
        segment_id=scene.scene_id,
        transcript_segment=TranscriptSegment(
            segment_id=scene.scene_id,
            text=scene.transcript_segment,
            start_time=scene.start_time,
            end_time=scene.end_time,
            duration=scene.duration,
            segment_type=scene.segment_type
        ),
        segment_type=scene.segment_type,
        key_concepts=scene.key_concepts,
        technical_terms=scene.technical_terms,
        referenced_figures=scene.referenced_figures
    )

    dalle_prompt = generate_dalle_prompt_from_atoms(
        segment=pseudo_segment,
        knowledge_graph=knowledge_graph,
        visual_mapping=SEGMENT_VISUAL_MAPPING
    )

    # Add style consistency markers
    style_suffix = style_consistency.get("style_suffix", "")
    if style_suffix:
        dalle_prompt += f" {style_suffix}"

    # Determine if animation is beneficial
    animate = (
        scene.animation_candidate and
        scene.visual_complexity in ["medium", "high"] and
        _scene_benefits_from_motion(scene)
    )

    # Generate Luma prompt if animating
    luma_prompt = None
    luma_settings = None
    if animate:
        luma_prompt = _generate_luma_prompt(scene)
        luma_settings = {
            "aspect_ratio": "16:9",
            "loop": False
        }

    # Determine transitions
    transition_in = _select_transition(scene, "in")
    transition_out = _select_transition(scene, "out")

    # Ken Burns configuration
    ken_burns_config = None
    if scene.ken_burns_enabled and not animate:
        ken_burns_config = {
            "enabled": True,
            "direction": "slow_zoom_in",
            "duration_match": "scene_duration"
        }

    return VisualPlan(
        scene_id=scene.scene_id,
        dalle_prompt=dalle_prompt,
        dalle_style=mapping.get("dalle_style", "natural"),
        dalle_settings={
            "model": "dall-e-3",
            "size": "1792x1024",
            "quality": "hd",
            "style": style_consistency.get("dalle_style", "natural")
        },
        animate_with_luma=animate,
        luma_prompt=luma_prompt,
        luma_settings=luma_settings,
        on_screen_text=scene.key_concepts[0] if scene.key_concepts else None,
        text_position="bottom-left",
        transition_in=transition_in,
        transition_out=transition_out,
        ken_burns=ken_burns_config
    )


# Helper functions (internal)

def _summarize_segment(segment: AlignedSegment) -> str:
    """Generate a one-sentence summary of a segment."""
    if segment.key_concepts:
        return f"Discussion of {segment.key_concepts[0]}"
    return "Segment discussion"


def _scene_benefits_from_motion(scene: VideoScene) -> bool:
    """
    Determine if a scene's concept benefits from animation.

    True for: processes, flows, transformations, comparisons, data reveals
    False for: static concepts, definitions, simple diagrams
    """
    motion_keywords = [
        "flow", "process", "transform", "evolve", "change", "compare",
        "integrate", "combine", "adapt", "dynamic", "transition",
        "propagate", "converge", "iterate", "optimize", "adjust"
    ]

    text = " ".join(scene.key_concepts + scene.technical_terms).lower()
    return any(kw in text for kw in motion_keywords)


def _generate_luma_prompt(scene: VideoScene) -> str:
    """Generate a Luma animation prompt for a scene."""
    # Build a motion description based on segment type
    seg_type_str = scene.segment_type.value.upper()

    motion_templates = {
        "PROBLEM_STATEMENT": "Subtle emergence of challenge, focus shifting to problem area",
        "METHODOLOGY": "Flow through process steps, systematic progression",
        "KEY_FINDING": "Data revealing itself, gradual highlight of key result",
        "FIGURE_DISCUSSION": "Annotation appearing, emphasis on key elements",
        "IMPLICATION": "Ripple effects expanding outward, impact visualization"
    }

    motion = motion_templates.get(seg_type_str, "Gentle camera movement, subtle zoom")

    concepts_text = ", ".join(scene.key_concepts[:2]) if scene.key_concepts else "the concept"
    return f"{motion}. Visualizing {concepts_text}. Smooth, professional motion."


def _select_transition(scene: VideoScene, direction: str) -> str:
    """
    Select appropriate transition for a scene.

    Args:
        scene: VideoScene to transition
        direction: "in" or "out"

    Returns:
        Transition type string
    """
    seg_type_str = scene.segment_type.value.upper()

    # Intro and conclusion get fades
    if seg_type_str in ["INTRO", "CONCLUSION"]:
        return "fade_in" if direction == "in" else "fade_out"

    # High complexity scenes get cuts (to maintain energy)
    if scene.visual_complexity == "high":
        return "cut"

    # Default to smooth dissolve
    return "dissolve"


# =============================================================================
# Budget Tier System
# =============================================================================

# Cost constants (USD)
DALLE_COST_PER_IMAGE = 0.08  # DALL-E 3 HD 1792x1024
LUMA_COST_PER_ANIMATION = 0.25  # Luma Dream Machine

# Budget tier definitions
BUDGET_TIERS = {
    "micro": {
        "description": "Text overlays only - no image generation",
        "max_dalle_images": 0,
        "max_luma_animations": 0,
        "use_ken_burns": False,
        "text_overlay_all": True,
    },
    "low": {
        "description": "Hero images for key moments only",
        "max_dalle_images": 15,
        "max_luma_animations": 0,
        "use_ken_burns": True,
        "text_overlay_all": False,
    },
    "medium": {
        "description": "Consolidated images with Ken Burns motion",
        "max_dalle_images": 40,
        "max_luma_animations": 0,
        "use_ken_burns": True,
        "text_overlay_all": False,
    },
    "high": {
        "description": "Full images, selective Luma animation",
        "max_dalle_images": 80,
        "max_luma_animations": 5,
        "use_ken_burns": True,
        "text_overlay_all": False,
    },
    "full": {
        "description": "All scenes get unique visuals",
        "max_dalle_images": 999,
        "max_luma_animations": 999,
        "use_ken_burns": True,
        "text_overlay_all": False,
    },
}

# Scene importance weights by segment type
SEGMENT_IMPORTANCE = {
    "KEY_FINDING": 10,       # Must visualize - this is the paper's contribution
    "FIGURE_DISCUSSION": 9,  # Highly visual by nature
    "METHODOLOGY": 8,        # Complex, benefits from diagrams
    "PROBLEM_STATEMENT": 7,  # Sets up the paper, important context
    "IMPLICATION": 6,        # Real-world impact, engaging
    "BACKGROUND": 4,         # Context, can be simpler
    "LIMITATION": 3,         # Often brief, less visual
    "TANGENT": 2,            # Side note, low priority
    "INTRO": 5,              # Opening visual matters
    "CONCLUSION": 5,         # Closing visual matters
    "TRANSITION": 0,         # No visual needed
}


def score_scene_importance(scene: VideoScene) -> float:
    """
    Score a scene's importance for visual generation.

    Higher scores = more important to generate a unique visual.
    Considers segment type, key_concepts richness, duration, and data quality.

    Args:
        scene: VideoScene to score

    Returns:
        Importance score (0-100 scale)
    """
    # Base score from segment type
    seg_type_str = scene.segment_type.value.upper()
    base_score = SEGMENT_IMPORTANCE.get(seg_type_str, 5)

    # Bonus for rich key_concepts (indicates well-analyzed segment)
    concepts_bonus = min(len(scene.key_concepts) * 2, 10)

    # Bonus for technical terms (more complex content)
    terms_bonus = min(len(scene.technical_terms) * 1.5, 7)

    # Bonus for referenced figures (direct connection to paper)
    figure_bonus = 5 if scene.referenced_figures else 0

    # Penalty for fallback titles (data quality issue)
    fallback_penalty = -5 if scene.title_is_fallback else 0

    # Duration factor (longer scenes might need more visual interest)
    duration_factor = min(scene.duration / 30.0, 1.5)  # Cap at 1.5x for 45+ sec

    # Calculate final score
    raw_score = (base_score + concepts_bonus + terms_bonus + figure_bonus + fallback_penalty)
    final_score = raw_score * duration_factor

    return min(max(final_score, 0), 100)  # Clamp to 0-100


def consolidate_scenes(
    scenes: List[VideoScene],
    max_images: int
) -> List[List[VideoScene]]:
    """
    Group scenes that can share a single visual.

    Adjacent scenes of the same type or with similar concepts are grouped.
    Each group will share one DALL-E image with Ken Burns panning across scenes.

    Args:
        scenes: List of VideoScene objects
        max_images: Maximum number of unique images to generate

    Returns:
        List of scene groups, where each group shares one visual
    """
    if not scenes:
        return []

    if max_images >= len(scenes):
        # No consolidation needed - each scene gets its own image
        return [[s] for s in scenes]

    # Score all scenes
    scored_scenes = [(scene, score_scene_importance(scene)) for scene in scenes]

    # Group adjacent scenes of same type
    groups: List[List[VideoScene]] = []
    current_group: List[VideoScene] = [scenes[0]]

    for i in range(1, len(scenes)):
        prev_scene = scenes[i - 1]
        curr_scene = scenes[i]

        # Check if scenes can be grouped
        same_type = prev_scene.segment_type == curr_scene.segment_type
        close_in_time = (curr_scene.start_time - prev_scene.end_time) < 5.0  # Within 5 sec

        if same_type and close_in_time:
            current_group.append(curr_scene)
        else:
            groups.append(current_group)
            current_group = [curr_scene]

    groups.append(current_group)

    # If still too many groups, merge lowest-importance adjacent groups
    while len(groups) > max_images:
        # Find the pair of adjacent groups with lowest combined importance
        min_importance = float('inf')
        merge_idx = 0

        for i in range(len(groups) - 1):
            group_a_importance = max(score_scene_importance(s) for s in groups[i])
            group_b_importance = max(score_scene_importance(s) for s in groups[i + 1])
            combined = group_a_importance + group_b_importance

            if combined < min_importance:
                min_importance = combined
                merge_idx = i

        # Merge the two groups
        groups[merge_idx] = groups[merge_idx] + groups[merge_idx + 1]
        groups.pop(merge_idx + 1)

    return groups


def estimate_tier_costs(
    scenes: List[VideoScene],
    visual_plans: Optional[List[VisualPlan]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Estimate costs for each budget tier.

    Args:
        scenes: List of VideoScene objects
        visual_plans: Optional existing visual plans (for full tier baseline)

    Returns:
        Dictionary mapping tier name to cost breakdown
    """
    total_scenes = len(scenes)

    # Count scenes that would get Luma in full mode
    luma_candidates = sum(
        1 for s in scenes
        if s.animation_candidate and s.visual_complexity in ["medium", "high"]
    )

    # Count Ken Burns candidates
    ken_burns_candidates = sum(1 for s in scenes if s.ken_burns_enabled)

    estimates = {}

    for tier_name, tier_config in BUDGET_TIERS.items():
        max_images = tier_config["max_dalle_images"]
        max_luma = tier_config["max_luma_animations"]

        # Calculate actual counts for this tier
        if tier_config["text_overlay_all"]:
            dalle_count = 0
            luma_count = 0
            ken_burns_count = 0
            text_only_count = total_scenes
        else:
            # Consolidate to fit budget
            groups = consolidate_scenes(scenes, max_images)
            dalle_count = len(groups)

            # Luma only for highest-importance scenes up to limit
            if max_luma > 0:
                # Score groups and pick top N for Luma
                group_scores = []
                for group in groups:
                    max_score = max(score_scene_importance(s) for s in group)
                    has_luma_candidate = any(
                        s.animation_candidate and s.visual_complexity in ["medium", "high"]
                        for s in group
                    )
                    if has_luma_candidate:
                        group_scores.append(max_score)
                group_scores.sort(reverse=True)
                luma_count = min(max_luma, len(group_scores))
            else:
                luma_count = 0

            # Ken Burns for non-Luma scenes
            if tier_config["use_ken_burns"]:
                ken_burns_count = dalle_count - luma_count
            else:
                ken_burns_count = 0

            text_only_count = total_scenes - dalle_count

        # Calculate costs
        dalle_cost = dalle_count * DALLE_COST_PER_IMAGE
        luma_cost = luma_count * LUMA_COST_PER_ANIMATION
        total_cost = dalle_cost + luma_cost

        estimates[tier_name] = {
            "description": tier_config["description"],
            "dalle_images": dalle_count,
            "luma_animations": luma_count,
            "ken_burns": ken_burns_count,
            "text_only": text_only_count,
            "dalle_cost": round(dalle_cost, 2),
            "luma_cost": round(luma_cost, 2),
            "total_cost": round(total_cost, 2),
            "scenes_per_image": round(total_scenes / max(dalle_count, 1), 1),
        }

    return estimates


def select_scenes_for_generation(
    scenes: List[VideoScene],
    tier: str = "medium"
) -> Dict[str, Any]:
    """
    Select which scenes get visuals based on budget tier.

    Args:
        scenes: List of VideoScene objects
        tier: Budget tier name

    Returns:
        Dictionary with:
        - 'generate': List of scene groups that get DALL-E images
        - 'luma': List of scene IDs that get Luma animation
        - 'ken_burns': List of scene IDs that get Ken Burns
        - 'text_only': List of scene IDs that get text overlay only
    """
    tier_config = BUDGET_TIERS.get(tier, BUDGET_TIERS["medium"])

    if tier_config["text_overlay_all"]:
        return {
            "generate": [],
            "luma": [],
            "ken_burns": [],
            "text_only": [s.scene_id for s in scenes],
        }

    # Consolidate scenes into groups
    groups = consolidate_scenes(scenes, tier_config["max_dalle_images"])

    # Score groups for Luma selection
    group_data = []
    for group in groups:
        max_score = max(score_scene_importance(s) for s in group)
        has_luma_candidate = any(
            s.animation_candidate and s.visual_complexity in ["medium", "high"]
            for s in group
        )
        group_data.append({
            "group": group,
            "score": max_score,
            "luma_candidate": has_luma_candidate,
            "scene_ids": [s.scene_id for s in group],
        })

    # Sort by score for Luma allocation
    luma_eligible = [g for g in group_data if g["luma_candidate"]]
    luma_eligible.sort(key=lambda x: x["score"], reverse=True)

    # Allocate Luma to top N
    luma_ids = []
    for g in luma_eligible[:tier_config["max_luma_animations"]]:
        luma_ids.extend(g["scene_ids"])

    # Ken Burns for DALL-E scenes without Luma
    ken_burns_ids = []
    if tier_config["use_ken_burns"]:
        for g in group_data:
            for sid in g["scene_ids"]:
                if sid not in luma_ids:
                    ken_burns_ids.append(sid)

    # All scene IDs that are in groups (get DALL-E)
    generated_ids = set()
    for g in group_data:
        generated_ids.update(g["scene_ids"])

    # Text-only for scenes not in any group (shouldn't happen, but safety)
    text_only_ids = [s.scene_id for s in scenes if s.scene_id not in generated_ids]

    return {
        "generate": groups,
        "luma": luma_ids,
        "ken_burns": ken_burns_ids,
        "text_only": text_only_ids,
        "group_count": len(groups),
    }
