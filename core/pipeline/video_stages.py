"""Data loading and conversion for video production.

Load training trials, convert script segments to aligned format.
"""

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from core.models.structured_script import StructuredScript

console = Console()

def _get_theme():
    from cli.theme import get_theme
    return get_theme()

async def load_training_trial(trial_id: str) -> dict:
    """Load artifacts from a training trial"""
    base_path = Path("artifacts/training_output")

    # Find the trial directory (latest match, since timestamps are in the name)
    trial_dir = None
    matching_dirs = sorted(
        [d for d in base_path.iterdir() if d.is_dir() and trial_id in d.name]
    )
    if matching_dirs:
        trial_dir = matching_dirs[-1]

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
