"""Tests for RunManifest model."""

import json
import pytest
from pathlib import Path

from core.models.run_manifest import (
    RunManifest, RunStage, SourceType, SceneStatus,
    SceneManifest, AudioManifest, BudgetManifest,
)


@pytest.fixture
def sample_manifest():
    m = RunManifest(
        run_id="20260221_120000",
        source_type=SourceType.PAPER,
        stage=RunStage.PRODUCTION,
        prompt="Test video about coffee",
        budget=BudgetManifest(total=15.0),
    )
    m.scenes = [
        SceneManifest(scene_id="s1", title="Intro", status=SceneStatus.READY, cost=3.0, provider="luma"),
        SceneManifest(scene_id="s2", title="Method", status=SceneStatus.FAILED, cost=0.0, provider="luma", error="timeout"),
        SceneManifest(scene_id="s3", title="Tips", status=SceneStatus.PENDING, provider="auto"),
    ]
    m.audio.voice = "nova"
    m.budget.spent = 3.0
    m.budget.per_scene = {"s1": 3.0}
    return m


class TestRunManifest:
    def test_scene_counts(self, sample_manifest):
        assert sample_manifest.scenes_ready == 1
        assert sample_manifest.scenes_failed == 1
        assert sample_manifest.scenes_pending == 1
        assert not sample_manifest.all_scenes_done

    def test_get_scene(self, sample_manifest):
        s = sample_manifest.get_scene("s2")
        assert s is not None
        assert s.title == "Method"
        assert sample_manifest.get_scene("nope") is None

    def test_roundtrip(self, sample_manifest, tmp_path):
        path = tmp_path / "manifest.json"
        sample_manifest.run_dir = str(tmp_path)
        sample_manifest.save(path)
        loaded = RunManifest.load(path)
        assert loaded.run_id == sample_manifest.run_id
        assert loaded.stage == RunStage.PRODUCTION
        assert loaded.source_type == SourceType.PAPER
        assert len(loaded.scenes) == 3
        assert loaded.scenes[0].status == SceneStatus.READY
        assert loaded.scenes[1].error == "timeout"
        assert loaded.budget.total == 15.0
        assert loaded.budget.spent == 3.0

    def test_summary(self, sample_manifest):
        s = sample_manifest.summary()
        assert "20260221_120000" in s
        assert "1/3 ready" in s
        assert "1 failed" in s

    def test_timeline(self, sample_manifest):
        t = sample_manifest.timeline()
        assert "✅" in t
        assert "❌" in t
        assert "⏳" in t

    def test_budget_tracking(self):
        b = BudgetManifest(total=10.0)
        assert b.remaining == 10.0
        assert b.can_spend(5.0)
        b.record_spend("s1", 4.32)
        assert b.spent == pytest.approx(4.32)
        assert b.remaining == pytest.approx(5.68)
        assert b.per_scene["s1"] == pytest.approx(4.32)

    def test_find_run(self, sample_manifest, tmp_path):
        run_dir = tmp_path / "artifacts" / "runs" / sample_manifest.run_id
        run_dir.mkdir(parents=True)
        sample_manifest.run_dir = str(run_dir)
        sample_manifest.save(run_dir / "manifest.json")
        found = RunManifest.find_run(
            sample_manifest.run_id,
            artifacts_dir=str(tmp_path / "artifacts" / "runs"),
        )
        assert found is not None
        assert found.run_id == sample_manifest.run_id

    def test_all_scenes_done(self):
        m = RunManifest(run_id="test", scenes=[
            SceneManifest(scene_id="s1", status=SceneStatus.READY),
            SceneManifest(scene_id="s2", status=SceneStatus.SKIPPED),
        ])
        assert m.all_scenes_done

    def test_scene_edit_workflow(self, sample_manifest):
        """Simulate editing a failed scene."""
        s = sample_manifest.get_scene("s2")
        s.provider = "higgsfield"
        s.status = SceneStatus.PENDING
        s.attempts = 0
        s.error = None
        assert sample_manifest.scenes_pending == 2
        assert sample_manifest.scenes_failed == 0
