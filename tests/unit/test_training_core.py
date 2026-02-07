"""Training pipeline unit tests

Tests pure-computation functions from the training pipeline:
- Loss functions (duration, ROUGE, total, levenshtein)
- Key concept extraction
- Vocabulary complexity calculation
- Structure profile extraction
- Convergence checking
- Depth target calculation
- Data model construction and serialization

No API calls — only tests deterministic, pure functions.
"""

import pytest
import numpy as np
from datetime import datetime
from collections import Counter
from unittest.mock import MagicMock

from core.training.models import (
    SegmentType,
    PodcastDepth,
    WordTimestamp,
    TranscriptSegment,
    TranscriptionResult,
    AlignedSegment,
    StructureProfile,
    StyleProfile,
    AggregatedProfile,
    LossMetrics,
    TrainingConfig,
    TrainingPair,
    TrialResult,
    DepthTarget,
)
from core.training.loss import (
    calculate_duration_loss,
    calculate_rouge_loss,
    calculate_total_loss,
    levenshtein_distance,
    extract_key_concepts,
    calculate_structure_loss,
)
from core.training.analysis import (
    calculate_vocabulary_complexity,
    extract_structure_profile,
)
from core.training.synthesis import calculate_depth_targets
from core.training.trainer import check_convergence


# ============================================================
# Factories
# ============================================================

def _transcript_segment(
    seg_id="seg_1",
    text="Test segment text.",
    start=0.0,
    end=5.0,
    seg_type=None,
) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=seg_id,
        text=text,
        start_time=start,
        end_time=end,
        duration=end - start,
        segment_type=seg_type,
    )


def _aligned_segment(
    seg_id="seg_1",
    seg_type=SegmentType.INTRO,
    text="Test segment.",
    start=0.0,
    end=10.0,
    concepts=None,
    figures=None,
    wpm=150.0,
) -> AlignedSegment:
    return AlignedSegment(
        segment_id=seg_id,
        transcript_segment=_transcript_segment(seg_id, text, start, end),
        segment_type=seg_type,
        key_concepts=concepts or [],
        referenced_figures=figures or [],
        words_per_minute=wpm,
    )


def _transcription(
    text="Hello world this is a test transcript.",
    duration=600.0,
    segments=None,
) -> TranscriptionResult:
    return TranscriptionResult(
        source_path="/test/audio.mp3",
        transcript_text=text,
        word_timestamps=[],
        segments=segments or [_transcript_segment()],
        total_duration=duration,
        speaker_id="test_speaker",
        confidence=0.95,
    )


def _loss_metrics(**overrides) -> LossMetrics:
    defaults = dict(
        duration_loss=0.1,
        duration_generated=550.0,
        duration_reference=600.0,
        coverage_loss=0.2,
        concepts_mentioned=8,
        concepts_total=10,
        concepts_missed=["concept_a", "concept_b"],
        structure_loss=0.15,
        segment_type_accuracy=0.85,
        sequence_similarity=0.90,
        engagement_score=75.0,
        clarity_score=80.0,
        accuracy_score=85.0,
        quality_loss=0.2,
        rouge_1=0.45,
        rouge_2=0.25,
        rouge_l=0.35,
        rouge_loss=0.65,
        total_loss=0.0,
        trial_id="trial_000",
        pair_id="pair_001",
    )
    defaults.update(overrides)
    return LossMetrics(**defaults)


def _trial_result(
    trial_id="trial_000",
    trial_num=0,
    avg_loss=0.5,
    **overrides,
) -> TrialResult:
    defaults = dict(
        trial_id=trial_id,
        trial_number=trial_num,
        pair_results={},
        avg_total_loss=avg_loss,
        avg_duration_loss=0.1,
        avg_coverage_loss=0.2,
        avg_structure_loss=0.15,
        avg_quality_loss=0.2,
        avg_rouge_loss=0.6,
        generated_scripts={},
        generated_audio={},
        prompt_version="v1",
        profile_version="v1",
    )
    defaults.update(overrides)
    return TrialResult(**defaults)


# ============================================================
# Enums & Basic Models
# ============================================================

class TestSegmentType:
    def test_all_types_exist(self):
        expected = [
            "intro", "background", "problem", "methodology",
            "key_finding", "figure", "implication", "limitation",
            "conclusion", "tangent", "transition",
        ]
        for val in expected:
            assert SegmentType(val) is not None

    def test_segment_type_is_string(self):
        assert SegmentType.INTRO.value == "intro"
        assert isinstance(SegmentType.INTRO, str)

    def test_from_value(self):
        assert SegmentType("intro") == SegmentType.INTRO
        assert SegmentType("key_finding") == SegmentType.KEY_FINDING


class TestPodcastDepth:
    def test_all_depths(self):
        assert PodcastDepth.OVERVIEW.value == "overview"
        assert PodcastDepth.STANDARD.value == "standard"
        assert PodcastDepth.DEEP_DIVE.value == "deep_dive"
        assert PodcastDepth.COMPREHENSIVE.value == "comprehensive"


class TestTrainingModels:
    def test_word_timestamp(self):
        wt = WordTimestamp(word="hello", start_time=0.0, end_time=0.5)
        assert wt.confidence == 1.0  # default

    def test_transcript_segment(self):
        seg = _transcript_segment("s1", "Hello world", 0.0, 3.0)
        assert seg.duration == 3.0
        assert seg.segment_type is None

    def test_transcription_result(self):
        tr = _transcription(duration=120.0)
        assert tr.total_duration == 120.0
        assert tr.language == "en"

    def test_aligned_segment_defaults(self):
        seg = _aligned_segment()
        assert seg.primary_atoms == []
        assert seg.density_score == 0.0

    def test_training_pair(self):
        pair = TrainingPair(
            pair_id="paper_001",
            pdf_path="/data/paper.pdf",
            audio_path="/data/paper.mp3",
        )
        assert pair.document_graph is None
        assert pair.speaker_gender == "unknown"
        assert pair.duration_minutes == 0.0

    def test_training_config_defaults(self):
        config = TrainingConfig()
        assert config.max_trials == 5
        assert config.convergence_threshold == 0.05
        assert config.target_depth == PodcastDepth.STANDARD
        assert sum(config.loss_weights.values()) == pytest.approx(1.0)

    def test_loss_metrics_construction(self):
        m = _loss_metrics()
        assert m.duration_loss == 0.1
        assert m.trial_id == "trial_000"


# ============================================================
# AggregatedProfile Serialization
# ============================================================

class TestAggregatedProfile:
    def _make_profile(self):
        return AggregatedProfile(
            canonical_segment_sequence=[SegmentType.INTRO, SegmentType.BACKGROUND],
            segment_duration_targets={"intro": (5.0, 15.0), "background": (10.0, 30.0)},
            depth_targets={},
            style_variants={},
            universal_intro_patterns=["Welcome to..."],
            universal_transition_patterns=["Now let's..."],
            universal_figure_patterns=["Looking at Figure..."],
            min_coverage=0.7,
            target_words_per_minute=(130.0, 170.0),
            target_concepts_per_minute=(2.0, 5.0),
            version="1.0",
            training_pairs_used=["pair_001"],
            created_at=datetime(2026, 1, 15, 12, 0, 0),
        )

    def test_to_dict_serializes_enums(self):
        profile = self._make_profile()
        d = profile.to_dict()
        assert d["canonical_segment_sequence"] == ["intro", "background"]

    def test_to_dict_contains_all_fields(self):
        profile = self._make_profile()
        d = profile.to_dict()
        expected_keys = [
            "canonical_segment_sequence", "segment_duration_targets",
            "depth_targets", "style_variants",
            "universal_intro_patterns", "universal_transition_patterns",
            "universal_figure_patterns", "min_coverage",
            "target_words_per_minute", "target_concepts_per_minute",
            "version", "training_pairs_used", "created_at",
        ]
        for key in expected_keys:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_datetime_is_string(self):
        profile = self._make_profile()
        d = profile.to_dict()
        assert isinstance(d["created_at"], str)
        assert "2026" in d["created_at"]

    def test_to_dict_with_style_variants(self):
        profile = self._make_profile()
        profile.style_variants["host"] = StyleProfile(
            speaker_id="host",
            speaker_gender="female",
            avg_sentence_length=15.0,
            vocabulary_complexity=0.5,
            jargon_density=0.2,
            questions_per_minute=1.0,
            analogies_per_segment=0.5,
        )
        d = profile.to_dict()
        assert "host" in d["style_variants"]
        assert d["style_variants"]["host"]["speaker_gender"] == "female"


# ============================================================
# Duration Loss
# ============================================================

class TestDurationLoss:
    def test_perfect_match(self):
        loss, details = calculate_duration_loss(600.0, 600.0)
        assert loss == 0.0
        assert details["diff_seconds"] == 0.0

    def test_ten_percent_over(self):
        loss, details = calculate_duration_loss(660.0, 600.0)
        assert loss == pytest.approx(0.1)
        assert details["diff_percentage"] == pytest.approx(10.0)

    def test_fifty_percent_under(self):
        loss, details = calculate_duration_loss(300.0, 600.0)
        assert loss == pytest.approx(0.5)

    def test_zero_reference(self):
        loss, _ = calculate_duration_loss(100.0, 0.0)
        assert loss == 0.0  # Division guard

    def test_details_contain_all_keys(self):
        _, details = calculate_duration_loss(500.0, 600.0)
        assert "generated_seconds" in details
        assert "reference_seconds" in details
        assert "diff_seconds" in details
        assert "diff_percentage" in details

    def test_symmetric_for_over_and_under(self):
        loss_over, _ = calculate_duration_loss(720.0, 600.0)
        loss_under, _ = calculate_duration_loss(480.0, 600.0)
        assert loss_over == loss_under  # Both 20% off


# ============================================================
# Levenshtein Distance
# ============================================================

class TestLevenshteinDistance:
    def test_identical_sequences(self):
        seq = [SegmentType.INTRO, SegmentType.BACKGROUND, SegmentType.CONCLUSION]
        assert levenshtein_distance(seq, seq) == 0

    def test_completely_different(self):
        seq1 = [SegmentType.INTRO, SegmentType.INTRO]
        seq2 = [SegmentType.CONCLUSION, SegmentType.CONCLUSION]
        assert levenshtein_distance(seq1, seq2) == 2

    def test_empty_sequences(self):
        assert levenshtein_distance([], []) == 0

    def test_one_empty(self):
        seq = [SegmentType.INTRO, SegmentType.BACKGROUND]
        assert levenshtein_distance(seq, []) == 2
        assert levenshtein_distance([], seq) == 2

    def test_single_insertion(self):
        seq1 = [SegmentType.INTRO, SegmentType.CONCLUSION]
        seq2 = [SegmentType.INTRO, SegmentType.BACKGROUND, SegmentType.CONCLUSION]
        assert levenshtein_distance(seq1, seq2) == 1

    def test_single_deletion(self):
        seq1 = [SegmentType.INTRO, SegmentType.BACKGROUND, SegmentType.CONCLUSION]
        seq2 = [SegmentType.INTRO, SegmentType.CONCLUSION]
        assert levenshtein_distance(seq1, seq2) == 1

    def test_single_substitution(self):
        seq1 = [SegmentType.INTRO, SegmentType.BACKGROUND]
        seq2 = [SegmentType.INTRO, SegmentType.METHODOLOGY]
        assert levenshtein_distance(seq1, seq2) == 1

    def test_works_with_strings(self):
        assert levenshtein_distance(["a", "b", "c"], ["a", "x", "c"]) == 1

    def test_works_with_integers(self):
        assert levenshtein_distance([1, 2, 3], [1, 3]) == 1


# ============================================================
# ROUGE Loss
# ============================================================

class TestROUGELoss:
    def test_identical_texts(self):
        text = "The cat sat on the mat."
        loss, details = calculate_rouge_loss(text, text)
        assert loss == pytest.approx(0.0, abs=0.01)
        assert details["rouge_1"] > 0.95

    def test_completely_different(self):
        loss, details = calculate_rouge_loss(
            "Alpha beta gamma delta",
            "One two three four five six seven"
        )
        assert loss > 0.8  # Very different texts

    def test_partial_overlap(self):
        generated = "The quick brown fox jumps over the lazy dog"
        reference = "The quick brown cat sits on the lazy mat"
        loss, details = calculate_rouge_loss(generated, reference)
        assert 0.0 < loss < 1.0  # Some overlap
        assert 0.0 < details["rouge_1"] < 1.0

    def test_interpretation_good_rouge1(self):
        # Create texts with high overlap
        text1 = "Machine learning is a subset of artificial intelligence"
        text2 = "Machine learning is a branch of artificial intelligence"
        _, details = calculate_rouge_loss(text1, text2)
        assert details["interpretation"]["rouge_1"] == "Good"

    def test_all_scores_present(self):
        _, details = calculate_rouge_loss("hello world", "hello world")
        assert "rouge_1" in details
        assert "rouge_2" in details
        assert "rouge_l" in details
        assert "interpretation" in details
        assert "note" in details


# ============================================================
# Total Loss (Weighted)
# ============================================================

class TestTotalLoss:
    def test_default_weights(self):
        metrics = _loss_metrics(
            duration_loss=0.0,
            coverage_loss=0.0,
            structure_loss=0.0,
            quality_loss=0.0,
            rouge_loss=0.0,
        )
        total = calculate_total_loss(metrics)
        assert total == 0.0

    def test_all_ones(self):
        metrics = _loss_metrics(
            duration_loss=1.0,
            coverage_loss=1.0,
            structure_loss=1.0,
            quality_loss=1.0,
            rouge_loss=1.0,
        )
        total = calculate_total_loss(metrics)
        assert total == pytest.approx(1.0)

    def test_custom_weights(self):
        metrics = _loss_metrics(
            duration_loss=1.0,
            coverage_loss=0.0,
            structure_loss=0.0,
            quality_loss=0.0,
            rouge_loss=0.0,
        )
        weights = {
            "duration": 0.5,
            "coverage": 0.2,
            "structure": 0.1,
            "quality": 0.1,
            "rouge": 0.1,
        }
        total = calculate_total_loss(metrics, weights)
        assert total == pytest.approx(0.5)

    def test_only_coverage(self):
        metrics = _loss_metrics(
            duration_loss=0.0,
            coverage_loss=0.8,
            structure_loss=0.0,
            quality_loss=0.0,
            rouge_loss=0.0,
        )
        weights = {
            "duration": 0.0,
            "coverage": 1.0,
            "structure": 0.0,
            "quality": 0.0,
            "rouge": 0.0,
        }
        total = calculate_total_loss(metrics, weights)
        assert total == pytest.approx(0.8)


# ============================================================
# Structure Loss (pure computation part)
# ============================================================

class TestStructureLoss:
    @pytest.mark.asyncio
    async def test_identical_structures(self):
        gen = [SegmentType.INTRO, SegmentType.BACKGROUND, SegmentType.CONCLUSION]
        ref = [
            _aligned_segment("s1", SegmentType.INTRO),
            _aligned_segment("s2", SegmentType.BACKGROUND),
            _aligned_segment("s3", SegmentType.CONCLUSION),
        ]
        loss, details = await calculate_structure_loss(gen, ref)
        assert loss == pytest.approx(0.0)
        assert details["sequence_similarity"] == pytest.approx(1.0)
        assert details["distribution_similarity"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_completely_different(self):
        gen = [SegmentType.INTRO, SegmentType.INTRO, SegmentType.INTRO]
        ref = [
            _aligned_segment("s1", SegmentType.CONCLUSION),
            _aligned_segment("s2", SegmentType.CONCLUSION),
            _aligned_segment("s3", SegmentType.CONCLUSION),
        ]
        loss, details = await calculate_structure_loss(gen, ref)
        assert loss > 0.5  # Very different

    @pytest.mark.asyncio
    async def test_different_lengths(self):
        gen = [SegmentType.INTRO]
        ref = [
            _aligned_segment("s1", SegmentType.INTRO),
            _aligned_segment("s2", SegmentType.BACKGROUND),
            _aligned_segment("s3", SegmentType.CONCLUSION),
        ]
        loss, details = await calculate_structure_loss(gen, ref)
        assert details["generated_segment_count"] == 1
        assert details["reference_segment_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_generated(self):
        ref = [_aligned_segment("s1", SegmentType.INTRO)]
        loss, details = await calculate_structure_loss([], ref)
        assert loss > 0.0


# ============================================================
# Extract Key Concepts
# ============================================================

class TestExtractKeyConcepts:
    def test_from_themes(self):
        graph = MagicMock()
        graph.project_id = "ml-paper"
        graph.key_themes = ["neural networks", "transformers", "attention"]
        graph.unified_summary = ""
        concepts = extract_key_concepts(graph)
        assert "neural networks" in concepts
        assert "transformers" in concepts

    def test_project_id_included(self):
        graph = MagicMock()
        graph.project_id = "deep-learning"
        graph.key_themes = []
        graph.unified_summary = ""
        concepts = extract_key_concepts(graph)
        assert any("Deep Learning" in c for c in concepts)

    def test_summary_words_included_when_long(self):
        graph = MagicMock()
        graph.project_id = "test"
        graph.key_themes = []
        graph.unified_summary = " ".join(["word"] * 25)
        concepts = extract_key_concepts(graph)
        # Summary fragment should be included
        assert any("word" in c for c in concepts)

    def test_limited_to_ten(self):
        graph = MagicMock()
        graph.project_id = "test"
        graph.key_themes = [f"theme_{i}" for i in range(20)]
        graph.unified_summary = " ".join(["summary"] * 25)
        concepts = extract_key_concepts(graph)
        assert len(concepts) <= 10

    def test_empty_graph(self):
        graph = MagicMock()
        graph.project_id = ""
        graph.key_themes = []
        graph.unified_summary = ""
        concepts = extract_key_concepts(graph)
        assert len(concepts) == 0

    def test_deduplicates(self):
        graph = MagicMock()
        graph.project_id = "neural-networks"
        graph.key_themes = ["neural networks", "neural networks"]
        graph.unified_summary = ""
        concepts = extract_key_concepts(graph)
        # Should not have exact duplicates
        assert len(concepts) == len(set(concepts))


# ============================================================
# Vocabulary Complexity
# ============================================================

class TestVocabularyComplexity:
    def test_empty_text(self):
        score = calculate_vocabulary_complexity("")
        assert score == 0.5  # Default for empty

    def test_simple_text(self):
        score = calculate_vocabulary_complexity(
            "The cat sat on the mat. The dog ran to the park. "
            "It was a nice day. The sun was bright."
        )
        assert score < 0.4  # Simple text

    def test_complex_text(self):
        score = calculate_vocabulary_complexity(
            "The epistemological ramifications of quantum mechanical "
            "indeterminacy fundamentally challenge ontological realism. "
            "Phenomenological approaches to consciousness underscore "
            "the intractability of the hard problem."
        )
        assert score > 0.4  # Complex text

    def test_returns_bounded_value(self):
        for text in [
            "Simple words here.",
            "Extraordinarily complicated multisyllabic terminology.",
            "A B C D E F G",
        ]:
            score = calculate_vocabulary_complexity(text)
            assert 0.0 <= score <= 1.0

    def test_whitespace_only(self):
        score = calculate_vocabulary_complexity("   ")
        assert score == 0.5


# ============================================================
# Extract Structure Profile
# ============================================================

class TestExtractStructureProfile:
    @pytest.mark.asyncio
    async def test_basic_profile(self):
        segments = [
            _aligned_segment("s1", SegmentType.INTRO, start=0, end=30),
            _aligned_segment("s2", SegmentType.BACKGROUND, start=30, end=120),
            _aligned_segment("s3", SegmentType.KEY_FINDING, start=120, end=300),
            _aligned_segment("s4", SegmentType.CONCLUSION, start=300, end=360),
        ]
        transcription = _transcription(
            text="word " * 600,  # ~600 words
            duration=360.0,
            segments=[s.transcript_segment for s in segments],
        )

        profile = await extract_structure_profile(segments, transcription)

        assert len(profile.segment_sequence) == 4
        assert profile.total_duration == 360.0
        assert profile.words_per_minute > 0
        assert profile.concepts_per_minute >= 0

    @pytest.mark.asyncio
    async def test_segment_counts(self):
        segments = [
            _aligned_segment("s1", SegmentType.INTRO),
            _aligned_segment("s2", SegmentType.KEY_FINDING),
            _aligned_segment("s3", SegmentType.KEY_FINDING),
            _aligned_segment("s4", SegmentType.CONCLUSION),
        ]
        transcription = _transcription(duration=240.0)

        profile = await extract_structure_profile(segments, transcription)

        assert profile.segment_counts[SegmentType.KEY_FINDING.value] == 2
        assert profile.segment_counts[SegmentType.INTRO.value] == 1

    @pytest.mark.asyncio
    async def test_figure_counting(self):
        segments = [
            _aligned_segment("s1", SegmentType.FIGURE_DISCUSSION, figures=["fig1"]),
            _aligned_segment("s2", SegmentType.KEY_FINDING, figures=["fig2"]),
            _aligned_segment("s3", SegmentType.BACKGROUND),
        ]
        transcription = _transcription(duration=180.0)

        profile = await extract_structure_profile(segments, transcription)

        assert profile.figures_discussed == 2  # Two segments with figures

    @pytest.mark.asyncio
    async def test_type_percentages(self):
        segments = [
            _aligned_segment("s1", SegmentType.INTRO, start=0, end=60),
            _aligned_segment("s2", SegmentType.METHODOLOGY, start=60, end=120),
        ]
        transcription = _transcription(duration=120.0)

        profile = await extract_structure_profile(segments, transcription)

        assert profile.intro_percentage == pytest.approx(50.0)
        assert profile.methodology_percentage == pytest.approx(50.0)


# ============================================================
# Convergence Checking
# ============================================================

class TestCheckConvergence:
    def test_not_enough_trials(self):
        config = TrainingConfig(convergence_window=2)
        results = [_trial_result(avg_loss=0.5)]
        assert check_convergence(results, config) is False

    def test_converged(self):
        config = TrainingConfig(convergence_threshold=0.05, convergence_window=2)
        results = [
            _trial_result("t0", 0, avg_loss=0.50),
            _trial_result("t1", 1, avg_loss=0.48),
            _trial_result("t2", 2, avg_loss=0.479),
        ]
        # Improvement: (0.48 - mean(0.48, 0.479)) / 0.48 = very small
        assert check_convergence(results, config) is True

    def test_not_converged(self):
        config = TrainingConfig(convergence_threshold=0.05, convergence_window=2)
        results = [
            _trial_result("t0", 0, avg_loss=0.80),
            _trial_result("t1", 1, avg_loss=0.50),
            _trial_result("t2", 2, avg_loss=0.30),
        ]
        # Big improvement from 0.50 to mean(0.50, 0.30) = 0.40 → 20% improvement
        assert check_convergence(results, config) is False

    def test_exactly_at_threshold(self):
        config = TrainingConfig(convergence_threshold=0.10, convergence_window=2)
        # previous = 0.50, recent avg needs to give exactly 10% improvement
        # improvement = (0.50 - avg) / 0.50 = 0.10 → avg = 0.45
        results = [
            _trial_result("t0", 0, avg_loss=0.50),
            _trial_result("t1", 1, avg_loss=0.45),
            _trial_result("t2", 2, avg_loss=0.45),
        ]
        # improvement = (0.50 - 0.45) / 0.50 = 0.10 = threshold → not less than → False
        assert check_convergence(results, config) is False

    def test_window_size_3(self):
        config = TrainingConfig(convergence_threshold=0.05, convergence_window=3)
        # Need 4 results minimum (window + 1)
        results = [
            _trial_result("t0", 0, avg_loss=0.50),
            _trial_result("t1", 1, avg_loss=0.49),
            _trial_result("t2", 2, avg_loss=0.485),
            _trial_result("t3", 3, avg_loss=0.483),
        ]
        assert check_convergence(results, config) is True


# ============================================================
# Depth Targets
# ============================================================

class TestCalculateDepthTargets:
    def test_basic_calculation(self):
        structures = [
            StructureProfile(
                segment_sequence=[SegmentType.INTRO, SegmentType.BACKGROUND, SegmentType.CONCLUSION],
                segment_counts={"intro": 1, "background": 1, "conclusion": 1},
                total_duration=600.0,
                segment_durations={},
                avg_segment_duration=200.0,
                words_per_minute=150.0,
                concepts_per_minute=3.0,
                figures_discussed=2,
                figure_discussion_duration=60.0,
                intro_percentage=10.0,
                methodology_percentage=20.0,
                findings_percentage=40.0,
                conclusion_percentage=10.0,
            )
        ]
        pairs = [TrainingPair("p1", "/p.pdf", "/p.mp3")]

        targets = calculate_depth_targets(structures, pairs)

        assert "standard" in targets
        target = targets["standard"]
        # Duration range should be ±20% of 600
        assert target.duration_range[0] == pytest.approx(480.0)
        assert target.duration_range[1] == pytest.approx(720.0)

    def test_segment_count_range(self):
        structures = [
            StructureProfile(
                segment_sequence=[SegmentType.INTRO] * 10,
                segment_counts={"intro": 10},
                total_duration=600.0,
                segment_durations={},
                avg_segment_duration=60.0,
                words_per_minute=150.0,
                concepts_per_minute=3.0,
                figures_discussed=0,
                figure_discussion_duration=0.0,
                intro_percentage=100.0,
                methodology_percentage=0.0,
                findings_percentage=0.0,
                conclusion_percentage=0.0,
            )
        ]
        pairs = [TrainingPair("p1", "/p.pdf", "/p.mp3")]

        targets = calculate_depth_targets(structures, pairs)

        target = targets["standard"]
        # 10 segments ± 2
        assert target.segment_count_range == (8, 12)


# ============================================================
# TrainingConfig Validation
# ============================================================

class TestTrainingConfig:
    def test_default_weights_sum_to_one(self):
        config = TrainingConfig()
        assert sum(config.loss_weights.values()) == pytest.approx(1.0)

    def test_structure_disabled_by_default(self):
        config = TrainingConfig()
        assert config.loss_weights["structure"] == 0.0

    def test_custom_weights(self):
        config = TrainingConfig(loss_weights={
            "duration": 0.5,
            "coverage": 0.5,
            "structure": 0.0,
            "quality": 0.0,
            "rouge": 0.0,
        })
        assert config.loss_weights["duration"] == 0.5
