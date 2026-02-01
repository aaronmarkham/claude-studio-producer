"""Loss metric calculations for training evaluation"""

import json
from collections import Counter
from datetime import datetime
from typing import Dict, List, Tuple

from rouge_score import rouge_scorer

from core.claude_client import ClaudeClient
from core.models.knowledge import KnowledgeGraph as DocumentGraph

from .models import AlignedSegment, LossMetrics, SegmentType, TranscriptionResult


def calculate_duration_loss(
    generated_duration: float,
    reference_duration: float,
) -> Tuple[float, Dict]:
    """
    Calculate how close generated duration is to reference.

    Returns:
        loss: Normalized difference (0 = perfect match)
        details: Breakdown of calculation
    """
    diff = abs(generated_duration - reference_duration)
    loss = diff / reference_duration if reference_duration > 0 else 0.0

    return loss, {
        "generated_seconds": generated_duration,
        "reference_seconds": reference_duration,
        "diff_seconds": diff,
        "diff_percentage": loss * 100,
    }


async def calculate_coverage_loss(
    generated_transcript: str,
    document_graph: DocumentGraph,
    claude_client: ClaudeClient,
) -> Tuple[float, Dict]:
    """
    Calculate what percentage of key concepts were covered.

    Uses LLM to check if each key concept from the paper
    is mentioned/explained in the generated transcript.
    """
    # Extract key concepts from paper
    key_concepts = extract_key_concepts(document_graph)

    if not key_concepts:
        return 0.0, {
            "concepts_total": 0,
            "concepts_covered": 0,
            "concepts_missed": [],
            "coverage_by_depth": {},
        }

    prompt = f"""Check which concepts from this paper are covered in the podcast transcript.

PAPER KEY CONCEPTS:
{json.dumps(key_concepts, indent=2)}

PODCAST TRANSCRIPT:
{generated_transcript[:3000]}...

For each concept, determine:
- covered: true/false (is it mentioned or explained?)
- depth: "not_mentioned" | "briefly_mentioned" | "explained" | "deeply_explained"

Return JSON: {{"concepts": [{{"concept": "...", "covered": true, "depth": "explained"}}]}}
"""

    response, usage = await claude_client.query(prompt, return_usage=True)

    # Parse response
    try:
        data = json.loads(response)
        results = data.get("concepts", [])
    except json.JSONDecodeError:
        results = []

    covered = [c for c in results if c.get("covered", False)]
    coverage_ratio = len(covered) / len(key_concepts) if key_concepts else 1.0

    return 1 - coverage_ratio, {
        "concepts_total": len(key_concepts),
        "concepts_covered": len(covered),
        "concepts_missed": [c.get("concept", "") for c in results if not c.get("covered", False)],
        "coverage_by_depth": {
            "deeply_explained": len([c for c in covered if c.get("depth") == "deeply_explained"]),
            "explained": len([c for c in covered if c.get("depth") == "explained"]),
            "briefly_mentioned": len([c for c in covered if c.get("depth") == "briefly_mentioned"]),
        }
    }


def extract_key_concepts(document_graph: DocumentGraph) -> List[str]:
    """Extract key concepts from document graph."""
    concepts = []

    # Add title/project_id as key concept
    if hasattr(document_graph, 'project_id') and document_graph.project_id:
        concepts.append(document_graph.project_id.replace("-", " ").replace("_", " ").title())

    # Add key themes
    if hasattr(document_graph, 'key_themes') and document_graph.key_themes:
        concepts.extend(document_graph.key_themes[:5])

    # Extract from summary if available
    if hasattr(document_graph, 'unified_summary') and document_graph.unified_summary:
        summary_words = document_graph.unified_summary.split()
        if len(summary_words) > 10:
            concepts.append(" ".join(summary_words[:20]))

    # Limit to reasonable number
    return list(set(concepts))[:10]  # Deduplicate and limit


async def calculate_structure_loss(
    generated_segments: List[SegmentType],
    reference_aligned: List[AlignedSegment],
) -> Tuple[float, Dict]:
    """
    Calculate structural similarity to reference.

    Uses edit distance and segment type distribution similarity.
    """
    ref_sequence = [s.segment_type for s in reference_aligned]

    # Sequence similarity using edit distance
    edit_distance = levenshtein_distance(generated_segments, ref_sequence)
    max_len = max(len(generated_segments), len(ref_sequence))
    sequence_similarity = 1 - (edit_distance / max_len) if max_len > 0 else 1.0

    # Segment type distribution similarity
    gen_dist = Counter([s.value if hasattr(s, 'value') else s for s in generated_segments])
    ref_dist = Counter([s.value for s in ref_sequence])

    all_types = set(gen_dist.keys()) | set(ref_dist.keys())
    total_diff = sum(abs(gen_dist.get(t, 0) - ref_dist.get(t, 0)) for t in all_types)
    total_count = len(generated_segments) + len(ref_sequence)
    dist_similarity = 1 - (total_diff / total_count) if total_count > 0 else 1.0

    # Combined structure loss
    structure_loss = 1 - (0.6 * sequence_similarity + 0.4 * dist_similarity)

    return structure_loss, {
        "sequence_similarity": sequence_similarity,
        "distribution_similarity": dist_similarity,
        "edit_distance": edit_distance,
        "generated_segment_count": len(generated_segments),
        "reference_segment_count": len(ref_sequence),
    }


def levenshtein_distance(seq1: List, seq2: List) -> int:
    """Calculate Levenshtein distance between two sequences."""
    if len(seq1) < len(seq2):
        return levenshtein_distance(seq2, seq1)

    if len(seq2) == 0:
        return len(seq1)

    previous_row = range(len(seq2) + 1)
    for i, c1 in enumerate(seq1):
        current_row = [i + 1]
        for j, c2 in enumerate(seq2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


async def calculate_quality_loss(
    generated_transcript: str,
    reference_transcript: str,
    document_graph: DocumentGraph,
    claude_client: ClaudeClient,
) -> Tuple[float, Dict]:
    """
    Use LLM to judge quality on engagement, clarity, accuracy.

    Returns quality loss (lower is better) and detailed scores.
    """
    # Extract title and summary from KnowledgeGraph
    title = getattr(document_graph, 'project_id', 'Unknown')
    summary = getattr(document_graph, 'unified_summary', 'N/A')[:500]

    prompt = f"""You are evaluating a generated podcast transcript against a human-created reference.

PAPER BEING DISCUSSED:
Title: {title}
Summary: {summary}

REFERENCE TRANSCRIPT (human-created, gold standard):
{reference_transcript[:2000]}...

GENERATED TRANSCRIPT (to evaluate):
{generated_transcript[:2000]}...

Score the GENERATED transcript on these criteria (0-100 each):

1. ENGAGEMENT: How engaging and interesting is it?
   - Does it use questions, analogies, enthusiasm markers?
   - Would a listener stay interested?

2. CLARITY: How clear are the explanations?
   - Are technical terms defined?
   - Is the structure logical?
   - Are examples used effectively?

3. ACCURACY: How faithful is it to the paper?
   - Are claims accurate?
   - Are nuances preserved?
   - Any misrepresentations?

Return JSON:
{{
    "engagement_score": 75,
    "clarity_score": 80,
    "accuracy_score": 85,
    "reference_strengths": ["strength1", "strength2"],
    "generated_strengths": ["strength1"],
    "improvement_suggestions": ["suggestion1", "suggestion2"]
}}
"""

    response, usage = await claude_client.query(prompt, return_usage=True)

    # Parse response
    try:
        data = json.loads(response)
        engagement = data.get("engagement_score", 50)
        clarity = data.get("clarity_score", 50)
        accuracy = data.get("accuracy_score", 50)
    except json.JSONDecodeError:
        engagement = clarity = accuracy = 50
        data = {}

    # Calculate quality loss (inverted from scores)
    quality_loss = (300 - (engagement + clarity + accuracy)) / 300

    return quality_loss, {
        "engagement_score": engagement,
        "clarity_score": clarity,
        "accuracy_score": accuracy,
        "reference_strengths": data.get("reference_strengths", []),
        "generated_strengths": data.get("generated_strengths", []),
        "improvement_suggestions": data.get("improvement_suggestions", []),
    }


def calculate_rouge_loss(
    generated_transcript: str,
    reference_transcript: str,
) -> Tuple[float, Dict]:
    """
    Calculate ROUGE scores for text similarity.

    ROUGE (Recall-Oriented Understudy for Gisting Evaluation):
    - ROUGE-1: Unigram (single word) overlap
    - ROUGE-2: Bigram (two word) overlap
    - ROUGE-L: Longest common subsequence

    Higher ROUGE = more similar to reference.
    For loss, we use 1 - ROUGE.
    """
    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
    scores = scorer.score(reference_transcript, generated_transcript)

    rouge_1 = scores['rouge1'].fmeasure
    rouge_2 = scores['rouge2'].fmeasure
    rouge_l = scores['rougeL'].fmeasure

    avg_rouge = (rouge_1 + rouge_2 + rouge_l) / 3
    rouge_loss = 1 - avg_rouge

    return rouge_loss, {
        "rouge_1": rouge_1,
        "rouge_2": rouge_2,
        "rouge_l": rouge_l,
        "interpretation": {
            "rouge_1": "Good" if rouge_1 > 0.4 else "Needs improvement",
            "rouge_2": "Good" if rouge_2 > 0.2 else "Needs improvement",
            "rouge_l": "Good" if rouge_l > 0.3 else "Needs improvement",
        },
        "note": "ROUGE measures n-gram overlap with reference. Higher is more similar."
    }


def calculate_total_loss(metrics: LossMetrics, weights: Dict[str, float] = None) -> float:
    """
    Calculate weighted total loss.

    Default weights emphasize duration and coverage.
    """
    weights = weights or {
        "duration": 0.25,
        "coverage": 0.25,
        "structure": 0.20,
        "quality": 0.20,
        "rouge": 0.10,
    }

    return (
        weights["duration"] * metrics.duration_loss +
        weights["coverage"] * metrics.coverage_loss +
        weights["structure"] * metrics.structure_loss +
        weights["quality"] * metrics.quality_loss +
        weights["rouge"] * metrics.rouge_loss
    )


async def calculate_all_metrics(
    generated_script: str,
    generated_duration: float,
    reference_transcription: TranscriptionResult,
    reference_aligned: List[AlignedSegment],
    document_graph: DocumentGraph,
    claude_client: ClaudeClient,
    trial_id: str,
    pair_id: str,
    weights: Dict[str, float],
) -> LossMetrics:
    """
    Calculate all loss metrics for a generated podcast.

    Returns comprehensive LossMetrics object with all scores.
    """
    # Duration loss
    duration_loss, duration_details = calculate_duration_loss(
        generated_duration,
        reference_transcription.total_duration
    )

    # Coverage loss
    coverage_loss, coverage_details = await calculate_coverage_loss(
        generated_script,
        document_graph,
        claude_client,
    )

    # Structure loss (simplified - would need to parse generated segments)
    # For now, use a placeholder
    structure_loss = 0.3  # Placeholder
    segment_type_accuracy = 0.7
    sequence_similarity = 0.7

    # Quality loss
    quality_loss, quality_details = await calculate_quality_loss(
        generated_script,
        reference_transcription.transcript_text,
        document_graph,
        claude_client,
    )

    # ROUGE loss
    rouge_loss, rouge_details = calculate_rouge_loss(
        generated_script,
        reference_transcription.transcript_text
    )

    # Create metrics object
    metrics = LossMetrics(
        duration_loss=duration_loss,
        duration_generated=generated_duration,
        duration_reference=reference_transcription.total_duration,
        coverage_loss=coverage_loss,
        concepts_mentioned=coverage_details["concepts_covered"],
        concepts_total=coverage_details["concepts_total"],
        concepts_missed=coverage_details["concepts_missed"],
        structure_loss=structure_loss,
        segment_type_accuracy=segment_type_accuracy,
        sequence_similarity=sequence_similarity,
        engagement_score=quality_details["engagement_score"],
        clarity_score=quality_details["clarity_score"],
        accuracy_score=quality_details["accuracy_score"],
        quality_loss=quality_loss,
        rouge_1=rouge_details["rouge_1"],
        rouge_2=rouge_details["rouge_2"],
        rouge_l=rouge_details["rouge_l"],
        rouge_loss=rouge_loss,
        total_loss=0.0,  # Calculated below
        trial_id=trial_id,
        pair_id=pair_id,
        generated_at=datetime.now(),
    )

    # Calculate total loss
    metrics.total_loss = calculate_total_loss(metrics, weights)

    return metrics
