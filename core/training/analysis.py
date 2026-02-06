"""Segment classification and profile extraction"""

import json
from collections import Counter, defaultdict
from typing import Dict, List, Optional

import textstat

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


def calculate_vocabulary_complexity(text: str) -> float:
    """
    Calculate vocabulary complexity using textstat metrics.

    Returns a normalized score between 0 and 1, where:
    - 0.0-0.3: Simple vocabulary (elementary level)
    - 0.3-0.5: Moderate vocabulary (high school level)
    - 0.5-0.7: Advanced vocabulary (college level)
    - 0.7-1.0: Complex vocabulary (professional/academic)
    """
    if not text or len(text.strip()) == 0:
        return 0.5

    # Get multiple readability scores
    flesch_reading_ease = textstat.flesch_reading_ease(text)  # 0-100, higher = easier
    flesch_kincaid_grade = textstat.flesch_kincaid_grade(text)  # US grade level
    dale_chall_score = textstat.dale_chall_readability_score(text)  # 4.9-16+

    # Normalize Flesch Reading Ease (invert since higher = easier)
    # 100-90 (very easy) -> 0.0-0.1
    # 50-60 (standard) -> 0.4-0.5
    # 0-30 (very difficult) -> 0.7-1.0
    normalized_flesch = (100 - max(0, min(100, flesch_reading_ease))) / 100

    # Normalize Flesch-Kincaid Grade Level
    # Grade 0-5 -> 0.0-0.25
    # Grade 8-12 -> 0.40-0.60
    # Grade 16+ -> 0.80-1.0
    normalized_fk = min(1.0, max(0, flesch_kincaid_grade) / 20)

    # Normalize Dale-Chall (4.9 = easy, 9.9+ = very difficult)
    # 4.9 = 0.0, 7.0 = 0.42, 9.9+ = 1.0
    normalized_dc = min(1.0, max(0, (dale_chall_score - 4.9) / 5.0))

    # Weighted average (emphasize Flesch-Kincaid as it's most reliable)
    complexity = (0.4 * normalized_fk + 0.3 * normalized_flesch + 0.3 * normalized_dc)

    return round(complexity, 3)


async def classify_segments(
    transcription: TranscriptionResult,
    document_graph: DocumentGraph,
    claude_client: ClaudeClient,
) -> tuple[List[AlignedSegment], Optional[Dict[str, int]]]:
    """
    Use LLM to classify each transcript segment and align to PDF atoms.

    Analyzes each segment to determine its type, what paper content it discusses,
    and extracts key concepts, analogies, questions, etc.

    Processes segments in batches to handle transcripts of any length.
    """
    # Build context about the paper from KnowledgeGraph
    title = getattr(document_graph, 'project_id', 'Unknown')
    abstract = getattr(document_graph, 'unified_summary', 'N/A')[:500]
    themes = getattr(document_graph, 'key_themes', [])

    # Process segments in batches of 40 to stay within token limits
    BATCH_SIZE = 40
    all_segments_data = []
    total_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}

    total_segments = len(transcription.segments)
    num_batches = (total_segments + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total_segments)
        batch_segments = transcription.segments[start_idx:end_idx]

        print(f"  Classifying batch {batch_idx + 1}/{num_batches} (segments {start_idx}-{end_idx - 1})...")

        # Build segment list for JSON
        segments_for_prompt = [
            {
                'id': s.segment_id,
                'text': s.text,
                'time': f'{s.start_time:.1f}-{s.end_time:.1f}s'
            }
            for s in batch_segments
        ]
        segments_json = json.dumps(segments_for_prompt, indent=2)

        prompt = f"""Analyze this podcast transcript segment by segment and classify each one.

PAPER BEING DISCUSSED:
Title: {title}
Summary: {abstract}
Key Themes: {', '.join(themes) if themes else 'N/A'}

TRANSCRIPT (segmented):
{segments_json}

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

        response, usage = await claude_client.query(prompt, return_usage=True)

        # Accumulate usage
        if usage:
            total_usage['input_tokens'] += usage.get('input_tokens', 0)
            total_usage['output_tokens'] += usage.get('output_tokens', 0)
            total_usage['total_tokens'] += usage.get('total_tokens', 0)

        # Parse response using JSONExtractor to handle markdown code fences
        try:
            from core.claude_client import JSONExtractor
            data = JSONExtractor.extract(response)
            batch_data = data.get("segments", [])
            all_segments_data.extend(batch_data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  WARNING: Failed to parse batch {batch_idx + 1} response: {e}")

    # Log total usage
    if total_usage['total_tokens'] > 0:
        print(f"  Total API usage: {total_usage['input_tokens']} in + {total_usage['output_tokens']} out = {total_usage['total_tokens']} tokens")

    # Create AlignedSegment objects
    aligned_segments = []
    segments_data = all_segments_data  # Use combined data from all batches
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

    return aligned_segments, total_usage


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
) -> tuple[StyleProfile, Optional[Dict[str, int]]]:
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

    response, usage = await claude_client.query(prompt, return_usage=True)

    # Log usage if available
    if usage:
        print(f"  API usage: {usage['input_tokens']} in + {usage['output_tokens']} out = {usage['total_tokens']} tokens")

    # Parse response using JSONExtractor to handle markdown code fences
    try:
        from core.claude_client import JSONExtractor
        data = JSONExtractor.extract(response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  WARNING: Failed to parse style profile response: {e}")
        data = {}

    # Count questions and analogies
    total_questions = sum(len(s.questions_asked) for s in aligned_segments)
    total_analogies = sum(len(s.analogies_used) for s in aligned_segments)
    duration_minutes = transcription.total_duration / 60.0 if transcription.total_duration > 0 else 1.0

    # Calculate vocabulary complexity using textstat
    vocab_complexity = calculate_vocabulary_complexity(transcription.transcript_text)

    profile = StyleProfile(
        speaker_id=transcription.speaker_id or "unknown",
        speaker_gender=speaker_gender,
        avg_sentence_length=data.get("avg_sentence_length", 15.0),
        vocabulary_complexity=vocab_complexity,
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

    return profile, usage
