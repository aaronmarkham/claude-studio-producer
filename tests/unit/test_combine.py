"""Smoke tests for cli/combine.py - scene-combining module entry point.

cli/combine.py is a standalone module run via `python -m cli.combine`, NOT a
registered Click subcommand in cli/__init__.py. These tests document its
behavior and guard against regressions in scene listing, argument validation,
ffmpeg discovery, and the concat flow (ffmpeg/subprocess are mocked, so no real
binary or video files are needed).
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from cli.combine import combine_cmd, find_ffmpeg, list_scenes


@pytest.fixture
def runner():
    return CliRunner()


def _make_run(base: Path, run_id: str, scene_nums) -> Path:
    """Create a run dir with empty scene_<n>_v0.mp4 video files."""
    run_dir = base / "artifacts" / "runs" / run_id
    videos = run_dir / "videos"
    videos.mkdir(parents=True)
    for n in scene_nums:
        (videos / f"scene_{n}_v0.mp4").write_bytes(b"\x00" * 16)
    return run_dir


# ------------------------------------------------------------------
# list_scenes
# ------------------------------------------------------------------

def test_list_scenes_parses_and_sorts(tmp_path):
    run_dir = _make_run(tmp_path, "run1", [3, 1, 2])
    scenes = list_scenes(run_dir)
    assert [s["number"] for s in scenes] == [1, 2, 3]
    assert scenes[0]["filename"] == "scene_1_v0.mp4"
    assert scenes[0]["size"] == 16


def test_list_scenes_missing_videos_dir(tmp_path):
    assert list_scenes(tmp_path / "nope") == []


# ------------------------------------------------------------------
# find_ffmpeg
# ------------------------------------------------------------------

def test_find_ffmpeg_returns_first_working(tmp_path):
    ok = MagicMock(returncode=0)
    with patch("cli.combine.subprocess.run", return_value=ok):
        assert find_ffmpeg() == "ffmpeg"


def test_find_ffmpeg_raises_when_absent():
    with patch("cli.combine.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            find_ffmpeg()


# ------------------------------------------------------------------
# combine_cmd - validation paths (no ffmpeg needed)
# ------------------------------------------------------------------

def test_combine_missing_run_dir(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(combine_cmd, ["missing_run"])
        assert result.exit_code == 0
        assert "Run directory not found" in result.output


def test_combine_list_mode(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        result = runner.invoke(combine_cmd, ["run1", "--list"])
        assert result.exit_code == 0
        assert "Available Scenes" in result.output
        assert "scene_1_v0.mp4" in result.output


def test_combine_no_scenes_specified(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        result = runner.invoke(combine_cmd, ["run1"])
        assert result.exit_code == 0
        assert "specify scenes to combine" in result.output


def test_combine_invalid_scene_format(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,x"])
        assert result.exit_code == 0
        assert "Invalid scene format" in result.output


def test_combine_requires_two_scenes(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        result = runner.invoke(combine_cmd, ["run1", "--scenes", "1"])
        assert result.exit_code == 0
        assert "at least 2 scenes" in result.output


def test_combine_missing_scene_numbers(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,9"])
        assert result.exit_code == 0
        assert "Scene(s) not found" in result.output


def test_combine_no_videos(runner):
    with runner.isolated_filesystem() as fs:
        (Path(fs) / "artifacts" / "runs" / "run1" / "videos").mkdir(parents=True)
        result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,2"])
        assert result.exit_code == 0
        assert "No video scenes found" in result.output


# ------------------------------------------------------------------
# combine_cmd - successful concat flow (ffmpeg mocked)
# ------------------------------------------------------------------

def test_combine_success(runner):
    with runner.isolated_filesystem() as fs:
        run_dir = _make_run(Path(fs), "run1", [1, 2, 3])

        def fake_run(cmd, *args, **kwargs):
            # The concat call is the one with "-f" "concat"; write the output file.
            if "concat" in cmd:
                out = Path(cmd[-1])
                out.write_bytes(b"\x00" * (2 * 1024 * 1024))
            return MagicMock(returncode=0, stderr="", stdout="")

        with patch("cli.combine.find_ffmpeg", return_value="ffmpeg"), \
             patch("cli.combine.subprocess.run", side_effect=fake_run):
            result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,3"])

        assert result.exit_code == 0
        assert "Combined video created" in result.output
        assert (run_dir / "renders" / "scenes_1_3_combined.mp4").exists()


def test_combine_custom_output_name(runner):
    with runner.isolated_filesystem() as fs:
        run_dir = _make_run(Path(fs), "run1", [1, 2])

        def fake_run(cmd, *args, **kwargs):
            if "concat" in cmd:
                Path(cmd[-1]).write_bytes(b"\x00" * 1024)
            return MagicMock(returncode=0, stderr="", stdout="")

        with patch("cli.combine.find_ffmpeg", return_value="ffmpeg"), \
             patch("cli.combine.subprocess.run", side_effect=fake_run):
            result = runner.invoke(
                combine_cmd, ["run1", "--scenes", "1,2", "-o", "highlight"]
            )

        assert result.exit_code == 0
        # ".mp4" auto-appended
        assert (run_dir / "renders" / "highlight.mp4").exists()


def test_combine_ffmpeg_failure(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        failed = MagicMock(returncode=1, stderr="boom", stdout="")
        with patch("cli.combine.find_ffmpeg", return_value="ffmpeg"), \
             patch("cli.combine.subprocess.run", return_value=failed):
            result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,2"])

        assert result.exit_code == 0
        assert "ffmpeg failed" in result.output


def test_combine_ffmpeg_not_found(runner):
    with runner.isolated_filesystem() as fs:
        _make_run(Path(fs), "run1", [1, 2])
        with patch("cli.combine.find_ffmpeg",
                   side_effect=FileNotFoundError("no ffmpeg")):
            result = runner.invoke(combine_cmd, ["run1", "--scenes", "1,2"])

        assert result.exit_code == 0
        assert "no ffmpeg" in result.output
