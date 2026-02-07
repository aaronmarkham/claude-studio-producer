"""Unit tests for ContentLibrary models"""

import json
import pytest
from pathlib import Path
import tempfile

from core.models.content_library import (
    AssetType,
    AssetStatus,
    AssetSource,
    AssetRecord,
    ContentLibrary,
)


class TestAssetType:
    """Test AssetType enum"""

    def test_asset_type_values(self):
        """Test that AssetType has expected values"""
        assert AssetType.AUDIO.value == "audio"
        assert AssetType.IMAGE.value == "image"
        assert AssetType.FIGURE.value == "figure"
        assert AssetType.VIDEO.value == "video"

    def test_asset_type_count(self):
        """Test that we have the expected number of types"""
        assert len(AssetType) == 4


class TestAssetStatus:
    """Test AssetStatus enum"""

    def test_asset_status_values(self):
        """Test that AssetStatus has expected values"""
        assert AssetStatus.DRAFT.value == "draft"
        assert AssetStatus.REVIEW.value == "review"
        assert AssetStatus.APPROVED.value == "approved"
        assert AssetStatus.REJECTED.value == "rejected"
        assert AssetStatus.REVISED.value == "revised"

    def test_asset_status_count(self):
        """Test that we have the expected number of statuses"""
        assert len(AssetStatus) == 5


class TestAssetSource:
    """Test AssetSource enum"""

    def test_asset_source_values(self):
        """Test that AssetSource has expected values"""
        assert AssetSource.DALLE.value == "dalle"
        assert AssetSource.ELEVENLABS.value == "elevenlabs"
        assert AssetSource.KB_EXTRACTION.value == "kb_extraction"
        assert AssetSource.LUMA.value == "luma"

    def test_asset_source_count(self):
        """Test that we have the expected number of sources"""
        assert len(AssetSource) == 9


class TestAssetRecord:
    """Test AssetRecord dataclass"""

    def test_record_creation_minimal(self):
        """Test creating a record with minimal fields"""
        record = AssetRecord(
            asset_id="aud_0001",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
        )
        assert record.asset_id == "aud_0001"
        assert record.asset_type == AssetType.AUDIO
        assert record.status == AssetStatus.DRAFT

    def test_record_creation_full(self):
        """Test creating a record with all fields"""
        record = AssetRecord(
            asset_id="img_0005",
            asset_type=AssetType.IMAGE,
            source=AssetSource.DALLE,
            status=AssetStatus.APPROVED,
            path="images/scene_005.png",
            file_size_bytes=1024000,
            format="png",
            describes="A drone flying through a warehouse",
            tags=["drone", "warehouse", "technology"],
            prompt="A professional photo of a drone...",
            segment_idx=5,
            used_in_segments=[5, 6, 7],
            origin_run_id="20260207_104648",
            generation_cost=0.04,
        )

        assert record.segment_idx == 5
        assert record.generation_cost == 0.04
        assert "drone" in record.tags

    def test_record_serialization_roundtrip(self):
        """Test that records serialize and deserialize correctly"""
        original = AssetRecord(
            asset_id="aud_0001",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.APPROVED,
            path="audio/audio_000.mp3",
            text_content="Welcome to the show",
            voice="lily",
            duration_sec=5.5,
            segment_idx=0,
        )

        data = original.to_dict()
        restored = AssetRecord.from_dict(data)

        assert restored.asset_id == original.asset_id
        assert restored.asset_type == original.asset_type
        assert restored.status == original.status
        assert restored.text_content == original.text_content
        assert restored.duration_sec == original.duration_sec


class TestContentLibrary:
    """Test ContentLibrary dataclass"""

    def test_empty_library(self):
        """Test creating an empty library"""
        lib = ContentLibrary(project_id="test_project")
        assert lib.project_id == "test_project"
        assert len(lib.assets) == 0

    def test_register_asset(self):
        """Test registering an asset"""
        lib = ContentLibrary(project_id="test_project")

        record = AssetRecord(
            asset_id="",  # Will be auto-generated
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
        )

        asset_id = lib.register(record)
        assert asset_id.startswith("aud_")
        assert asset_id in lib.assets
        assert lib.assets[asset_id].generated_at is not None

    def test_register_with_explicit_id(self):
        """Test registering with an explicit asset ID"""
        lib = ContentLibrary(project_id="test_project")

        record = AssetRecord(
            asset_id="custom_id_001",
            asset_type=AssetType.IMAGE,
            source=AssetSource.DALLE,
        )

        asset_id = lib.register(record)
        assert asset_id == "custom_id_001"

    def test_auto_id_generation(self):
        """Test that IDs are generated correctly for each type"""
        lib = ContentLibrary(project_id="test_project")

        # Register audio
        lib.register(AssetRecord(asset_id="", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))
        lib.register(AssetRecord(asset_id="", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        # Register image
        lib.register(AssetRecord(asset_id="", asset_type=AssetType.IMAGE, source=AssetSource.DALLE))

        # Register figure
        lib.register(AssetRecord(asset_id="", asset_type=AssetType.FIGURE, source=AssetSource.KB_EXTRACTION))

        assert "aud_0001" in lib.assets
        assert "aud_0002" in lib.assets
        assert "img_0001" in lib.assets
        assert "fig_0001" in lib.assets

    def test_get_asset(self):
        """Test getting an asset by ID"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test_001", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        asset = lib.get("test_001")
        assert asset is not None
        assert asset.asset_id == "test_001"

        missing = lib.get("nonexistent")
        assert missing is None

    def test_query_by_type(self):
        """Test querying assets by type"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="aud_1", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))
        lib.register(AssetRecord(asset_id="aud_2", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))
        lib.register(AssetRecord(asset_id="img_1", asset_type=AssetType.IMAGE, source=AssetSource.DALLE))

        audio_assets = lib.query(asset_type=AssetType.AUDIO)
        assert len(audio_assets) == 2

        image_assets = lib.query(asset_type=AssetType.IMAGE)
        assert len(image_assets) == 1

    def test_query_by_status(self):
        """Test querying assets by status"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="a1", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS, status=AssetStatus.DRAFT))
        lib.register(AssetRecord(asset_id="a2", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS, status=AssetStatus.APPROVED))
        lib.register(AssetRecord(asset_id="a3", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS, status=AssetStatus.APPROVED))

        approved = lib.query(status=AssetStatus.APPROVED)
        assert len(approved) == 2

    def test_query_by_segment(self):
        """Test querying assets by segment index"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(
            asset_id="a1", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS,
            segment_idx=5,
        ))
        lib.register(AssetRecord(
            asset_id="a2", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS,
            segment_idx=6, used_in_segments=[5, 6, 7],
        ))

        # Query for segment 5 - should find both (one primary, one shared)
        seg5_assets = lib.query(segment_idx=5)
        assert len(seg5_assets) == 2

    def test_query_by_figure_number(self):
        """Test querying assets by figure number"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(
            asset_id="fig_6", asset_type=AssetType.FIGURE,
            source=AssetSource.KB_EXTRACTION, figure_number=6,
        ))
        lib.register(AssetRecord(
            asset_id="fig_9", asset_type=AssetType.FIGURE,
            source=AssetSource.KB_EXTRACTION, figure_number=9,
        ))

        fig6 = lib.query(figure_number=6)
        assert len(fig6) == 1
        assert fig6[0].asset_id == "fig_6"

    def test_approve_asset(self):
        """Test approving an asset"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        result = lib.approve("test", approved_by="reviewer")
        assert result is True
        assert lib.get("test").status == AssetStatus.APPROVED
        assert lib.get("test").approved_by == "reviewer"
        assert lib.get("test").approved_at is not None

    def test_reject_asset(self):
        """Test rejecting an asset"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        result = lib.reject("test", reason="Audio quality too low")
        assert result is True
        assert lib.get("test").status == AssetStatus.REJECTED
        assert lib.get("test").rejected_reason == "Audio quality too low"

    def test_flag_for_review(self):
        """Test flagging an asset for review"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        result = lib.flag_for_review("test")
        assert result is True
        assert lib.get("test").status == AssetStatus.REVIEW

    def test_has_approved_asset_for(self):
        """Test checking for approved assets for a segment"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(
            asset_id="aud_5", asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS, segment_idx=5, status=AssetStatus.DRAFT,
        ))

        # Should be False for draft status
        assert lib.has_approved_asset_for(5, AssetType.AUDIO) is False

        # Approve it
        lib.approve("aud_5")

        # Now should be True
        assert lib.has_approved_asset_for(5, AssetType.AUDIO) is True

    def test_get_approved_for_segment(self):
        """Test getting approved asset for a segment"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(
            asset_id="aud_5", asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS, segment_idx=5, status=AssetStatus.APPROVED,
        ))

        asset = lib.get_approved_for_segment(5, AssetType.AUDIO)
        assert asset is not None
        assert asset.asset_id == "aud_5"

        # No approved image for this segment
        img = lib.get_approved_for_segment(5, AssetType.IMAGE)
        assert img is None

    def test_serialization_roundtrip(self):
        """Test full library serialization and deserialization"""
        lib = ContentLibrary(project_id="test_project", created_at="2026-02-07T10:00:00")
        lib.register(AssetRecord(
            asset_id="aud_001", asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS, status=AssetStatus.APPROVED,
            text_content="Hello world",
        ))
        lib.register(AssetRecord(
            asset_id="img_001", asset_type=AssetType.IMAGE,
            source=AssetSource.DALLE, prompt="A beautiful sunset",
        ))

        # Roundtrip via dict
        data = lib.to_dict()
        restored = ContentLibrary.from_dict(data)

        assert restored.project_id == lib.project_id
        assert len(restored.assets) == 2
        assert restored.get("aud_001").text_content == "Hello world"
        assert restored.get("img_001").prompt == "A beautiful sunset"

        # Verify counters are preserved
        assert restored._audio_counter == lib._audio_counter

    def test_json_roundtrip(self):
        """Test JSON string serialization"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        json_str = lib.to_json()
        restored = ContentLibrary.from_json(json_str)

        assert restored.project_id == lib.project_id
        assert "test" in restored.assets

    def test_file_save_and_load(self):
        """Test saving and loading from file"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="test", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "library.json"
            lib.save(path)

            assert path.exists()

            restored = ContentLibrary.load(path)
            assert restored.project_id == lib.project_id
            assert "test" in restored.assets

    def test_load_nonexistent_returns_empty(self):
        """Test that loading from nonexistent file returns empty library"""
        lib = ContentLibrary.load(Path("/nonexistent/path/library.json"))
        assert lib.project_id == "default"
        assert len(lib.assets) == 0

    def test_summary(self):
        """Test library summary"""
        lib = ContentLibrary(project_id="test_project")
        lib.register(AssetRecord(asset_id="a1", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS, status=AssetStatus.DRAFT))
        lib.register(AssetRecord(asset_id="a2", asset_type=AssetType.AUDIO, source=AssetSource.ELEVENLABS, status=AssetStatus.APPROVED))
        lib.register(AssetRecord(asset_id="i1", asset_type=AssetType.IMAGE, source=AssetSource.DALLE, status=AssetStatus.APPROVED))

        summary = lib.summary()
        assert summary["total_assets"] == 3
        assert summary["by_type"]["audio"] == 2
        assert summary["by_type"]["image"] == 1
        assert summary["by_status"]["draft"] == 1
        assert summary["by_status"]["approved"] == 2


class TestFromAssetManifestV1:
    """Test the from_asset_manifest_v1 migration method"""

    def test_migrate_simple_manifest(self):
        """Test migrating a simple v1 manifest"""
        manifest_data = {
            "run_id": "20260207_104648",
            "mode": "live",
            "total_scenes": 2,
            "animated_scenes": 0,
            "audio_clips": 0,
            "assets": [
                {
                    "scene_id": "scene_000",
                    "image_path": None,  # No file, won't be registered
                    "video_path": None,
                    "audio_path": None,
                    "display_start": 0.0,
                    "display_end": 0.0,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "asset_manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            lib = ContentLibrary.from_asset_manifest_v1(str(manifest_path))

            assert lib.project_id == "20260207_104648"
            # No assets should be registered since files don't exist
            assert len(lib.assets) == 0

    def test_migrate_manifest_with_files(self):
        """Test migrating a manifest where files exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create fake image file
            img_path = tmpdir / "scene_000.png"
            img_path.write_text("fake image")

            manifest_data = {
                "run_id": "test_run",
                "mode": "live",
                "total_scenes": 1,
                "assets": [
                    {
                        "scene_id": "scene_000",
                        "image_path": str(img_path),
                        "video_path": None,
                        "audio_path": None,
                        "display_start": 0.0,
                        "display_end": 5.0,
                    },
                ],
            }

            manifest_path = tmpdir / "asset_manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            lib = ContentLibrary.from_asset_manifest_v1(str(manifest_path))

            assert len(lib.assets) == 1

            # Check the registered asset
            img_asset = list(lib.assets.values())[0]
            assert img_asset.asset_type == AssetType.IMAGE
            assert img_asset.source == AssetSource.DALLE
            assert img_asset.status == AssetStatus.DRAFT
            assert img_asset.segment_idx == 0
            assert img_asset.origin_run_id == "test_run"

    def test_migrate_extracts_segment_index(self):
        """Test that segment index is extracted from scene_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create fake files
            (tmpdir / "scene_042.png").write_text("fake")
            (tmpdir / "audio_042.mp3").write_text("fake")

            manifest_data = {
                "run_id": "test",
                "assets": [
                    {
                        "scene_id": "scene_042",
                        "image_path": str(tmpdir / "scene_042.png"),
                        "audio_path": str(tmpdir / "audio_042.mp3"),
                        "video_path": None,
                    },
                ],
            }

            manifest_path = tmpdir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

            lib = ContentLibrary.from_asset_manifest_v1(str(manifest_path))

            # Should have both image and audio
            assert len(lib.assets) == 2

            # Both should have segment_idx = 42
            for asset in lib.assets.values():
                assert asset.segment_idx == 42

    def test_migrate_nonexistent_manifest_raises(self):
        """Test that migrating nonexistent manifest raises error"""
        with pytest.raises(FileNotFoundError):
            ContentLibrary.from_asset_manifest_v1("/nonexistent/manifest.json")
