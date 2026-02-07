"""Unit tests for cli/assets.py - Asset management CLI commands

Tests the assets CLI with mock ContentLibrary and StructuredScript data.
Uses click.testing.CliRunner for testing CLI commands.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import tempfile

from core.models.content_library import (
    ContentLibrary,
    AssetRecord,
    AssetType,
    AssetStatus,
    AssetSource,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def runner():
    """Click CliRunner for testing CLI commands"""
    return CliRunner()


@pytest.fixture
def sample_content_library():
    """Create a sample ContentLibrary with various assets"""
    lib = ContentLibrary(project_id="test_project")

    # Add audio assets
    lib.register(AssetRecord(
        asset_id="aud_0001",
        asset_type=AssetType.AUDIO,
        source=AssetSource.ELEVENLABS,
        status=AssetStatus.DRAFT,
        segment_idx=0,
        path="/audio/audio_000.mp3",
    ))
    lib.register(AssetRecord(
        asset_id="aud_0002",
        asset_type=AssetType.AUDIO,
        source=AssetSource.ELEVENLABS,
        status=AssetStatus.APPROVED,
        segment_idx=1,
        path="/audio/audio_001.mp3",
    ))

    # Add image assets
    lib.register(AssetRecord(
        asset_id="img_0001",
        asset_type=AssetType.IMAGE,
        source=AssetSource.DALLE,
        status=AssetStatus.DRAFT,
        segment_idx=0,
        path="/images/scene_000.png",
    ))
    lib.register(AssetRecord(
        asset_id="img_0002",
        asset_type=AssetType.IMAGE,
        source=AssetSource.DALLE,
        status=AssetStatus.REJECTED,
        segment_idx=1,
        path="/images/scene_001.png",
    ))

    # Add figure asset
    lib.register(AssetRecord(
        asset_id="fig_0001",
        asset_type=AssetType.FIGURE,
        source=AssetSource.KB_EXTRACTION,
        status=AssetStatus.APPROVED,
        figure_number=6,
        path="/figures/fig_005.png",
    ))

    return lib


# ============================================================
# Tests for find_library function
# ============================================================

class TestFindLibrary:
    """Tests for the find_library helper function"""

    def test_find_library_content_library_json(self):
        """Should load content_library.json when present"""
        from cli.assets import find_library

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)

            # Create a content library file
            lib = ContentLibrary(project_id="test")
            lib.save(run_path / "content_library.json")

            result = find_library(run_path)
            assert result is not None
            assert result.project_id == "test"

    def test_find_library_missing_dir(self):
        """Should return None for directory without library"""
        from cli.assets import find_library

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            result = find_library(run_path)
            assert result is None


# ============================================================
# Tests for parse_segment_range function
# ============================================================

class TestParseSegmentRange:
    """Tests for segment range parsing"""

    def test_parse_single_number(self):
        """Should parse single number"""
        from cli.assets import parse_segment_range

        result = parse_segment_range("5")
        assert result == [5]

    def test_parse_comma_separated(self):
        """Should parse comma-separated list"""
        from cli.assets import parse_segment_range

        result = parse_segment_range("1,3,5")
        assert result == [1, 3, 5]

    def test_parse_range(self):
        """Should parse range with hyphen"""
        from cli.assets import parse_segment_range

        result = parse_segment_range("1-5")
        assert result == [1, 2, 3, 4, 5]

    def test_parse_all(self):
        """Should return empty list for 'all'"""
        from cli.assets import parse_segment_range

        result = parse_segment_range("all")
        assert result == []

    def test_parse_mixed(self):
        """Should parse mixed format"""
        from cli.assets import parse_segment_range

        result = parse_segment_range("1,3-5,10")
        assert result == [1, 3, 4, 5, 10]


# ============================================================
# Tests for list command
# ============================================================

class TestAssetListCommand:
    """Tests for the 'assets list' command"""

    def test_list_all_assets(self, runner, sample_content_library):
        """List command shows all assets"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["list", str(run_path)])
            assert result.exit_code == 0
            assert "aud_0001" in result.output or "AUDIO" in result.output

    def test_list_filter_by_status(self, runner, sample_content_library):
        """List command filters by status"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["list", str(run_path), "--status", "approved"])
            assert result.exit_code == 0

    def test_list_filter_by_type(self, runner, sample_content_library):
        """List command filters by asset type"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["list", str(run_path), "--type", "audio"])
            assert result.exit_code == 0

    def test_list_empty_library(self, runner):
        """List command handles empty library"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            lib = ContentLibrary(project_id="empty")
            lib.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["list", str(run_path)])
            assert result.exit_code == 0
            assert "No assets found" in result.output

    def test_list_no_library(self, runner):
        """List command errors when no library found"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(assets, ["list", tmpdir])
            assert result.exit_code != 0
            assert "No content library found" in result.output


# ============================================================
# Tests for approve command
# ============================================================

class TestAssetApproveCommand:
    """Tests for the 'assets approve' command"""

    def test_approve_audio_all(self, runner, sample_content_library):
        """Approve all audio assets"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["approve", str(run_path), "--audio", "all"])
            assert result.exit_code == 0
            assert "Approved" in result.output

            # Verify library was updated
            lib = ContentLibrary.load(run_path / "content_library.json")
            audio_assets = lib.query(asset_type=AssetType.AUDIO)
            for asset in audio_assets:
                assert asset.status == AssetStatus.APPROVED

    def test_approve_image_specific(self, runner, sample_content_library):
        """Approve specific image segments"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["approve", str(run_path), "--image", "0"])
            assert result.exit_code == 0

    def test_approve_no_match(self, runner, sample_content_library):
        """Approve command with no matching assets"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["approve", str(run_path), "--image", "999"])
            assert result.exit_code == 0
            assert "No assets matched" in result.output


# ============================================================
# Tests for reject command
# ============================================================

class TestAssetRejectCommand:
    """Tests for the 'assets reject' command"""

    def test_reject_with_reason(self, runner, sample_content_library):
        """Reject assets with reason"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, [
                "reject", str(run_path),
                "--image", "0",
                "--reason", "wrong style"
            ])
            assert result.exit_code == 0
            assert "Rejected" in result.output

    def test_reject_audio(self, runner, sample_content_library):
        """Reject audio assets"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, [
                "reject", str(run_path),
                "--audio", "0"
            ])
            assert result.exit_code == 0


# ============================================================
# Tests for build command
# ============================================================

class TestAssetBuildCommand:
    """Tests for the 'assets build' command"""

    def test_build_shows_plan(self, runner, sample_content_library):
        """Build command shows asset counts"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["build", str(run_path)])
            assert result.exit_code == 0
            assert "Build Plan" in result.output

    def test_build_no_approved(self, runner):
        """Build command errors with no approved assets"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            lib = ContentLibrary(project_id="test")
            # Add only draft assets
            lib.register(AssetRecord(
                asset_id="aud_001",
                asset_type=AssetType.AUDIO,
                source=AssetSource.ELEVENLABS,
                status=AssetStatus.DRAFT,
            ))
            lib.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["build", str(run_path)])
            assert result.exit_code != 0
            assert "No approved assets" in result.output


# ============================================================
# Tests for import command
# ============================================================

class TestAssetImportCommand:
    """Tests for the 'assets import' command"""

    def test_import_approved_assets(self, runner, sample_content_library):
        """Import approved assets from another run"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source"
            target_path = Path(tmpdir) / "target"
            source_path.mkdir()
            target_path.mkdir()

            sample_content_library.save(source_path / "content_library.json")
            target_lib = ContentLibrary(project_id="target")
            target_lib.save(target_path / "content_library.json")

            result = runner.invoke(assets, [
                "import",
                str(source_path),
                str(target_path),
                "--status", "approved"
            ])
            assert result.exit_code == 0


# ============================================================
# Tests for summary command
# ============================================================

class TestAssetSummaryCommand:
    """Tests for the 'assets summary' command"""

    def test_summary_shows_counts(self, runner, sample_content_library):
        """Summary command shows asset counts"""
        from cli.assets import assets

        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir)
            sample_content_library.save(run_path / "content_library.json")

            result = runner.invoke(assets, ["summary", str(run_path)])
            assert result.exit_code == 0
            assert "Asset Summary" in result.output
