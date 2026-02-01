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
