"""Unit tests for training pipeline"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import json

from core.training.transcription import compress_audio_if_needed
from core.training.synthesis import store_profile_in_memory
from core.training.models import AggregatedProfile
from cli.training import save_checkpoint, load_checkpoint


class TestCheckpointing:
    """Test checkpoint save/load functionality"""

    def test_save_and_load_checkpoint(self, tmp_path):
        """Test that checkpoints can be saved and loaded"""
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        test_data = {
            "test_key": "test_value",
            "test_number": 42
        }

        # Save checkpoint
        save_checkpoint(checkpoint_dir, "test_pair", "test_type", test_data)

        # Load checkpoint
        loaded = load_checkpoint(checkpoint_dir, "test_pair", "test_type")

        assert loaded == test_data

    def test_load_nonexistent_checkpoint(self, tmp_path):
        """Test loading a checkpoint that doesn't exist"""
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        loaded = load_checkpoint(checkpoint_dir, "nonexistent", "test_type")

        assert loaded is None

    def test_transcription_checkpoint_with_metrics(self, tmp_path):
        """Test that transcription checkpoints include quality metrics"""
        checkpoint_dir = tmp_path / "checkpoints"
        checkpoint_dir.mkdir()

        transcription_data = {
            "source_path": "/path/to/audio.mp3",
            "transcript_text": "This is a test transcript with several words.",
            "word_timestamps": [],
            "segments": [],
            "total_duration": 10.0,
            "speaker_id": "test_speaker",
            "confidence": 0.95,
            "language": "en",
            # Quality metrics
            "word_count": 8,
            "words_per_minute": 48.0,
            "timestamp_count": 8,
            "segment_coverage_percentage": 95.0,
            "num_segments": 2,
        }

        # Save checkpoint
        save_checkpoint(checkpoint_dir, "test_pair", "transcription", transcription_data)

        # Load checkpoint
        loaded = load_checkpoint(checkpoint_dir, "test_pair", "transcription")

        # Verify all fields including metrics
        assert loaded["source_path"] == transcription_data["source_path"]
        assert loaded["word_count"] == 8
        assert loaded["words_per_minute"] == 48.0
        assert loaded["timestamp_count"] == 8
        assert loaded["segment_coverage_percentage"] == 95.0
        assert loaded["num_segments"] == 2


class TestTranscription:
    """Test audio transcription utilities"""

    @pytest.mark.asyncio
    async def test_compress_audio_if_needed_small_file(self, tmp_path):
        """Test that small files are not compressed"""
        # Create a small dummy file
        audio_file = tmp_path / "small.mp3"
        audio_file.write_bytes(b"small file" * 100)  # ~1KB

        result_path, needs_chunking = await compress_audio_if_needed(str(audio_file))

        # Small file should not be compressed
        assert result_path == str(audio_file)
        assert needs_chunking is False


class TestProfileStorage:
    """Test profile storage functionality"""

    @pytest.mark.asyncio
    async def test_store_profile_creates_file(self, tmp_path):
        """Test that profile storage creates a JSON file"""
        from datetime import datetime

        # Create a mock profile
        profile = Mock(spec=AggregatedProfile)
        profile.version = "v1"
        profile.training_pairs_used = ["pair1", "pair2"]
        profile.created_at = datetime.now()
        profile.to_dict = Mock(return_value={"test": "data"})

        # Create mock memory manager
        memory_manager = Mock()

        # Store profile
        await store_profile_in_memory(profile, memory_manager, tmp_path)

        # Check file was created
        profile_file = tmp_path / "aggregated_profile.json"
        assert profile_file.exists()

        # Check content
        data = json.loads(profile_file.read_text())
        assert data["version"] == "v1"
        assert "pair1" in data["training_pairs_used"]
        assert data["profile"] == {"test": "data"}


class TestTrainingPipelineImports:
    """Test that all training modules can be imported"""

    def test_import_training_module(self):
        """Test that training module imports successfully"""
        from core.training import (
            TranscriptionResult,
            TrainingPair,
            TrainingConfig,
            PodcastDepth,
        )

        assert TranscriptionResult is not None
        assert TrainingPair is not None
        assert TrainingConfig is not None
        assert PodcastDepth is not None

    def test_import_training_functions(self):
        """Test that training functions import successfully"""
        from core.training import (
            transcribe_podcast,
            classify_segments,
            synthesize_profiles,
        )

        assert callable(transcribe_podcast)
        assert callable(classify_segments)
        assert callable(synthesize_profiles)


class TestPhase3Checkpointing:
    """Test Phase 3 analysis checkpoint serialization"""

    def test_serialize_deserialize_aligned_segment(self):
        """Test AlignedSegment serialization round-trip"""
        from core.training.models import AlignedSegment, TranscriptSegment, SegmentType
        from cli.training import serialize_aligned_segment, deserialize_aligned_segment

        # Create a test AlignedSegment
        transcript_seg = TranscriptSegment(
            segment_id="seg_001",
            text="This is a test segment about quantum computing.",
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            segment_type=SegmentType.INTRO,
            linked_atoms=["atom_1", "atom_2"]
        )

        aligned_seg = AlignedSegment(
            segment_id="seg_001",
            transcript_segment=transcript_seg,
            primary_atoms=["atom_1"],
            referenced_figures=["fig_1"],
            segment_type=SegmentType.INTRO,
            key_concepts=["quantum", "computing"],
            technical_terms=["qubit"],
            analogies_used=["like a coin flip"],
            questions_asked=["What is quantum computing?"],
            words_per_minute=120.0,
            density_score=0.4,
        )

        # Serialize
        serialized = serialize_aligned_segment(aligned_seg)

        # Deserialize
        reconstructed = deserialize_aligned_segment(serialized)

        # Verify fields match
        assert reconstructed.segment_id == aligned_seg.segment_id
        assert reconstructed.segment_type == aligned_seg.segment_type
        assert reconstructed.key_concepts == aligned_seg.key_concepts
        assert reconstructed.technical_terms == aligned_seg.technical_terms
        assert reconstructed.analogies_used == aligned_seg.analogies_used
        assert reconstructed.questions_asked == aligned_seg.questions_asked
        assert reconstructed.words_per_minute == aligned_seg.words_per_minute
        assert reconstructed.density_score == aligned_seg.density_score

        # Verify nested TranscriptSegment
        assert reconstructed.transcript_segment.segment_id == transcript_seg.segment_id
        assert reconstructed.transcript_segment.text == transcript_seg.text
        assert reconstructed.transcript_segment.start_time == transcript_seg.start_time
        assert reconstructed.transcript_segment.end_time == transcript_seg.end_time
        assert reconstructed.transcript_segment.duration == transcript_seg.duration
        assert reconstructed.transcript_segment.segment_type == transcript_seg.segment_type

    def test_serialize_deserialize_structure_profile(self):
        """Test StructureProfile serialization round-trip"""
        from core.training.models import StructureProfile, SegmentType
        from cli.training import serialize_structure_profile, deserialize_structure_profile

        # Create a test StructureProfile
        profile = StructureProfile(
            segment_sequence=[SegmentType.INTRO, SegmentType.METHODOLOGY],
            segment_counts={"intro": 1, "methodology": 1},
            total_duration=300.0,
            segment_durations={"intro": [60.0], "methodology": [240.0]},
            avg_segment_duration=150.0,
            words_per_minute=140.0,
            concepts_per_minute=2.5,
            figures_discussed=2,
            figure_discussion_duration=120.0,
            intro_percentage=20.0,
            methodology_percentage=80.0,
            findings_percentage=0.0,
            conclusion_percentage=0.0,
            transition_phrases=["Now turning to", "Let's examine"],
        )

        # Serialize
        serialized = serialize_structure_profile(profile)

        # Deserialize
        reconstructed = deserialize_structure_profile(serialized)

        # Verify fields match
        assert reconstructed.segment_sequence == profile.segment_sequence
        assert reconstructed.segment_counts == profile.segment_counts
        assert reconstructed.total_duration == profile.total_duration
        assert reconstructed.segment_durations == profile.segment_durations
        assert reconstructed.avg_segment_duration == profile.avg_segment_duration
        assert reconstructed.words_per_minute == profile.words_per_minute
        assert reconstructed.concepts_per_minute == profile.concepts_per_minute
        assert reconstructed.figures_discussed == profile.figures_discussed
        assert reconstructed.transition_phrases == profile.transition_phrases

    def test_serialize_deserialize_style_profile(self):
        """Test StyleProfile serialization round-trip"""
        from core.training.models import StyleProfile
        from cli.training import serialize_style_profile, deserialize_style_profile

        # Create a test StyleProfile
        profile = StyleProfile(
            speaker_id="test_speaker",
            speaker_gender="female",
            avg_sentence_length=18.5,
            vocabulary_complexity=0.7,
            jargon_density=0.3,
            questions_per_minute=0.5,
            analogies_per_segment=1.2,
            enthusiasm_markers=["fascinating", "remarkable"],
            definition_style="inline",
            example_frequency=1.5,
            intro_phrases=["Today we're looking at", "This paper examines"],
            transition_phrases=["Now turning to", "Let's move on"],
            emphasis_phrases=["This is crucial", "The key finding is"],
            conclusion_phrases=["To summarize", "In conclusion"],
            figure_intro_pattern="Let's look at Figure {n}",
            figure_explanation_depth="detailed",
        )

        # Serialize
        serialized = serialize_style_profile(profile)

        # Deserialize
        reconstructed = deserialize_style_profile(serialized)

        # Verify fields match
        assert reconstructed.speaker_id == profile.speaker_id
        assert reconstructed.speaker_gender == profile.speaker_gender
        assert reconstructed.avg_sentence_length == profile.avg_sentence_length
        assert reconstructed.vocabulary_complexity == profile.vocabulary_complexity
        assert reconstructed.jargon_density == profile.jargon_density
        assert reconstructed.enthusiasm_markers == profile.enthusiasm_markers
        assert reconstructed.intro_phrases == profile.intro_phrases
        assert reconstructed.figure_intro_pattern == profile.figure_intro_pattern
        assert reconstructed.figure_explanation_depth == profile.figure_explanation_depth
