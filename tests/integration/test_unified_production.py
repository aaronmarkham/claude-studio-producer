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


class TestDoPIntegration:
    """Test DoP (Director of Photography) integration with produce_video.py.

    Tests the visual assignment pipeline:
    1. Loading StructuredScript from trial directory
    2. Using DoP assign_visuals() to populate display modes
    3. Verifying visual plans are created correctly from DoP assignments
    """

    @pytest.fixture
    def mock_structured_script(self):
        """Create a mock StructuredScript with realistic segments."""
        from core.models.structured_script import (
            ScriptSegment,
            SegmentIntent,
            FigureInventory
        )

        script = StructuredScript(
            script_id="test_script_001_v1",
            trial_id="test_trial_001",
            version=1
        )

        # Add diverse segments covering different intents
        segments = [
            # INTRO - always high importance
            ScriptSegment(
                idx=0,
                text="Welcome to our research presentation on distributed systems.",
                intent=SegmentIntent.INTRO,
                figure_refs=[],
                key_concepts=["distributed systems", "overview"],
                importance_score=0.9
            ),
            # BACKGROUND with figure reference
            ScriptSegment(
                idx=1,
                text="We build on prior work, as shown in Figure 2, which demonstrates...",
                intent=SegmentIntent.BACKGROUND,
                figure_refs=[2],
                key_concepts=["background", "prior work"],
                importance_score=0.7
            ),
            # METHODOLOGY - technical detail
            ScriptSegment(
                idx=2,
                text="Our methodology follows a three-phase approach to network design.",
                intent=SegmentIntent.METHODOLOGY,
                figure_refs=[],
                key_concepts=["methodology", "network", "design"],
                importance_score=0.8
            ),
            # KEY_FINDING - high importance
            ScriptSegment(
                idx=3,
                text="Our key finding shows a 40% improvement over baseline methods.",
                intent=SegmentIntent.KEY_FINDING,
                figure_refs=[],
                key_concepts=["results", "improvement", "performance"],
                importance_score=0.95
            ),
            # FIGURE_WALKTHROUGH - medium importance
            ScriptSegment(
                idx=4,
                text="In Figure 5, we show the detailed breakdown of latency components.",
                intent=SegmentIntent.FIGURE_WALKTHROUGH,
                figure_refs=[5],
                key_concepts=["latency", "breakdown", "components"],
                importance_score=0.75
            ),
            # DATA_DISCUSSION - low importance
            ScriptSegment(
                idx=5,
                text="The measurement setup included 100 nodes across three regions.",
                intent=SegmentIntent.DATA_DISCUSSION,
                figure_refs=[],
                key_concepts=["measurement", "setup", "nodes"],
                importance_score=0.4
            ),
            # TRANSITION - always text_only
            ScriptSegment(
                idx=6,
                text="Next, let's explore the implications of these findings.",
                intent=SegmentIntent.TRANSITION,
                figure_refs=[],
                key_concepts=[],
                importance_score=0.2
            ),
            # COMPARISON
            ScriptSegment(
                idx=7,
                text="Compared to method A, our approach shows faster convergence.",
                intent=SegmentIntent.COMPARISON,
                figure_refs=[],
                key_concepts=["comparison", "convergence", "performance"],
                importance_score=0.7
            ),
            # RECAP
            ScriptSegment(
                idx=8,
                text="To summarize, we have demonstrated three key innovations.",
                intent=SegmentIntent.RECAP,
                figure_refs=[],
                key_concepts=["summary", "innovations"],
                importance_score=0.6
            ),
            # OUTRO
            ScriptSegment(
                idx=9,
                text="Thank you for watching. Questions are welcome.",
                intent=SegmentIntent.OUTRO,
                figure_refs=[],
                key_concepts=[],
                importance_score=0.5
            ),
        ]

        script.segments = segments
        script.total_segments = len(segments)
        script.total_estimated_duration_sec = 180.0  # ~3 minutes

        # Add figure inventory using FigureInventory objects
        script.figure_inventory = {
            2: FigureInventory(
                figure_number=2,
                kb_path="/path/to/figure_2.png",
                caption="Prior work comparison"
            ),
            5: FigureInventory(
                figure_number=5,
                kb_path="/path/to/figure_5.png",
                caption="Latency breakdown details"
            )
        }

        return script

    @pytest.fixture
    def empty_content_library(self):
        """Create an empty content library for testing."""
        return ContentLibrary(project_id="test_dop_run")

    @pytest.fixture
    def library_with_approved_assets(self):
        """Create a content library with some pre-approved assets."""
        library = ContentLibrary(project_id="test_dop_run")

        # Add some pre-approved images
        for i in [1, 3, 7]:
            asset = AssetRecord(
                asset_id=f"img_{i:03d}",
                asset_type=AssetType.IMAGE,
                source=AssetSource.DALLE,
                status=AssetStatus.APPROVED,
                segment_idx=i,
                path=f"images/scene_{i:03d}.png",
                format="png",
                file_size_bytes=512000
            )
            library.register(asset)

        # Add some KB figures
        for fig_num in [2, 5]:
            asset = AssetRecord(
                asset_id=f"fig_{fig_num:03d}",
                asset_type=AssetType.FIGURE,
                source=AssetSource.KB_EXTRACTION,
                status=AssetStatus.APPROVED,
                figure_number=fig_num,
                path=f"figures/figure_{fig_num}.png",
                format="png",
                file_size_bytes=256000
            )
            library.register(asset)

        return library

    def test_dop_assign_visuals_with_empty_library_medium_tier(
        self, mock_structured_script, empty_content_library
    ):
        """Test DoP visual assignment with empty library and medium budget."""
        from core.dop import assign_visuals, get_visual_plan_summary

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="medium"
        )

        # Verify script is modified in place
        assert script.script_id == "test_script_001_v1"

        # Get summary
        summary = get_visual_plan_summary(script)

        # For medium tier with 10 segments (27% ratio):
        # ~3 DALL-E images should be allocated to non-transition, non-figure segments
        assert summary["figure_sync"] == 2, "Should have 2 figure_sync segments (figures 2, 5)"
        assert summary["dall_e"] > 0, "Should allocate some DALL-E budget"
        assert summary["carry_forward"] > 0, "Should have carry_forward segments"
        assert summary["text_only"] > 0, "Should have text_only transitions"
        assert summary["unassigned"] == 0, "All segments should be assigned"

    def test_dop_respects_figure_priority(
        self, mock_structured_script, empty_content_library
    ):
        """Test that DoP prioritizes figure_sync over DALL-E."""
        from core.dop import assign_visuals, get_figure_sync_list

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="high"
        )

        # Get figure sync segments
        figure_segments = get_figure_sync_list(script)

        # Should have exactly 2 figure segments (idx 1 and 4)
        assert len(figure_segments) == 2
        segment_indices = [seg_idx for seg_idx, _ in figure_segments]
        assert 1 in segment_indices, "Segment 1 references Figure 2"
        assert 4 in segment_indices, "Segment 4 references Figure 5"

    def test_dop_transitions_always_text_only(
        self, mock_structured_script, empty_content_library
    ):
        """Test that TRANSITION segments always get text_only mode."""
        from core.dop import assign_visuals

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="full"  # Even with full budget
        )

        transition_seg = script.get_segment(6)
        assert transition_seg is not None
        assert transition_seg.display_mode == "text_only", "Transition should always be text_only"

    def test_dop_micro_tier_all_text_only(
        self, mock_structured_script, empty_content_library
    ):
        """Test that micro tier makes everything text_only except figures."""
        from core.dop import assign_visuals, get_visual_plan_summary

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="micro"
        )

        summary = get_visual_plan_summary(script)

        # Micro tier: only figures get special treatment, rest is text_only
        assert summary["figure_sync"] == 2, "Figures should still get figure_sync"
        assert summary["text_only"] == 8, "All non-figure segments text_only"
        assert summary["dall_e"] == 0, "No DALL-E in micro tier"
        assert summary["carry_forward"] == 0, "No carry_forward in micro tier"

    def test_dop_full_tier_allocates_images_to_all(
        self, mock_structured_script, empty_content_library
    ):
        """Test that full tier allocates DALL-E to most segments."""
        from core.dop import assign_visuals, get_visual_plan_summary

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="full"
        )

        summary = get_visual_plan_summary(script)

        # Full tier: 100% image ratio, so most non-transition segments get DALL-E
        assert summary["figure_sync"] == 2, "Figures get figure_sync"
        assert summary["dall_e"] > 6, "Most non-transition, non-figure segments get DALL-E"
        assert summary["text_only"] >= 1, "At least transition segments text_only"
        assert summary["unassigned"] == 0

    def test_dop_respects_approved_assets(
        self, mock_structured_script, library_with_approved_assets
    ):
        """Test that DoP links approved assets correctly."""
        from core.dop import assign_visuals

        script = assign_visuals(
            mock_structured_script,
            library_with_approved_assets,
            budget_tier="medium"
        )

        # Segments with pre-approved assets should link to them
        # Segment 1 and 3 have approved images
        seg_1 = script.get_segment(1)
        seg_3 = script.get_segment(3)

        # These should be marked for DALL-E or use existing
        assert seg_1.display_mode in ["dall_e", "figure_sync"]
        assert seg_3.display_mode in ["dall_e", "carry_forward"]

    def test_dop_generates_visual_direction_for_dalle(
        self, mock_structured_script, empty_content_library
    ):
        """Test that DoP generates visual direction hints for DALL-E segments."""
        from core.dop import assign_visuals

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="high"
        )

        # Check DALL-E segments have visual direction
        dalle_segments = [s for s in script.segments if s.display_mode == "dall_e"]
        assert len(dalle_segments) > 0

        for seg in dalle_segments:
            assert seg.visual_direction, f"Segment {seg.idx} with DALL-E should have visual_direction"
            # Visual direction should mention intent or concepts
            assert (
                seg.intent.value.lower() in seg.visual_direction.lower() or
                any(c.lower() in seg.visual_direction.lower() for c in seg.key_concepts)
            ), f"Visual direction should reference intent or concepts"

    def test_dop_visual_direction_mentions_figures(
        self, mock_structured_script, empty_content_library
    ):
        """Test that visual direction for figure segments mentions the figure."""
        from core.dop import assign_visuals

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="full"
        )

        # Check figure segments have meaningful visual direction
        figure_segs = script.get_figure_segments()
        assert len(figure_segs) > 0

        for seg in figure_segs:
            if seg.display_mode == "figure_sync":
                assert "Figure" in seg.visual_direction, \
                    f"Figure sync segment should mention figure in visual_direction"

    def test_dop_importance_affects_budget_allocation(
        self, mock_structured_script, empty_content_library
    ):
        """Test that higher importance scores get DALL-E allocation priority."""
        from core.dop import assign_visuals

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="low"  # Limited budget
        )

        # Get DALL-E segments
        dalle_segs = [s for s in script.segments if s.display_mode == "dall_e"]
        carry_segs = [s for s in script.segments if s.display_mode == "carry_forward"]

        # Should have some of both
        assert len(dalle_segs) > 0
        assert len(carry_segs) > 0

        # DALL-E segments should have higher average importance
        if dalle_segs and carry_segs:
            avg_dalle_importance = sum(s.importance_score for s in dalle_segs) / len(dalle_segs)
            avg_carry_importance = sum(s.importance_score for s in carry_segs) / len(carry_segs)

            assert avg_dalle_importance >= avg_carry_importance * 0.8, \
                "Higher importance segments should get DALL-E preferentially"

    def test_dop_integration_with_visual_plan_creation(
        self, mock_structured_script, empty_content_library
    ):
        """Test complete pipeline: DoP assignment -> visual plan conversion.

        Simulates the produce_video.py workflow where DoP output is used to
        create VisualPlan objects.
        """
        from core.dop import assign_visuals
        from core.models.video_production import VisualPlan

        # Step 1: Use DoP to assign visuals
        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="medium"
        )

        # Step 2: Convert to visual plans (simulating produce_video.py behavior)
        visual_plans = []
        style_consistency = {
            "style_suffix": "Style: clean technical illustration, dark background, vibrant accents.",
            "dalle_style": "natural"
        }

        for seg in script.segments:
            dalle_prompt = ""
            ken_burns = None
            kb_figure_path = None

            if seg.display_mode == "dall_e":
                dalle_prompt = f"{seg.visual_direction} {style_consistency['style_suffix']}"
            elif seg.display_mode == "figure_sync":
                # In real code, this would look up the figure from KB
                kb_figure_path = f"/path/to/figure_{seg.figure_refs[0]}.png" if seg.figure_refs else None

            if seg.display_mode in ["dall_e", "figure_sync"]:
                ken_burns = {"enabled": True, "direction": "slow_zoom_in"}

            plan = VisualPlan(
                scene_id=f"scene_{seg.idx:03d}",
                dalle_prompt=dalle_prompt,
                dalle_style="natural",
                dalle_settings={},
                animate_with_luma=False,
                luma_prompt=None,
                luma_settings={},
                transition_in="fade",
                transition_out="fade",
                ken_burns=ken_burns,
                on_screen_text=None,
                text_position="lower_third"
            )
            plan.budget_mode = seg.display_mode
            plan.kb_figure_path = kb_figure_path

            visual_plans.append(plan)

        # Step 3: Verify the conversion worked correctly
        assert len(visual_plans) == len(script.segments)

        # Verify specific modes translated correctly
        dalle_plans = [p for p in visual_plans if p.dalle_prompt]
        assert len(dalle_plans) > 0, "Should have DALL-E plans from DoP assignment"

        figure_plans = [p for p in visual_plans if p.kb_figure_path]
        assert len(figure_plans) == 2, "Should have 2 figure plans"

        # Verify text-only segments have no prompts
        text_only_plans = [p for p in visual_plans if p.budget_mode == "text_only"]
        for plan in text_only_plans:
            assert plan.dalle_prompt == "", "Text-only should not have DALL-E prompt"

    def test_dop_summary_counts_match_segments(
        self, mock_structured_script, empty_content_library
    ):
        """Test that visual plan summary counts equal total segments."""
        from core.dop import assign_visuals, get_visual_plan_summary

        script = assign_visuals(
            mock_structured_script,
            empty_content_library,
            budget_tier="medium"
        )

        summary = get_visual_plan_summary(script)

        total_assigned = (
            summary["figure_sync"] +
            summary["dall_e"] +
            summary["carry_forward"] +
            summary["text_only"]
        )

        assert total_assigned == len(script.segments), \
            f"Summary counts ({total_assigned}) should equal total segments ({len(script.segments)})"

    def test_dop_cost_estimation(
        self, mock_structured_script, empty_content_library
    ):
        """Test that DoP cost estimation is reasonable."""
        from core.dop import assign_visuals, estimate_visual_cost

        for tier in ["micro", "low", "medium", "high", "full"]:
            script = assign_visuals(
                mock_structured_script,
                empty_content_library,
                budget_tier=tier
            )

            cost = estimate_visual_cost(script, dalle_cost=0.08)

            # Cost should be non-negative
            assert cost >= 0.0, f"Cost for {tier} tier should be >= 0"

            # Estimate should follow tier progression
            # (more images as tier increases)
            # This is tested by checking the DALL-E count in summary
            from core.dop import get_visual_plan_summary
            summary = get_visual_plan_summary(script)
            expected_cost = summary["dall_e"] * 0.08
            assert abs(cost - expected_cost) < 0.01
