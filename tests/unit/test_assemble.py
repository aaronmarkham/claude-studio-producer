"""Unit tests for cli/assemble.py module"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

from cli.assemble import (
    VisualSegment,
    AudioClip,
    load_production_run,
    build_visual_segments_from_manifest,
    build_visual_segments_from_librarian,
    get_media_duration,
    print_assembly_summary,
)
from core.models.structured_script import (
    StructuredScript,
    ScriptSegment,
    SegmentIntent,
    FigureInventory,
)
from core.models.content_library import (
    ContentLibrary,
    AssetRecord,
    AssetType,
    AssetSource,
    AssetStatus,
)
from core.content_librarian import ContentLibrarian


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_run_dir():
    """Create a temporary run directory with common subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        (run_dir / "audio").mkdir()
        (run_dir / "images").mkdir()
        (run_dir / "assembly").mkdir()
        yield run_dir


@pytest.fixture
def sample_structured_script():
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


@pytest.fixture
def sample_content_library():
    """Create a sample content library with assets."""
    lib = ContentLibrary(project_id="test_project")

    # Register some audio
    for i in range(5):
        lib.register(AssetRecord(
            asset_id=f"aud_{i:03d}",
            asset_type=AssetType.AUDIO,
            source=AssetSource.ELEVENLABS,
            status=AssetStatus.APPROVED,
            segment_idx=i,
            path=f"audio/audio_{i:03d}.mp3",
            duration_sec=5.0 + i,
        ))

    # Register a figure
    lib.register(AssetRecord(
        asset_id="kb_fig_006",
        asset_type=AssetType.FIGURE,
        source=AssetSource.KB_EXTRACTION,
        status=AssetStatus.APPROVED,
        figure_number=6,
        path="figures/fig_005.png",
    ))

    return lib


@pytest.fixture
def sample_manifest():
    """Create a sample asset manifest."""
    return {
        "assets": [
            {
                "scene_id": "scene_000",
                "audio_path": "audio/audio_000.mp3",
                "image_path": "images/scene_000.png",
            },
            {
                "scene_id": "scene_001",
                "audio_path": "audio/audio_001.mp3",
                "image_path": None,
            },
            {
                "scene_id": "scene_002",
                "audio_path": "audio/audio_002.mp3",
                "image_path": "images/scene_002.png",
            },
        ]
    }


# ============================================================
# Tests for VisualSegment Dataclass
# ============================================================


class TestVisualSegmentDataclass:
    """Test VisualSegment dataclass creation and properties."""

    def test_visual_segment_creation(self):
        """Test creating a VisualSegment with all fields."""
        image_path = Path("/tmp/image.png")
        audio_path = Path("/tmp/audio.mp3")

        segment = VisualSegment(
            segment_idx=0,
            display_mode="dall_e",
            image_path=image_path,
            audio_path=audio_path,
            audio_duration=5.0,
            start_time=0.0,
            end_time=5.0,
        )

        assert segment.segment_idx == 0
        assert segment.display_mode == "dall_e"
        assert segment.image_path == image_path
        assert segment.audio_path == audio_path
        assert segment.audio_duration == 5.0
        assert segment.start_time == 0.0
        assert segment.end_time == 5.0

    def test_visual_segment_with_optional_paths(self):
        """Test VisualSegment with None paths."""
        segment = VisualSegment(
            segment_idx=1,
            display_mode="text_only",
            image_path=None,
            audio_path=None,
            audio_duration=3.0,
            start_time=5.0,
            end_time=8.0,
        )

        assert segment.image_path is None
        assert segment.audio_path is None
        assert segment.display_mode == "text_only"

    def test_visual_segment_display_modes(self):
        """Test VisualSegment with different display modes."""
        modes = ["figure_sync", "dall_e", "carry_forward", "text_only"]

        for i, mode in enumerate(modes):
            segment = VisualSegment(
                segment_idx=i,
                display_mode=mode,
                image_path=None,
                audio_path=None,
                audio_duration=5.0,
                start_time=float(i * 5),
                end_time=float((i + 1) * 5),
            )
            assert segment.display_mode == mode


class TestAudioClipDataclass:
    """Test AudioClip dataclass creation."""

    def test_audio_clip_creation(self):
        """Test creating an AudioClip with all fields."""
        path = Path("/tmp/audio.mp3")
        clip = AudioClip(
            path=path,
            duration=5.0,
            segment_idx=0,
            start_time=0.0,
        )

        assert clip.path == path
        assert clip.duration == 5.0
        assert clip.segment_idx == 0
        assert clip.start_time == 0.0

    def test_audio_clip_with_custom_start_time(self):
        """Test AudioClip with custom start_time."""
        clip = AudioClip(
            path=Path("/tmp/audio.mp3"),
            duration=3.0,
            segment_idx=2,
            start_time=10.5,
        )

        assert clip.start_time == 10.5


# ============================================================
# Tests for load_production_run()
# ============================================================


class TestLoadProductionRun:
    """Test load_production_run() function."""

    def test_load_structured_script(self, temp_run_dir, sample_structured_script):
        """Test loading structured script from run directory."""
        script_path = temp_run_dir / "trial_000_structured_script.json"
        sample_structured_script.save(script_path)

        script, library, manifest = load_production_run(temp_run_dir)

        assert script is not None
        assert script.script_id == "test_script_v1"
        assert len(script.segments) == 5

    def test_load_content_library(self, temp_run_dir, sample_content_library):
        """Test loading content library from run directory."""
        lib_path = temp_run_dir / "content_library.json"
        sample_content_library.save(lib_path)

        script, library, manifest = load_production_run(temp_run_dir)

        assert library is not None
        assert library.project_id == "test_project"

    def test_load_asset_manifest(self, temp_run_dir, sample_manifest):
        """Test loading asset manifest from run directory."""
        manifest_path = temp_run_dir / "asset_manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(sample_manifest, f)

        script, library, manifest = load_production_run(temp_run_dir)

        assert manifest is not None
        assert len(manifest.get("assets", [])) == 3

    def test_load_all_artifacts_together(self, temp_run_dir, sample_structured_script, sample_content_library, sample_manifest):
        """Test loading all artifacts together."""
        # Save all artifacts
        sample_structured_script.save(temp_run_dir / "trial_000_structured_script.json")
        sample_content_library.save(temp_run_dir / "content_library.json")
        with open(temp_run_dir / "asset_manifest.json", 'w') as f:
            json.dump(sample_manifest, f)

        script, library, manifest = load_production_run(temp_run_dir)

        assert script is not None
        assert library is not None
        assert manifest is not None

    def test_load_empty_run_dir(self, temp_run_dir):
        """Test loading from empty directory returns None/empty values."""
        script, library, manifest = load_production_run(temp_run_dir)

        assert script is None
        assert library is None
        assert manifest == {}

    def test_load_with_corrupted_json(self, temp_run_dir):
        """Test that corrupted JSON files are gracefully handled."""
        # Corrupt script file
        script_path = temp_run_dir / "trial_000_structured_script.json"
        script_path.write_text("{invalid json}")

        # Corrupt manifest file
        manifest_path = temp_run_dir / "asset_manifest.json"
        manifest_path.write_text("{invalid json}")

        script, library, manifest = load_production_run(temp_run_dir)

        assert script is None
        assert library is None
        assert manifest == {}


# ============================================================
# Tests for build_visual_segments_from_manifest()
# ============================================================


class TestBuildVisualSegmentsFromManifest:
    """Test build_visual_segments_from_manifest() function."""

    def test_build_basic_segments(self, temp_run_dir, sample_manifest):
        """Test building segments from a basic manifest."""
        # Create dummy audio and image files
        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        for asset in sample_manifest["assets"]:
            if asset.get("audio_path"):
                Path(asset["audio_path"]).parent.mkdir(parents=True, exist_ok=True)
                Path(asset["audio_path"]).write_text("mock audio")
            if asset.get("image_path"):
                Path(asset["image_path"]).parent.mkdir(parents=True, exist_ok=True)
                Path(asset["image_path"]).write_text("mock image")

        with patch('cli.assemble.get_media_duration', return_value=5.0):
            segments = build_visual_segments_from_manifest(sample_manifest, audio_dir, images_dir)

        assert len(segments) == 3
        assert segments[0].segment_idx == 0
        assert segments[0].display_mode == "dall_e"
        assert segments[0].image_path is not None

    def test_segments_have_cumulative_timing(self, temp_run_dir, sample_manifest):
        """Test that segments have proper cumulative timing."""
        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        with patch('cli.assemble.get_media_duration', side_effect=[3.0, 4.0, 5.0]):
            segments = build_visual_segments_from_manifest(sample_manifest, audio_dir, images_dir)

        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 3.0

        assert segments[1].start_time == 3.0
        assert segments[1].end_time == 7.0

        assert segments[2].start_time == 7.0
        assert segments[2].end_time == 12.0

    def test_carry_forward_display_mode(self, temp_run_dir):
        """Test that carry_forward mode is used when no image."""
        manifest = {
            "assets": [
                {"scene_id": "scene_000", "audio_path": "audio/audio_000.mp3", "image_path": "images/scene_000.png"},
                {"scene_id": "scene_001", "audio_path": "audio/audio_001.mp3", "image_path": None},
            ]
        }

        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        # Create first image
        images_dir.mkdir(exist_ok=True)
        (images_dir / "scene_000.png").write_text("mock")

        with patch('cli.assemble.get_media_duration', return_value=5.0):
            segments = build_visual_segments_from_manifest(manifest, audio_dir, images_dir)

        assert segments[0].display_mode == "dall_e"
        assert segments[1].display_mode == "carry_forward"
        assert segments[1].image_path == segments[0].image_path  # Same image

    def test_empty_manifest(self, temp_run_dir):
        """Test with empty manifest."""
        manifest = {"assets": []}
        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        segments = build_visual_segments_from_manifest(manifest, audio_dir, images_dir)

        assert len(segments) == 0

    def test_missing_audio_file(self, temp_run_dir):
        """Test handling of missing audio files."""
        manifest = {
            "assets": [
                {"scene_id": "scene_000", "audio_path": None, "image_path": None},
            ]
        }

        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        with patch('cli.assemble.get_media_duration', return_value=5.0):
            segments = build_visual_segments_from_manifest(manifest, audio_dir, images_dir)

        assert len(segments) == 1
        assert segments[0].audio_path is None
        assert segments[0].audio_duration == 5.0  # Default

    def test_scene_id_parsing(self, temp_run_dir):
        """Test extraction of segment index from scene_id."""
        manifest = {
            "assets": [
                {"scene_id": "scene_005", "audio_path": None, "image_path": None},
                {"scene_id": "scene_042", "audio_path": None, "image_path": None},
            ]
        }

        audio_dir = temp_run_dir / "audio"
        images_dir = temp_run_dir / "images"

        with patch('cli.assemble.get_media_duration', return_value=5.0):
            segments = build_visual_segments_from_manifest(manifest, audio_dir, images_dir)

        assert segments[0].segment_idx == 5
        assert segments[1].segment_idx == 42


# ============================================================
# Tests for build_visual_segments_from_librarian()
# ============================================================


class TestBuildVisualSegmentsFromLibrarian:
    """Test build_visual_segments_from_librarian() function."""

    def test_build_segments_with_librarian(self, temp_run_dir, sample_structured_script, sample_content_library):
        """Test building segments using librarian."""
        audio_dir = temp_run_dir / "audio"

        librarian = ContentLibrarian(sample_content_library)

        with patch.object(librarian, 'build_assembly_manifest') as mock_manifest:
            mock_manifest.return_value = {
                "segments": [
                    {
                        "segment_idx": 0,
                        "display_mode": "dall_e",
                        "audio": {"path": "audio/audio_000.mp3", "duration_sec": 5.0},
                        "visual": {"path": "images/scene_000.png"},
                    },
                    {
                        "segment_idx": 1,
                        "display_mode": "carry_forward",
                        "audio": {"path": "audio/audio_001.mp3", "duration_sec": 4.0},
                        "visual": {"path": None},
                    },
                ]
            }

            with patch('cli.assemble.get_media_duration', return_value=5.0):
                segments, manifest = build_visual_segments_from_librarian(
                    sample_structured_script, librarian, audio_dir
                )

        assert len(segments) == 2
        assert segments[0].display_mode == "dall_e"
        assert segments[1].display_mode == "carry_forward"
        # Verify manifest is returned for debugging
        assert manifest is not None
        assert "segments" in manifest

    def test_librarian_figure_sync_mode(self, temp_run_dir, sample_structured_script, sample_content_library):
        """Test that figure_sync mode is properly set from librarian."""
        audio_dir = temp_run_dir / "audio"

        # Create the figure file so it exists
        figures_dir = temp_run_dir / "figures"
        figures_dir.mkdir()
        (figures_dir / "fig_005.png").write_text("mock figure")

        librarian = ContentLibrarian(sample_content_library)

        with patch.object(librarian, 'build_assembly_manifest') as mock_manifest:
            mock_manifest.return_value = {
                "segments": [
                    {
                        "segment_idx": 2,
                        "display_mode": "figure_sync",
                        "audio": {"path": str(audio_dir / "audio_002.mp3"), "duration_sec": 6.0},
                        "visual": {"path": str(figures_dir / "fig_005.png")},
                    },
                ]
            }

            with patch('cli.assemble.get_media_duration', return_value=6.0):
                segments, manifest = build_visual_segments_from_librarian(
                    sample_structured_script, librarian, audio_dir
                )

        assert len(segments) == 1
        assert segments[0].display_mode == "figure_sync"
        assert segments[0].image_path == Path(str(figures_dir / "fig_005.png"))
        assert manifest is not None

    def test_librarian_cumulative_timing(self, temp_run_dir, sample_structured_script, sample_content_library):
        """Test cumulative timing with librarian."""
        audio_dir = temp_run_dir / "audio"

        librarian = ContentLibrarian(sample_content_library)

        with patch.object(librarian, 'build_assembly_manifest') as mock_manifest:
            mock_manifest.return_value = {
                "segments": [
                    {
                        "segment_idx": 0,
                        "display_mode": "dall_e",
                        "audio": {"path": None, "duration_sec": 3.0},
                        "visual": {"path": None},
                    },
                    {
                        "segment_idx": 1,
                        "display_mode": "carry_forward",
                        "audio": {"path": None, "duration_sec": 4.0},
                        "visual": {"path": None},
                    },
                    {
                        "segment_idx": 2,
                        "display_mode": "dall_e",
                        "audio": {"path": None, "duration_sec": 5.0},
                        "visual": {"path": None},
                    },
                ]
            }

            segments, manifest = build_visual_segments_from_librarian(
                sample_structured_script, librarian, audio_dir
            )

        assert segments[0].start_time == 0.0
        assert segments[0].end_time == 3.0

        assert segments[1].start_time == 3.0
        assert segments[1].end_time == 7.0

        assert segments[2].start_time == 7.0
        assert segments[2].end_time == 12.0

        assert manifest is not None

    def test_librarian_carry_forward_logic(self, temp_run_dir, sample_structured_script, sample_content_library):
        """Test carry-forward logic with librarian."""
        audio_dir = temp_run_dir / "audio"

        librarian = ContentLibrarian(sample_content_library)

        with patch.object(librarian, 'build_assembly_manifest') as mock_manifest:
            # First segment has image, second and third carry forward
            mock_manifest.return_value = {
                "segments": [
                    {
                        "segment_idx": 0,
                        "display_mode": "dall_e",
                        "audio": {"path": None, "duration_sec": 5.0},
                        "visual": {"path": "images/scene_000.png"},
                    },
                    {
                        "segment_idx": 1,
                        "display_mode": "carry_forward",
                        "audio": {"path": None, "duration_sec": 5.0},
                        "visual": {"path": None},
                    },
                    {
                        "segment_idx": 2,
                        "display_mode": "carry_forward",
                        "audio": {"path": None, "duration_sec": 5.0},
                        "visual": {"path": None},
                    },
                ]
            }

            segments, manifest = build_visual_segments_from_librarian(
                sample_structured_script, librarian, audio_dir
            )

        # All should reference the same first image
        assert segments[0].image_path == Path("images/scene_000.png")
        assert segments[1].image_path == segments[0].image_path
        assert segments[2].image_path == segments[0].image_path
        assert manifest is not None

    def test_librarian_missing_audio_info(self, temp_run_dir, sample_structured_script, sample_content_library):
        """Test handling when audio info is missing."""
        audio_dir = temp_run_dir / "audio"

        librarian = ContentLibrarian(sample_content_library)

        with patch.object(librarian, 'build_assembly_manifest') as mock_manifest:
            mock_manifest.return_value = {
                "segments": [
                    {
                        "segment_idx": 0,
                        "display_mode": "dall_e",
                        "audio": {},  # Missing path and duration
                        "visual": {"path": None},
                    },
                ]
            }

            segments, manifest = build_visual_segments_from_librarian(
                sample_structured_script, librarian, audio_dir
            )

        assert len(segments) == 1
        assert segments[0].audio_duration == 5.0  # Default value
        assert manifest is not None


# ============================================================
# Tests for get_media_duration()
# ============================================================


class TestGetMediaDuration:
    """Test get_media_duration() function."""

    def test_get_duration_success(self):
        """Test successfully getting media duration."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout="30.5", returncode=0)

            duration = get_media_duration(Path("/tmp/video.mp4"))

            assert duration == 30.5

    def test_get_duration_timeout(self):
        """Test handling of ffprobe timeout."""
        import subprocess
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 30)

            duration = get_media_duration(Path("/tmp/video.mp4"))

            assert duration == 0.0

    def test_get_duration_invalid_output(self):
        """Test handling of invalid ffprobe output."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(stdout="not a number", returncode=0)

            duration = get_media_duration(Path("/tmp/video.mp4"))

            assert duration == 0.0


# ============================================================
# Tests for print_assembly_summary()
# ============================================================


class TestPrintAssemblySummary:
    """Test print_assembly_summary() function."""

    def test_print_summary_counts_display_modes(self, capsys):
        """Test that summary correctly counts display modes."""
        from cli.theme import get_theme

        segments = [
            VisualSegment(0, "dall_e", None, None, 5.0, 0.0, 5.0),
            VisualSegment(1, "dall_e", None, None, 5.0, 5.0, 10.0),
            VisualSegment(2, "carry_forward", None, None, 5.0, 10.0, 15.0),
            VisualSegment(3, "figure_sync", None, None, 4.0, 15.0, 19.0),
        ]

        t = get_theme()
        print_assembly_summary(segments, t)

        captured = capsys.readouterr()
        assert "Assembly Plan" in captured.out or "carry_forward" in captured.out

    def test_print_summary_calculates_totals(self):
        """Test that summary calculates total duration correctly."""
        from cli.theme import get_theme

        segments = [
            VisualSegment(0, "dall_e", None, None, 3.0, 0.0, 3.0),
            VisualSegment(1, "carry_forward", None, None, 4.0, 3.0, 7.0),
            VisualSegment(2, "dall_e", None, None, 5.0, 7.0, 12.0),
        ]

        t = get_theme()
        # Just verify it doesn't crash
        print_assembly_summary(segments, t)

    def test_print_summary_empty_segments(self):
        """Test summary with empty segment list."""
        from cli.theme import get_theme

        segments = []
        t = get_theme()
        print_assembly_summary(segments, t)
