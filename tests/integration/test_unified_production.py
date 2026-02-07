"""Integration tests for Phase 1 & 2 unified production pipeline.

Tests the real-world data flow:
1. StructuredScript.from_script_text() on real trial data
2. ContentLibrarian registering assets from real run directories
3. build_assembly_manifest() end-to-end with real data

These tests use actual artifacts from the training and video production pipelines.
They are skipped gracefully if real data is not available.
"""

import json
import pytest
from pathlib import Path

from core.content_librarian import ContentLibrarian
from core.models.content_library import (
    AssetRecord,
    AssetSource,
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import (
    SegmentIntent,
    StructuredScript,
)


# Paths to real data artifacts
TRIAL_SCRIPT_PATH = Path(
    "artifacts/training_output/trial_000_20260206_195813/aerial-vehicle-positioning-full_script.txt"
)
VIDEO_PROD_AUDIO_DIR_20260207_101747 = Path(
    "artifacts/video_production/20260207_101747"
)
VIDEO_PROD_IMAGES_DIR_20260207_104648 = Path(
    "artifacts/video_production/20260207_104648"
)


def skip_if_data_missing():
    """Decorator to skip tests if real data is not available."""
    def decorator(test_func):
        @pytest.mark.skipif(
            not TRIAL_SCRIPT_PATH.exists(),
            reason=f"Real trial data not found at {TRIAL_SCRIPT_PATH}"
        )
        def wrapper(*args, **kwargs):
            return test_func(*args, **kwargs)
        return wrapper
    return decorator


class TestStructuredScriptFromRealData:
    """Test StructuredScript.from_script_text() on real trial data."""

    @skip_if_data_missing()
    def test_parse_real_trial_script(self):
        """Test parsing the real trial_000 script."""
        script_text = TRIAL_SCRIPT_PATH.read_text()

        # Parse it
        result = StructuredScript.from_script_text(script_text, "trial_000_20260206_195813")

        # Verify basic structure
        assert result.trial_id == "trial_000_20260206_195813"
        assert result.total_segments > 0
        assert len(result.segments) == result.total_segments
        assert result.total_estimated_duration_sec > 0

    @skip_if_data_missing()
    def test_real_script_has_segments_with_text(self):
        """Verify all segments have text content."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        result = StructuredScript.from_script_text(script_text, "trial_000")

        for seg in result.segments:
            assert seg.text, f"Segment {seg.idx} has no text"
            assert len(seg.text) > 0
            assert seg.idx >= 0

    @skip_if_data_missing()
    def test_real_script_intent_classification(self):
        """Verify intent classification on real data."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        result = StructuredScript.from_script_text(script_text, "trial_000")

        # First segment should be INTRO
        assert result.segments[0].intent == SegmentIntent.INTRO

        # Last segment should be OUTRO
        assert result.segments[-1].intent == SegmentIntent.OUTRO

        # All segments should have valid intent
        for seg in result.segments:
            assert seg.intent in SegmentIntent

    @skip_if_data_missing()
    def test_real_script_figure_detection(self):
        """Verify figure references are detected in real data."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        result = StructuredScript.from_script_text(script_text, "trial_000")

        # The trial_000 script mentions Figure 6 and Figure 9
        figure_segments = result.get_figure_segments()
        assert len(figure_segments) > 0, "Expected some segments with figure references"

        # Check figure inventory
        assert len(result.figure_inventory) > 0

        # Verify figure refs are valid
        for seg in figure_segments:
            assert seg.figure_refs, f"Segment {seg.idx} marked as figure but has no refs"
            assert seg.intent == SegmentIntent.FIGURE_WALKTHROUGH

    @skip_if_data_missing()
    def test_real_script_duration_estimation(self):
        """Verify duration estimation works on real data."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        result = StructuredScript.from_script_text(script_text, "trial_000")

        # All segments should have duration estimates
        for seg in result.segments:
            assert seg.estimated_duration_sec is not None
            assert seg.estimated_duration_sec > 0

        # Total should equal sum of segments
        total = sum(s.estimated_duration_sec or 0 for s in result.segments)
        assert abs(total - result.total_estimated_duration_sec) < 0.1

    @skip_if_data_missing()
    def test_real_script_importance_scoring(self):
        """Verify importance scores are calculated on real data."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        result = StructuredScript.from_script_text(script_text, "trial_000")

        # All segments should have importance scores
        for seg in result.segments:
            assert 0.0 <= seg.importance_score <= 1.0

        # Figure segments should have higher scores
        figure_segs = result.get_figure_segments()
        if figure_segs:
            avg_figure_score = sum(s.importance_score for s in figure_segs) / len(figure_segs)
            all_scores = [s.importance_score for s in result.segments]
            avg_all = sum(all_scores) / len(all_scores)
            assert avg_figure_score >= avg_all * 0.9, "Figure segments should have higher scores"

    @skip_if_data_missing()
    def test_real_script_serialization_roundtrip(self):
        """Verify the real script survives serialization."""
        script_text = TRIAL_SCRIPT_PATH.read_text()
        original = StructuredScript.from_script_text(script_text, "trial_000")

        # Roundtrip via JSON
        json_str = original.to_json()
        restored = StructuredScript.from_json(json_str)

        assert restored.trial_id == original.trial_id
        assert len(restored.segments) == len(original.segments)
        assert restored.total_segments == original.total_segments

        # Verify segments match
        for orig_seg, rest_seg in zip(original.segments, restored.segments):
            assert orig_seg.idx == rest_seg.idx
            assert orig_seg.text == rest_seg.text
            assert orig_seg.intent == rest_seg.intent
            assert orig_seg.figure_refs == rest_seg.figure_refs


class TestContentLibrarianRealAudioRegistration:
    """Test registering audio assets from real video production runs."""

    @pytest.fixture
    def real_script(self):
        """Load the real trial script."""
        if not TRIAL_SCRIPT_PATH.exists():
            pytest.skip(f"Real trial data not found at {TRIAL_SCRIPT_PATH}")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        return StructuredScript.from_script_text(script_text, "trial_000")

    @pytest.mark.skipif(
        not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason=f"Real audio data not found at {VIDEO_PROD_AUDIO_DIR_20260207_101747}"
    )
    def test_register_real_audio_files(self, real_script):
        """Test registering audio from real video production run."""
        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        run_dir = str(VIDEO_PROD_AUDIO_DIR_20260207_101747)
        registered = librarian.register_audio_from_run(
            run_dir,
            real_script,
            voice="lily",
            source=AssetSource.ELEVENLABS,
        )

        # Should have registered audio files
        assert len(registered) > 0, "Expected to register audio files"
        assert len(registered) == 45, f"Expected 45 audio files, got {len(registered)}"

        # Verify registered assets
        for asset_id in registered:
            asset = lib.get(asset_id)
            assert asset is not None
            assert asset.asset_type == AssetType.AUDIO
            assert asset.source == AssetSource.ELEVENLABS
            assert asset.voice == "lily"
            assert asset.segment_idx is not None
            assert asset.format == "mp3"
            assert asset.duration_sec is not None

    @pytest.mark.skipif(
        not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real audio data not found"
    )
    def test_audio_files_associated_with_segments(self, real_script):
        """Verify audio files are correctly associated with script segments."""
        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        run_dir = str(VIDEO_PROD_AUDIO_DIR_20260207_101747)
        registered = librarian.register_audio_from_run(run_dir, real_script)

        # Each registered audio should map to a segment
        for asset_id in registered:
            asset = lib.get(asset_id)
            segment = real_script.get_segment(asset.segment_idx)

            assert segment is not None, f"Audio {asset_id} maps to non-existent segment {asset.segment_idx}"
            assert asset.text_content is not None or asset.text_content == ""

    @pytest.mark.skipif(
        not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real audio data not found"
    )
    def test_audio_asset_metadata(self, real_script):
        """Verify audio asset metadata is correctly populated."""
        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        run_dir = str(VIDEO_PROD_AUDIO_DIR_20260207_101747)
        registered = librarian.register_audio_from_run(run_dir, real_script, voice="lily")

        for asset_id in registered:
            asset = lib.get(asset_id)

            # Basic metadata
            assert asset.asset_id == asset_id
            assert asset.asset_type == AssetType.AUDIO
            assert asset.status == AssetStatus.DRAFT

            # File info
            assert asset.path, "Audio should have path"
            assert asset.file_size_bytes > 0
            assert asset.format == "mp3"

            # Audio-specific
            assert asset.voice == "lily"
            assert asset.duration_sec is not None
            assert asset.describes, "Audio should have description"

            # Provenance
            assert asset.origin_run_id == "20260207_101747"
            assert asset.script_id == "trial_000_v1"


class TestContentLibrarianRealImageRegistration:
    """Test registering image assets from real video production runs."""

    @pytest.fixture
    def real_script(self):
        """Load the real trial script."""
        if not TRIAL_SCRIPT_PATH.exists():
            pytest.skip(f"Real trial data not found at {TRIAL_SCRIPT_PATH}")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        return StructuredScript.from_script_text(script_text, "trial_000")

    @pytest.mark.skipif(
        not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists(),
        reason=f"Real images data not found at {VIDEO_PROD_IMAGES_DIR_20260207_104648}"
    )
    def test_register_real_image_files(self, real_script):
        """Test registering images from real video production run."""
        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        run_dir = str(VIDEO_PROD_IMAGES_DIR_20260207_104648)
        registered = librarian.register_images_from_run(run_dir, real_script)

        # Should have registered image files
        assert len(registered) > 0, "Expected to register image files"
        assert len(registered) == 27, f"Expected 27 images, got {len(registered)}"

        # Verify registered assets
        for asset_id in registered:
            asset = lib.get(asset_id)
            assert asset is not None
            assert asset.asset_type == AssetType.IMAGE
            assert asset.source == AssetSource.DALLE
            assert asset.segment_idx is not None
            assert asset.format == "png"

    @pytest.mark.skipif(
        not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists(),
        reason="Real images data not found"
    )
    def test_image_assets_have_descriptions_when_segment_exists(self, real_script):
        """Verify image assets have descriptions when their segment exists."""
        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        run_dir = str(VIDEO_PROD_IMAGES_DIR_20260207_104648)
        registered = librarian.register_images_from_run(run_dir, real_script)

        # Check images with valid segments
        for asset_id in registered:
            asset = lib.get(asset_id)
            segment = real_script.get_segment(asset.segment_idx)
            if segment:
                # If segment exists, we should have a description
                assert asset.describes, f"Image {asset_id} for valid segment should have description"
            else:
                # If segment doesn't exist, describes will be empty (this is OK)
                pass


class TestBuildAssemblyManifestWithRealData:
    """Test end-to-end assembly manifest building with real data."""

    @pytest.fixture
    def populated_library_with_audio(self):
        """Create library with real audio assets."""
        if not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists():
            pytest.skip("Real data not found")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        script = StructuredScript.from_script_text(script_text, "trial_000")

        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        librarian.register_audio_from_run(
            str(VIDEO_PROD_AUDIO_DIR_20260207_101747),
            script,
        )

        return librarian, script

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_manifest_includes_all_audio(self, populated_library_with_audio):
        """Verify manifest includes all registered audio."""
        librarian, script = populated_library_with_audio

        manifest = librarian.build_assembly_manifest(script)

        # Verify manifest structure
        assert manifest["script_id"] == script.script_id
        assert manifest["trial_id"] == script.trial_id
        assert manifest["total_segments"] == len(script.segments)

        # Count audio entries
        audio_count = sum(1 for seg in manifest["segments"] if seg["audio"]["asset_id"])
        assert audio_count == 45, f"Expected 45 audio entries, got {audio_count}"

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_manifest_audio_paths_valid(self, populated_library_with_audio):
        """Verify audio paths in manifest point to real files."""
        librarian, script = populated_library_with_audio

        manifest = librarian.build_assembly_manifest(script)

        for seg_entry in manifest["segments"]:
            if seg_entry["audio"]["path"]:
                audio_path = Path(seg_entry["audio"]["path"])
                assert audio_path.exists(), f"Audio path doesn't exist: {audio_path}"

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_manifest_summary_accurate(self, populated_library_with_audio):
        """Verify manifest summary counts are accurate."""
        librarian, script = populated_library_with_audio

        manifest = librarian.build_assembly_manifest(script)

        summary = manifest["summary"]
        assert summary["total_audio"] == 45
        assert summary["total_images"] >= 0
        assert summary["total_figures"] >= 0

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_manifest_segments_complete(self, populated_library_with_audio):
        """Verify each segment in manifest has complete structure."""
        librarian, script = populated_library_with_audio

        manifest = librarian.build_assembly_manifest(script)

        for seg_entry in manifest["segments"]:
            # Required fields
            assert "segment_idx" in seg_entry
            assert "text_preview" in seg_entry
            assert "intent" in seg_entry
            assert "figure_refs" in seg_entry
            assert "display_mode" in seg_entry

            # Audio block
            assert "audio" in seg_entry
            assert "asset_id" in seg_entry["audio"]
            assert "path" in seg_entry["audio"]
            assert "duration_sec" in seg_entry["audio"]

            # Visual block
            assert "visual" in seg_entry
            assert "asset_id" in seg_entry["visual"]
            assert "path" in seg_entry["visual"]
            assert "type" in seg_entry["visual"]


class TestMultiRunIntegration:
    """Test integrating assets from multiple runs."""

    @pytest.fixture
    def populated_library_with_mixed_assets(self):
        """Create library with assets from different runs."""
        if not TRIAL_SCRIPT_PATH.exists() or (
            not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists() and
            not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists()
        ):
            pytest.skip("Real data not found")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        script = StructuredScript.from_script_text(script_text, "trial_000")

        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        # Register audio from one run
        if VIDEO_PROD_AUDIO_DIR_20260207_101747.exists():
            librarian.register_audio_from_run(
                str(VIDEO_PROD_AUDIO_DIR_20260207_101747),
                script,
            )

        # Register images from another run
        if VIDEO_PROD_IMAGES_DIR_20260207_104648.exists():
            librarian.register_images_from_run(
                str(VIDEO_PROD_IMAGES_DIR_20260207_104648),
                script,
            )

        return librarian, script

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or (
            not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists() and
            not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists()
        ),
        reason="Real data not found"
    )
    def test_mixed_assets_query(self, populated_library_with_mixed_assets):
        """Verify querying mixed asset types works."""
        librarian, script = populated_library_with_mixed_assets

        # Query audio
        audio_assets = librarian.library.query(asset_type=AssetType.AUDIO)
        assert len(audio_assets) > 0

        # Query images
        image_assets = librarian.library.query(asset_type=AssetType.IMAGE)
        assert len(image_assets) > 0

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or (
            not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists() and
            not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists()
        ),
        reason="Real data not found"
    )
    def test_mixed_assets_by_origin_run(self, populated_library_with_mixed_assets):
        """Verify assets can be queried by origin run."""
        librarian, script = populated_library_with_mixed_assets

        # Assets from audio run
        audio_run_assets = [
            a for a in librarian.library.assets.values()
            if a.origin_run_id == "20260207_101747"
        ]
        assert len(audio_run_assets) > 0

        # Assets from images run
        image_run_assets = [
            a for a in librarian.library.assets.values()
            if a.origin_run_id == "20260207_104648"
        ]
        assert len(image_run_assets) > 0

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or (
            not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists() and
            not VIDEO_PROD_IMAGES_DIR_20260207_104648.exists()
        ),
        reason="Real data not found"
    )
    def test_generation_plan_with_mixed_assets(self, populated_library_with_mixed_assets):
        """Verify generation planning works with mixed assets."""
        librarian, script = populated_library_with_mixed_assets

        # Get plan for images (most will need generation since library is small)
        image_plan = librarian.get_generation_plan(script, AssetType.IMAGE)
        assert isinstance(image_plan, list)

        # Get plan for audio (should be few or none since we have 45 audio files)
        audio_plan = librarian.get_generation_plan(script, AssetType.AUDIO)
        assert isinstance(audio_plan, list)


class TestApprovalWorkflow:
    """Test asset approval workflow with real data."""

    @pytest.fixture
    def librarian_with_real_assets(self):
        """Create librarian with real registered assets."""
        if not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists():
            pytest.skip("Real data not found")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        script = StructuredScript.from_script_text(script_text, "trial_000")

        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        librarian.register_audio_from_run(
            str(VIDEO_PROD_AUDIO_DIR_20260207_101747),
            script,
        )

        return librarian

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_approve_real_assets(self, librarian_with_real_assets):
        """Test approving real assets."""
        librarian = librarian_with_real_assets

        # Get first few assets
        assets_to_approve = list(librarian.library.assets.values())[:5]

        for asset in assets_to_approve:
            result = librarian.library.approve(asset.asset_id, approved_by="test_user")
            assert result is True

            # Verify approval
            updated = librarian.library.get(asset.asset_id)
            assert updated.status == AssetStatus.APPROVED
            assert updated.approved_by == "test_user"
            assert updated.approved_at is not None

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_generation_plan_excludes_approved(self, librarian_with_real_assets):
        """Verify generation plan excludes approved assets."""
        librarian = librarian_with_real_assets
        script_text = TRIAL_SCRIPT_PATH.read_text()
        script = StructuredScript.from_script_text(script_text, "trial_000")

        # Initially all need generation
        initial_plan = librarian.get_generation_plan(script, AssetType.AUDIO)
        initial_count = len(initial_plan)

        # Approve some
        for asset in list(librarian.library.assets.values())[:3]:
            librarian.library.approve(asset.asset_id)

        # Plan should shrink
        updated_plan = librarian.get_generation_plan(script, AssetType.AUDIO)
        assert len(updated_plan) < initial_count


class TestLibrarySerialization:
    """Test library serialization with real data."""

    @pytest.fixture
    def librarian_with_real_assets(self):
        """Create librarian with real registered assets."""
        if not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists():
            pytest.skip("Real data not found")

        script_text = TRIAL_SCRIPT_PATH.read_text()
        script = StructuredScript.from_script_text(script_text, "trial_000")

        lib = ContentLibrary(project_id="test_project")
        librarian = ContentLibrarian(lib)

        librarian.register_audio_from_run(
            str(VIDEO_PROD_AUDIO_DIR_20260207_101747),
            script,
        )

        return librarian

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_save_and_load_library_with_real_assets(self, librarian_with_real_assets, tmp_path):
        """Test that library with real assets survives serialization."""
        librarian = librarian_with_real_assets
        original_count = len(librarian.library.assets)

        # Save
        lib_path = tmp_path / "library.json"
        librarian.save(lib_path)

        assert lib_path.exists()

        # Load
        loaded_lib = ContentLibrary.load(lib_path)

        # Verify
        assert len(loaded_lib.assets) == original_count
        assert loaded_lib.project_id == librarian.library.project_id

    @pytest.mark.skipif(
        not TRIAL_SCRIPT_PATH.exists() or not VIDEO_PROD_AUDIO_DIR_20260207_101747.exists(),
        reason="Real data not found"
    )
    def test_library_summary_with_real_assets(self, librarian_with_real_assets):
        """Test library summary with real data."""
        librarian = librarian_with_real_assets

        summary = librarian.library.summary()

        assert summary["project_id"] == "test_project"
        assert summary["total_assets"] == 45
        assert summary["by_type"]["audio"] == 45
        assert summary["by_status"]["draft"] == 45
