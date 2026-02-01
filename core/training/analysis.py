"""Segment classification and profile extraction"""

import json
from collections import Counter, defaultdict
from typing import List

from core.claude_client import ClaudeClient
from core.models.knowledge import KnowledgeGraph as DocumentGraph

from .models import (
    AlignedSegment,
    SegmentType,
    StructureProfile,
    StyleProfile,
    TranscriptionResult,
    TranscriptSegment,
)


async def classify_segments(
    transcription: TranscriptionResult,
    document_graph: DocumentGraph,
    claude_client: ClaudeClient,
) -> List[AlignedSegment]:
    """
    Use LLM to classify each transcript segment and align to PDF atoms.

    Analyzes each segment to determine its type, what paper content it discusses,
    and extracts key concepts, analogies, questions, etc.
    """
    # Build context about the paper from KnowledgeGraph
    title = getattr(document_graph, 'project_id', 'Unknown')
    abstract = getattr(document_graph, 'unified_summary', 'N/A')[:500]
    themes = getattr(document_graph, 'key_themes', [])

    prompt = f"""Analyze this podcast transcript segment by segment and classify each one.

PAPER BEING DISCUSSED:
Title: {title}
Summary: {abstract}
Key Themes: {', '.join(themes) if themes else 'N/A'}

TRANSCRIPT (segmented):
{json.dumps([{{'id': s.segment_id, 'text': s.text, 'time': f'{s.start_time:.1f}-{s.end_time:.1f}s'}} for s in transcription.segments[:50]], indent=2)}

For each segment, identify:
1. segment_type: One of {[t.value for t in SegmentType]}
2. key_concepts: Main ideas mentioned (list of strings)
3. technical_terms: Technical vocabulary used (list of strings)
4. analogies_used: Any analogies or metaphors (list of strings)
5. questions_asked: Rhetorical or actual questions (list of strings)
6. referenced_figures: Figure numbers mentioned (list of ints, e.g., [1, 2])

Return as JSON array with one entry per segment:
{{
    "segments": [
        {{
            "segment_id": "seg_000",
            "segment_type": "intro",
            "key_concepts": ["concept1", "concept2"],
            "technical_terms": ["term1"],
            "analogies_used": ["analogy1"],
            "questions_asked": ["question1"],
            "referenced_figures": [1]
        }},
        ...
    ]
}}
"""

    response = await claude_client.query(prompt, response_format="json")

    # Parse response
    try:
        data = json.loads(response)
        segments_data = data.get("segments", [])
    except json.JSONDecodeError:
        # Fallback: create basic aligned segments
        segments_data = []

    # Create AlignedSegment objects
    aligned_segments = []
    for i, trans_seg in enumerate(transcription.segments):
        # Find matching data
        seg_data = next((s for s in segments_data if s.get("segment_id") == trans_seg.segment_id), {})

        # Parse segment type
        seg_type_str = seg_data.get("segment_type", "intro")
        try:
            seg_type = SegmentType(seg_type_str)
        except ValueError:
            seg_type = SegmentType.INTRO

        # Calculate words per minute
        word_count = len(trans_seg.text.split())
        duration_minutes = trans_seg.duration / 60.0 if trans_seg.duration > 0 else 1.0
        wpm = word_count / duration_minutes

        aligned_seg = AlignedSegment(
            segment_id=trans_seg.segment_id,
            transcript_segment=trans_seg,
            segment_type=seg_type,
            key_concepts=seg_data.get("key_concepts", []),
            technical_terms=seg_data.get("technical_terms", []),
            analogies_used=seg_data.get("analogies_used", []),
            questions_asked=seg_data.get("questions_asked", []),
            referenced_figures=[f"fig_{n}" for n in seg_data.get("referenced_figures", [])],
            words_per_minute=wpm,
            density_score=len(seg_data.get("key_concepts", [])) / max(trans_seg.duration, 1.0),
        )
        aligned_segments.append(aligned_seg)

    return aligned_segments


async def extract_structure_profile(
    aligned_segments: List[AlignedSegment],
    transcription: TranscriptionResult,
) -> StructureProfile:
    """Extract structural patterns from analyzed podcast."""

    segment_sequence = [s.segment_type for s in aligned_segments]

    # Calculate timing distributions
    segment_durations = defaultdict(list)
    for seg in aligned_segments:
        segment_durations[seg.segment_type.value].append(seg.transcript_segment.duration)

    total_duration = transcription.total_duration
    word_count = len(transcription.transcript_text.split())

    # Calculate concept metrics
    total_concepts = sum(len(s.key_concepts) for s in aligned_segments)
    duration_minutes = total_duration / 60.0 if total_duration > 0 else 1.0

    # Count figures discussed
    figures_discussed = sum(1 for s in aligned_segments if s.referenced_figures)
    figure_segments = [s for s in aligned_segments if s.segment_type == SegmentType.FIGURE_DISCUSSION]
    figure_discussion_duration = sum(s.transcript_segment.duration for s in figure_segments)

    # Calculate percentages by type
    type_durations = defaultdict(float)
    for seg in aligned_segments:
        type_durations[seg.segment_type.value] += seg.transcript_segment.duration

    intro_percentage = (type_durations[SegmentType.INTRO.value] / total_duration * 100) if total_duration > 0 else 0
    methodology_percentage = (type_durations[SegmentType.METHODOLOGY.value] / total_duration * 100) if total_duration > 0 else 0
    findings_percentage = (type_durations[SegmentType.KEY_FINDING.value] / total_duration * 100) if total_duration > 0 else 0
    conclusion_percentage = (type_durations[SegmentType.CONCLUSION.value] / total_duration * 100) if total_duration > 0 else 0

    return StructureProfile(
        segment_sequence=segment_sequence,
        segment_counts={t.value: segment_sequence.count(t) for t in SegmentType},
        total_duration=total_duration,
        segment_durations=dict(segment_durations),
        avg_segment_duration=total_duration / len(aligned_segments) if aligned_segments else 0,
        words_per_minute=word_count / duration_minutes,
        concepts_per_minute=total_concepts / duration_minutes,
        figures_discussed=figures_discussed,
        figure_discussion_duration=figure_discussion_duration,
        intro_percentage=intro_percentage,
        methodology_percentage=methodology_percentage,
        findings_percentage=findings_percentage,
        conclusion_percentage=conclusion_percentage,
        transition_phrases=[],  # Filled in by style analysis
    )


async def extract_style_profile(
    aligned_segments: List[AlignedSegment],
    transcription: TranscriptionResult,
    speaker_gender: str,
    claude_client: ClaudeClient,
) -> StyleProfile:
    """Extract style patterns using LLM analysis."""

    prompt = f"""Analyze the speaking style of this podcast transcript.

TRANSCRIPT:
{transcription.transcript_text[:5000]}...

Extract the following patterns:

1. Common phrases used to:
   - Introduce the paper (e.g., "Today we're looking at...", "This paper examines...")
   - Transition between topics (e.g., "Now, turning to...", "Let's move on to...")
   - Emphasize important points (e.g., "This is crucial because...", "The key finding is...")
   - Conclude sections (e.g., "So what does this mean?", "To summarize...")

2. Explanation style:
   - How are technical terms defined? ("inline", "parenthetical", "before_use")
   - Average examples per concept (estimate 0-3)

3. Engagement techniques:
   - Questions per minute (estimate)
   - Enthusiasm markers (phrases like "fascinating", "remarkable", etc.)

4. Language complexity:
   - Average sentence length in words (estimate)
   - Technical term density (0-1, where 1 is very technical)

Return as JSON:
{{
    "intro_phrases": ["phrase1", "phrase2", ...],
    "transition_phrases": ["phrase1", ...],
    "emphasis_phrases": ["phrase1", ...],
    "conclusion_phrases": ["phrase1", ...],
    "definition_style": "inline" | "parenthetical" | "before_use",
    "example_frequency": 1.5,
    "questions_per_minute": 0.5,
    "enthusiasm_markers": ["fascinating", "remarkable", ...],
    "avg_sentence_length": 15.0,
    "jargon_density": 0.3,
    "figure_intro_pattern": "Now let's look at Figure X which shows...",
    "figure_explanation_depth": "brief" | "moderate" | "detailed"
}}
"""

    response = await claude_client.query(prompt, response_format="json")

    # Parse response
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        data = {}

    # Count questions and analogies
    total_questions = sum(len(s.questions_asked) for s in aligned_segments)
    total_analogies = sum(len(s.analogies_used) for s in aligned_segments)
    duration_minutes = transcription.total_duration / 60.0 if transcription.total_duration > 0 else 1.0

    return StyleProfile(
        speaker_id=transcription.speaker_id or "unknown",
        speaker_gender=speaker_gender,
        avg_sentence_length=data.get("avg_sentence_length", 15.0),
        vocabulary_complexity=0.5,  # Placeholder
        jargon_density=data.get("jargon_density", 0.3),
        questions_per_minute=total_questions / duration_minutes,
        analogies_per_segment=total_analogies / len(aligned_segments) if aligned_segments else 0,
        enthusiasm_markers=data.get("enthusiasm_markers", []),
        definition_style=data.get("definition_style", "inline"),
        example_frequency=data.get("example_frequency", 1.0),
        intro_phrases=data.get("intro_phrases", []),
        transition_phrases=data.get("transition_phrases", []),
        emphasis_phrases=data.get("emphasis_phrases", []),
        conclusion_phrases=data.get("conclusion_phrases", []),
        figure_intro_pattern=data.get("figure_intro_pattern", ""),
        figure_explanation_depth=data.get("figure_explanation_depth", "moderate"),
    )
