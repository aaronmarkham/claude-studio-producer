"""Profile aggregation and synthesis"""

from collections import defaultdict
from datetime import datetime
from typing import List

from core.memory.manager import MemoryManager

from .models import (
    AggregatedProfile,
    DepthTarget,
    PodcastDepth,
    TrainingPair,
)


async def synthesize_profiles(
    training_pairs: List[TrainingPair],
) -> AggregatedProfile:
    """
    Combine individual profiles into unified template.

    Analyzes patterns across all training pairs to create a canonical
    structure and style template for podcast generation.
    """
    # Collect all structure and style profiles
    structures = [p.structure_profile for p in training_pairs if p.structure_profile]
    styles = [p.style_profile for p in training_pairs if p.style_profile]

    if not structures:
        raise ValueError("No structure profiles available for synthesis")

    # Find most common segment sequence pattern
    # For now, use the sequence from the first pair as canonical
    # (In production, would use sequence alignment or mode)
    canonical_sequence = structures[0].segment_sequence

    # Calculate duration targets from data
    segment_durations = defaultdict(list)
    for struct in structures:
        for seg_type, durations in struct.segment_durations.items():
            segment_durations[seg_type].extend(durations)

    duration_targets = {
        seg_type: (min(durs), max(durs)) if durs else (0.0, 0.0)
        for seg_type, durs in segment_durations.items()
    }

    # Group styles by speaker
    style_variants = {}
    for pair in training_pairs:
        if pair.style_profile:
            key = f"{pair.speaker_gender}_{pair.pair_id}"
            style_variants[key] = pair.style_profile

    # Extract common phrases
    all_intro = [phrase for s in styles for phrase in s.intro_phrases]
    all_transition = [phrase for s in styles for phrase in s.transition_phrases]
    all_figure = [s.figure_intro_pattern for s in styles if s.figure_intro_pattern]

    universal_intro = list(set(all_intro))[:10]  # Top 10 unique
    universal_transition = list(set(all_transition))[:10]
    universal_figure = list(set(all_figure))[:5]

    # Calculate quality thresholds
    avg_wpm = sum(s.words_per_minute for s in structures) / len(structures)
    avg_cpm = sum(s.concepts_per_minute for s in structures) / len(structures)

    wpm_range = (avg_wpm * 0.8, avg_wpm * 1.2)  # +/- 20%
    cpm_range = (avg_cpm * 0.7, avg_cpm * 1.3)  # +/- 30%

    # Calculate depth targets
    depth_targets = calculate_depth_targets(structures, training_pairs)

    return AggregatedProfile(
        canonical_segment_sequence=canonical_sequence,
        segment_duration_targets=duration_targets,
        depth_targets=depth_targets,
        style_variants=style_variants,
        universal_intro_patterns=universal_intro,
        universal_transition_patterns=universal_transition,
        universal_figure_patterns=universal_figure,
        min_coverage=0.7,  # Expect 70% concept coverage minimum
        target_words_per_minute=wpm_range,
        target_concepts_per_minute=cpm_range,
        version="v1",
        training_pairs_used=[p.pair_id for p in training_pairs],
        created_at=datetime.now(),
    )


def calculate_depth_targets(structures, training_pairs) -> dict:
    """Calculate targets for different podcast depth levels."""

    # Group by duration
    durations = [s.total_duration for s in structures]
    avg_duration = sum(durations) / len(durations)

    # Define depth targets based on average
    targets = {}

    targets[PodcastDepth.STANDARD.value] = DepthTarget(
        depth=PodcastDepth.STANDARD,
        duration_range=(avg_duration * 0.8, avg_duration * 1.2),
        segment_count_range=(len(structures[0].segment_sequence) - 2,
                             len(structures[0].segment_sequence) + 2),
        concepts_per_segment=(2, 5),
        figure_coverage=0.6,  # Discuss 60% of figures
        example_pair_ids=[p.pair_id for p in training_pairs],
    )

    return targets


async def store_profile_in_memory(
    profile: AggregatedProfile,
    memory_manager: MemoryManager,
    output_dir: Path = None,
):
    """Store aggregated profile for agent use."""
    from pathlib import Path
    import json

    # Save to training output directory
    if output_dir is None:
        output_dir = Path("artifacts/training_output")

    profile_file = output_dir / "aggregated_profile.json"
    profile_data = {
        "version": profile.version,
        "training_pairs_used": profile.training_pairs_used,
        "created_at": profile.created_at.isoformat(),
        "profile": profile.to_dict(),
    }

    profile_file.write_text(json.dumps(profile_data, indent=2, default=str))

    # Store canonical sequence separately for easy access
    await memory_manager.store(
        namespace=f"{namespace}/structure",
        key="canonical_sequence",
        data={"sequence": [s.value for s in profile.canonical_segment_sequence]}
    )

    # Store style patterns
    await memory_manager.store(
        namespace=f"{namespace}/style",
        key="patterns",
        data={
            "intro": profile.universal_intro_patterns,
            "transition": profile.universal_transition_patterns,
            "figure": profile.universal_figure_patterns,
        }
    )
