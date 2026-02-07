"""Unit tests for ContentLibrarian"""

import json
import pytest
from pathlib import Path
import tempfile

from core.content_librarian import ContentLibrarian
from core.models.content_library import (
    AssetRecord,
    AssetSource,
    AssetStatus,
    AssetType,
    ContentLibrary,
)
from core.models.structured_script import (
    FigureInventory,
    ScriptSegment,
    SegmentIntent,
    StructuredScript,
)


@pytest.fixture
def empty_library():
    """Create an empty content library."""
    return ContentLibrary(project_id="test_project")


@pytest.fixture
def empty_librarian(empty_library):
    """Create a librarian with empty library."""
    return ContentLibrarian(empty_library)


@pytest.fixture
def sample_script():
    """Create a sample structured script."""
    segments = [
        ScriptSegment(idx=0, text="Welcome to the show.", intent=SegmentIntent.INTRO),
        ScriptSegment(idx=1, text="Let me explain the background.", intent=SegmentIntent.BACKGROUND),
        ScriptSegment(idx=2, text="Figure 6 shows the results.", intent=SegmentIntent.FIGURE_WALKTHROUGH, figure_refs=[6]),
        ScriptSegment(idx=3, text="The methodology uses filtering.", intent=SegmentIntent.METHODOLOGY, importance_score=0.7),
        ScriptSegment(idx=4, text="Thanks for listening.", intent=SegmentIntent.OUTRO),
    ]
    figure_inventory = {
        6: FigureInventory(
            figure_number=6,
            kb_path="figures/fig_005.png",
            caption="Results comparison",
            discussed_in_segments=[2],
        )
    }
    return StructuredScript(
        script_id="test_script_v1",
        trial_id="test_trial",
        segments=segments,
        figure_inventory=figure_inventory,
        total_segments=5,
    )


class TestContentLibrarianCreation:
    """Test ContentLibrarian creation and loading."""

    def test_create_with_empty_library(self, empty_library):
        """Test creating librarian with empty library."""
        librarian = ContentLibrarian(empty_library)
        assert librarian.library.project_id == "test_project"

    def test_load_or_create_new(self):
        """Test load_or_create creates new library when none exists."""
        librarian = ContentLibrarian.load_or_create("new_project")
        assert librarian.library.project_id == "new_project"

    def test_load_or_create_existing(self):
        """Test load_or_create loads existing library."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_path = Path(tmpdir) / "library.json"

            # Create and save a library
            lib = ContentLibrary(project_id="existing_project")
            lib.register(AssetRecord(
                asset_id="test_asset",
                asset_type=AssetType.AUDIO,
                source=AssetSource.ELEVENLABS,
            ))
            lib.save(lib_path)

            # Load it
            librarian = ContentLibrarian.load_or_create("ignored", lib_path)
            assert librarian.library.project_id == "existing_project"
            assert "test_asset" in librarian.library.assets


class TestRegisterAudioFromRun:
    """Test registering audio from a production run."""

    def test_register_audio_files(self, empty_librarian, sample_script):
        """Test registering audio files from a run directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            audio_dir = run_dir / "audio"
            audio_dir.mkdir()

            # Create fake audio files
            (audio_dir / "audio_000.mp3").write_text("fake audio 0")
            (audio_dir / "audio_001.mp3").write_text("fake audio 1")
            (audio_dir / "audio_002.mp3").write_text("fake audio 2")

            registered = empty_librarian.register_audio_from_run(
                str(run_dir),
                sample_script,
                voice="lily",
            )

            assert len(registered) == 3

            # Check registered assets
            for asset_id in registered:
                asset = empty_librarian.library.get(asset_id)
                assert asset.asset_type == AssetType.AUDIO
                assert asset.source == AssetSource.ELEVENLABS
                assert asset.voice == "lily"
                assert asset.segment_idx in [0, 1, 2]

    def test_register_audio_empty_dir(self, empty_librarian, sample_script):
        """Test registering from directory with no audio."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registered = empty_librarian.register_audio_from_run(
                str(tmpdir),
                sample_script,
            )
            assert len(registered) == 0

    def test_register_audio_nonexistent_dir(self, empty_librarian, sample_script):
        """Test registering from nonexistent directory."""
        registered = empty_librarian.register_audio_from_run(
            "/nonexistent/path",
            sample_script,
        )
        assert len(registered) == 0


class TestRegisterImagesFromRun:
    """Test registering images from a production run."""

    def test_register_image_files(self, empty_librarian, sample_script):
        """Test registering image files from a run directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            images_dir = run_dir / "images"
            images_dir.mkdir()

            # Create fake image files
            (images_dir / "scene_000.png").write_text("fake image 0")
            (images_dir / "scene_003.png").write_text("fake image 3")

            registered = empty_librarian.register_images_from_run(
                str(run_dir),
                sample_script,
            )

            assert len(registered) == 2

            # Check registered assets
            for asset_id in registered:
                asset = empty_librarian.library.get(asset_id)
                assert asset.asset_type == AssetType.IMAGE
                assert asset.source == AssetSource.DALLE


class TestRegisterKBFigures:
    """Test registering KB figures."""

    def test_register_kb_figures(self, empty_librarian, sample_script):
        """Test registering KB figures referenced in script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb_dir = Path(tmpdir)
            figures_dir = kb_dir / "figures"
            figures_dir.mkdir()

            # Create fake figure file (Figure 6 = fig_005.png)
            (figures_dir / "fig_005.png").write_text("fake figure")

            registered = empty_librarian.register_kb_figures(
                str(kb_dir),
                sample_script,
            )

            assert len(registered) == 1

            # Check the registered figure
            asset = empty_librarian.library.get(registered[0])
            assert asset.asset_type == AssetType.FIGURE
            assert asset.source == AssetSource.KB_EXTRACTION
            assert asset.status == AssetStatus.APPROVED  # KB figures auto-approved
            assert asset.figure_number == 6

    def test_register_kb_figures_not_found(self, empty_librarian, sample_script):
        """Test registering when figure file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registered = empty_librarian.register_kb_figures(
                str(tmpdir),
                sample_script,
            )
            assert len(registered) == 0


class TestGetGenerationPlan:
    """Test generation planning."""

    def test_all_segments_need_generation(self, empty_librarian, sample_script):
        """Test that all segments need generation with empty library."""
        plan = empty_librarian.get_generation_plan(sample_script, AssetType.AUDIO)
        assert plan == [0, 1, 2, 3, 4]

    def test_some_segments_have_approved_assets(self, empty_librarian, sample_script):
        """Test that approved segments are excluded from plan."""
        # Add approved audio for segments 0 and 2
        empty_librarian.library.register(AssetRecord(
            asset_id="aud_0",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.APPROVED,
            segment_idx=0,
        ))
        empty_librarian.library.register(AssetRecord(
            asset_id="aud_2",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.APPROVED,
            segment_idx=2,
        ))

        plan = empty_librarian.get_generation_plan(sample_script, AssetType.AUDIO)
        assert 0 not in plan
        assert 2 not in plan
        assert plan == [1, 3, 4]

    def test_draft_assets_still_need_regeneration(self, empty_librarian, sample_script):
        """Test that draft (non-approved) assets are still in plan."""
        empty_librarian.library.register(AssetRecord(
            asset_id="aud_0",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.DRAFT,  # Not approved
            segment_idx=0,
        ))

        plan = empty_librarian.get_generation_plan(sample_script, AssetType.AUDIO)
        assert 0 in plan  # Still needs generation


class TestGetVisualAssignment:
    """Test visual assignment logic."""

    def test_figure_segment_gets_figure_sync(self, empty_librarian, sample_script):
        """Test that figure-referencing segments get figure_sync mode."""
        # Register the KB figure
        empty_librarian.library.register(AssetRecord(
            asset_id="kb_fig_006",
            asset_type=AssetType.FIGURE,
            source=AssetSource.KB_EXTRACTION,
            status=AssetStatus.APPROVED,
            figure_number=6,
        ))

        segment = sample_script.get_segment(2)  # Figure 6 segment
        mode, asset_id = empty_librarian.get_visual_assignment(segment)

        assert mode == "figure_sync"
        assert asset_id == "kb_fig_006"

    def test_figure_segment_without_figure_in_library(self, empty_librarian, sample_script):
        """Test figure segment when figure not in library."""
        segment = sample_script.get_segment(2)  # Figure 6 segment, but no figure registered
        mode, asset_id = empty_librarian.get_visual_assignment(segment)

        assert mode == "figure_sync"
        assert asset_id is None  # Figure not found

    def test_high_importance_gets_dall_e(self, empty_librarian, sample_script):
        """Test that high importance segments get dall_e mode."""
        segment = sample_script.get_segment(3)  # importance_score=0.7
        mode, asset_id = empty_librarian.get_visual_assignment(segment)

        assert mode == "dall_e"

    def test_approved_image_returned(self, empty_librarian, sample_script):
        """Test that approved images are returned."""
        empty_librarian.library.register(AssetRecord(
            asset_id="img_003",
            asset_type=AssetType.IMAGE,
            source=AssetSource.DALLE,
            status=AssetStatus.APPROVED,
            segment_idx=3,
        ))

        segment = sample_script.get_segment(3)
        mode, asset_id = empty_librarian.get_visual_assignment(segment)

        assert mode == "dall_e"
        assert asset_id == "img_003"

    def test_low_importance_gets_carry_forward(self, empty_librarian, sample_script):
        """Test that low importance segments get carry_forward mode."""
        # Modify segment 1 to have low importance
        sample_script.segments[1].importance_score = 0.3

        segment = sample_script.get_segment(1)
        mode, asset_id = empty_librarian.get_visual_assignment(segment)

        assert mode == "carry_forward"


class TestBuildAssemblyManifest:
    """Test assembly manifest building."""

    def test_build_manifest_empty_library(self, empty_librarian, sample_script):
        """Test building manifest with empty library."""
        manifest = empty_librarian.build_assembly_manifest(sample_script)

        assert manifest["script_id"] == "test_script_v1"
        assert manifest["total_segments"] == 5
        assert len(manifest["segments"]) == 5

        # Check figure sync point was recorded
        assert len(manifest["figure_sync_points"]) == 1
        assert manifest["figure_sync_points"][0]["segment_idx"] == 2
        assert manifest["figure_sync_points"][0]["figure_refs"] == [6]

    def test_build_manifest_with_assets(self, empty_librarian, sample_script):
        """Test building manifest with assets in library."""
        # Register audio for segment 0
        empty_librarian.library.register(AssetRecord(
            asset_id="aud_000",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.APPROVED,
            segment_idx=0,
            path="/audio/audio_000.mp3",
            duration_sec=5.0,
        ))

        # Register KB figure
        empty_librarian.library.register(AssetRecord(
            asset_id="kb_fig_006",
            asset_type=AssetType.FIGURE,
            source=AssetSource.KB_EXTRACTION,
            status=AssetStatus.APPROVED,
            figure_number=6,
            path="/figures/fig_005.png",
        ))

        manifest = empty_librarian.build_assembly_manifest(sample_script)

        # Check segment 0 has audio
        seg0 = manifest["segments"][0]
        assert seg0["audio"]["asset_id"] == "aud_000"
        assert seg0["audio"]["path"] == "/audio/audio_000.mp3"

        # Check segment 2 has figure
        seg2 = manifest["segments"][2]
        assert seg2["display_mode"] == "figure_sync"
        assert seg2["visual"]["asset_id"] == "kb_fig_006"

        # Check summary
        assert manifest["summary"]["total_audio"] >= 1
        assert manifest["summary"]["figure_syncs"] == 1

    def test_manifest_tracks_figure_sync_points(self, empty_librarian, sample_script):
        """Test that figure sync points are properly tracked."""
        manifest = empty_librarian.build_assembly_manifest(sample_script)

        # Should have one figure sync point for segment 2
        sync_points = manifest["figure_sync_points"]
        assert len(sync_points) == 1
        assert sync_points[0]["segment_idx"] == 2
        assert sync_points[0]["figure_refs"] == [6]


class TestMissingAssetsReport:
    """Test missing assets reporting."""

    def test_all_missing_with_empty_library(self, empty_librarian, sample_script):
        """Test report with empty library shows all missing."""
        report = empty_librarian.get_missing_assets_report(sample_script)

        # All segments missing audio
        assert len(report["segments_missing_audio"]) == 5

        # Figure 6 missing
        assert 6 in report["figures_missing"]

    def test_partial_missing(self, empty_librarian, sample_script):
        """Test report with some assets present."""
        # Add audio for segment 0
        empty_librarian.library.register(AssetRecord(
            asset_id="aud_0",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            segment_idx=0,
        ))

        # Add figure 6
        empty_librarian.library.register(AssetRecord(
            asset_id="fig_6",
            asset_type=AssetType.FIGURE,
            source=AssetSource.KB_EXTRACTION,
            figure_number=6,
        ))

        report = empty_librarian.get_missing_assets_report(sample_script)

        # Segment 0 should not be in missing audio
        assert 0 not in report["segments_missing_audio"]
        assert len(report["segments_missing_audio"]) == 4

        # Figure 6 should not be missing
        assert 6 not in report["figures_missing"]


class TestSaveAndLoad:
    """Test save and load functionality."""

    def test_save_library(self, empty_librarian):
        """Test saving library to disk."""
        empty_librarian.library.register(AssetRecord(
            asset_id="test",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
        ))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "library.json"
            saved_path = empty_librarian.save(path)

            assert saved_path.exists()

            # Verify content
            data = json.loads(saved_path.read_text())
            assert "test" in data["assets"]
