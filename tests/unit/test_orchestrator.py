"""Orchestrator unit tests

Tests the StudioOrchestrator pipeline with mocked agents to verify:
- Correct agent call sequence (planning → generation → QA → critic → selection)
- Budget enforcement at every stage
- Pilot approval/rejection gates
- Parallel pilot execution
- Error handling and edge cases

No real API calls — all agents are mocked.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import List

from core.orchestrator import StudioOrchestrator, ProductionResult
from core.budget import BudgetTracker, ProductionTier
from agents.producer import PilotStrategy
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from agents.qa_verifier import QAResult
from agents.critic import SceneResult, PilotResults


# ============================================================
# Factories — lightweight builders for test data
# ============================================================

def _scene(scene_id="scene_1", duration=5.0) -> Scene:
    return Scene(
        scene_id=scene_id,
        title=f"Test {scene_id}",
        description=f"Description for {scene_id}",
        duration=duration,
        visual_elements=["element"],
        audio_notes="ambient",
        transition_in="cut",
        transition_out="cut",
        prompt_hints=["professional"],
    )


def _video(scene_id="scene_1", variation=0, cost=0.50) -> GeneratedVideo:
    return GeneratedVideo(
        scene_id=scene_id,
        variation_id=variation,
        video_url=f"https://mock/{scene_id}_v{variation}.mp4",
        thumbnail_url=f"https://mock/{scene_id}_v{variation}_thumb.jpg",
        generation_cost=cost,
        duration=5.0,
        provider="mock",
        metadata={"prompt": "test prompt"},
        quality_score=80.0,
    )


def _qa(scene_id="scene_1", score=85.0) -> QAResult:
    return QAResult(
        scene_id=scene_id,
        video_url=f"https://mock/{scene_id}.mp4",
        overall_score=score,
        visual_accuracy=score,
        style_consistency=score,
        technical_quality=score,
        narrative_fit=score,
        issues=[],
        suggestions=[],
        passed=score >= 75.0,
        threshold=75.0,
    )


def _scene_result(scene_id="scene_1", qa_score=85.0, cost=0.50) -> SceneResult:
    return SceneResult(
        scene_id=scene_id,
        description=f"Desc {scene_id}",
        video_url=f"https://mock/{scene_id}.mp4",
        qa_score=qa_score,
        generation_cost=cost,
    )


def _pilot_strategy(
    pilot_id="pilot_a",
    tier=ProductionTier.ANIMATED,
    budget=10.0,
    test_scenes=2,
    full_scenes=5,
) -> PilotStrategy:
    return PilotStrategy(
        pilot_id=pilot_id,
        tier=tier,
        allocated_budget=budget,
        test_scene_count=test_scenes,
        full_scene_count=full_scenes,
        rationale="Test pilot",
    )


def _pilot_results(
    pilot_id="pilot_a",
    approved=True,
    score=80.0,
    budget_remaining=5.0,
    total_cost=5.0,
    num_scenes=2,
) -> PilotResults:
    scenes = [_scene_result(f"scene_{i+1}", qa_score=score) for i in range(num_scenes)]
    return PilotResults(
        pilot_id=pilot_id,
        tier="ANIMATED",
        scenes_generated=scenes,
        critic_score=score,
        approved=approved,
        budget_remaining=budget_remaining,
        total_cost=total_cost,
        avg_qa_score=score,
    )


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def orchestrator():
    """StudioOrchestrator in mock mode with all agents mocked."""
    with patch("core.orchestrator.ClaudeClient"):
        orch = StudioOrchestrator(num_variations=1, mock_mode=True)

    # Replace all agents with mocks
    orch.producer = MagicMock()
    orch.script_writer = MagicMock()
    orch.video_generator = MagicMock()
    orch.qa_verifier = MagicMock()
    orch.critic = MagicMock()

    return orch


# ============================================================
# ProductionResult Dataclass
# ============================================================

class TestProductionResult:
    """Tests for the ProductionResult dataclass."""

    def test_success_result(self):
        result = ProductionResult(
            status="success",
            best_pilot=_pilot_results(),
            all_pilots=[_pilot_results()],
            budget_used=5.0,
            budget_remaining=5.0,
            total_scenes=2,
        )
        assert result.status == "success"
        assert result.best_pilot is not None
        assert result.budget_used + result.budget_remaining == 10.0

    def test_failed_result(self):
        result = ProductionResult(
            status="failed",
            best_pilot=None,
            all_pilots=[],
            budget_used=2.0,
            budget_remaining=8.0,
            total_scenes=0,
        )
        assert result.status == "failed"
        assert result.best_pilot is None
        assert result.total_scenes == 0

    def test_partial_result(self):
        result = ProductionResult(
            status="partial",
            best_pilot=_pilot_results(num_scenes=1),
            all_pilots=[_pilot_results(num_scenes=1)],
            budget_used=9.0,
            budget_remaining=1.0,
            total_scenes=1,
        )
        assert result.status == "partial"
        assert result.total_scenes == 1


# ============================================================
# StudioOrchestrator Initialization
# ============================================================

class TestOrchestratorInit:
    """Tests for StudioOrchestrator construction."""

    def test_mock_mode_creates_mock_provider(self):
        with patch("core.orchestrator.ClaudeClient"):
            orch = StudioOrchestrator(mock_mode=True)
        assert orch.mock_mode is True

    def test_live_mode_requires_provider(self):
        with patch("core.orchestrator.ClaudeClient"):
            with pytest.raises(ValueError, match="video_provider required"):
                StudioOrchestrator(mock_mode=False)

    def test_live_mode_with_provider(self):
        mock_provider = MagicMock()
        with patch("core.orchestrator.ClaudeClient"):
            orch = StudioOrchestrator(mock_mode=False, video_provider=mock_provider)
        assert orch.mock_mode is False

    def test_num_variations_stored(self):
        with patch("core.orchestrator.ClaudeClient"):
            orch = StudioOrchestrator(num_variations=5, mock_mode=True)
        assert orch.num_variations == 5

    def test_debug_stored(self):
        with patch("core.orchestrator.ClaudeClient"):
            orch = StudioOrchestrator(debug=True, mock_mode=True)
        assert orch.debug is True


# ============================================================
# Full Pipeline: produce_video
# ============================================================

class TestProduceVideoPipeline:
    """Tests for the full produce_video pipeline with mocked agents."""

    @pytest.mark.asyncio
    async def test_success_pipeline(self, orchestrator):
        """Happy path: 1 pilot planned → approved → completed → selected."""
        pilot = _pilot_strategy()
        scenes = [_scene("s1"), _scene("s2")]
        videos = [_video("s1"), _video("s2")]
        qa = [_qa("s1", 90.0), _qa("s2", 85.0)]
        evaluation = _pilot_results(approved=True, budget_remaining=5.0)

        # Wire up mocks
        orchestrator.producer.analyze_and_plan = AsyncMock(return_value=[pilot])
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=3.0)
        orchestrator.script_writer.create_script = AsyncMock(return_value=scenes)
        orchestrator.video_generator.generate_scene = AsyncMock(side_effect=[
            [_video("s1")], [_video("s2")],  # test phase
            [_video("s3")], [_video("s4")], [_video("s5")],  # completion phase
        ])
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa(score=85.0)])
        orchestrator.critic.evaluate_pilot = AsyncMock(return_value=evaluation)
        orchestrator.critic.compare_pilots = MagicMock(return_value=evaluation)

        result = await orchestrator.produce_video("test concept", total_budget=20.0)

        assert result.status == "success"
        assert result.best_pilot is not None
        orchestrator.producer.analyze_and_plan.assert_awaited_once()
        orchestrator.critic.evaluate_pilot.assert_awaited_once()
        orchestrator.critic.compare_pilots.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_pilots_approved(self, orchestrator):
        """When critic rejects all pilots, result is 'failed'."""
        pilot = _pilot_strategy()
        scenes = [_scene()]
        rejected = _pilot_results(approved=False, budget_remaining=0.0)

        orchestrator.producer.analyze_and_plan = AsyncMock(return_value=[pilot])
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=3.0)
        orchestrator.script_writer.create_script = AsyncMock(return_value=scenes)
        orchestrator.video_generator.generate_scene = AsyncMock(return_value=[_video()])
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa(score=40.0)])
        orchestrator.critic.evaluate_pilot = AsyncMock(return_value=rejected)

        result = await orchestrator.produce_video("bad concept", total_budget=10.0)

        assert result.status == "failed"
        assert result.best_pilot is None

    @pytest.mark.asyncio
    async def test_multiple_pilots_parallel(self, orchestrator):
        """Multiple pilots run in parallel; best is selected."""
        pilot_a = _pilot_strategy("pilot_a", budget=8.0)
        pilot_b = _pilot_strategy("pilot_b", budget=8.0)
        eval_a = _pilot_results("pilot_a", approved=True, score=90.0, budget_remaining=3.0)
        eval_b = _pilot_results("pilot_b", approved=True, score=70.0, budget_remaining=3.0)

        orchestrator.producer.analyze_and_plan = AsyncMock(return_value=[pilot_a, pilot_b])
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=3.0)
        orchestrator.script_writer.create_script = AsyncMock(return_value=[_scene()])
        orchestrator.video_generator.generate_scene = AsyncMock(return_value=[_video()])
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa(score=80.0)])
        orchestrator.critic.evaluate_pilot = AsyncMock(side_effect=[eval_a, eval_b])
        orchestrator.critic.compare_pilots = MagicMock(return_value=eval_a)

        result = await orchestrator.produce_video("test", total_budget=20.0)

        assert result.status == "success"
        assert result.best_pilot.pilot_id == "pilot_a"
        # Both pilots were evaluated
        assert orchestrator.critic.evaluate_pilot.await_count == 2

    @pytest.mark.asyncio
    async def test_budget_exhausted_stops_continuation(self, orchestrator):
        """When budget is fully spent in test phase, continuation is skipped."""
        pilot = _pilot_strategy(budget=1.0, test_scenes=2, full_scenes=5)
        # Evaluation says approved but budget tracker will have $0 left
        eval_result = _pilot_results(approved=True, budget_remaining=0.5, total_cost=1.0)

        orchestrator.producer.analyze_and_plan = AsyncMock(return_value=[pilot])
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=1.0)
        orchestrator.script_writer.create_script = AsyncMock(return_value=[_scene()])
        orchestrator.video_generator.generate_scene = AsyncMock(return_value=[_video(cost=0.5)])
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa(score=80.0)])
        orchestrator.critic.evaluate_pilot = AsyncMock(return_value=eval_result)
        orchestrator.critic.compare_pilots = MagicMock(return_value=eval_result)

        result = await orchestrator.produce_video("test", total_budget=1.0)

        # Should still produce a result (using test scenes as final)
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_zero_budget_approved_but_no_remaining(self, orchestrator):
        """Approved pilot with 0 budget_remaining skips continuation."""
        pilot = _pilot_strategy(budget=5.0)
        eval_result = _pilot_results(approved=True, budget_remaining=0.0, total_cost=5.0)

        orchestrator.producer.analyze_and_plan = AsyncMock(return_value=[pilot])
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=5.0)
        orchestrator.script_writer.create_script = AsyncMock(return_value=[_scene()])
        orchestrator.video_generator.generate_scene = AsyncMock(return_value=[_video()])
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa()])
        orchestrator.critic.evaluate_pilot = AsyncMock(return_value=eval_result)
        orchestrator.critic.compare_pilots = MagicMock(return_value=eval_result)

        result = await orchestrator.produce_video("test", total_budget=5.0)

        # Approved but 0 remaining = not in approved_pilots list
        assert result.status == "failed"


# ============================================================
# _run_pilot_test
# ============================================================

class TestRunPilotTest:
    """Tests for the _run_pilot_test method."""

    @pytest.mark.asyncio
    async def test_basic_pilot_test(self, orchestrator):
        """Generates script, videos, QA for test scenes."""
        pilot = _pilot_strategy(test_scenes=2)
        tracker = BudgetTracker(20.0)
        scenes = [_scene("s1"), _scene("s2")]

        orchestrator.script_writer.create_script = AsyncMock(return_value=scenes)
        orchestrator.video_generator.generate_scene = AsyncMock(
            side_effect=[[_video("s1", cost=1.0)], [_video("s2", cost=1.0)]]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            side_effect=[[_qa("s1", 90.0)], [_qa("s2", 85.0)]]
        )

        result = await orchestrator._run_pilot_test("concept", pilot, tracker)

        assert result["pilot_id"] == "pilot_a"
        assert len(result["scenes"]) == 2
        assert result["budget_spent"] == 2.0

    @pytest.mark.asyncio
    async def test_budget_exhaustion_mid_test(self, orchestrator):
        """Stops generating when pilot budget is exhausted."""
        pilot = _pilot_strategy(budget=0.50, test_scenes=3)
        tracker = BudgetTracker(1.0)
        scenes = [_scene("s1"), _scene("s2"), _scene("s3")]

        orchestrator.script_writer.create_script = AsyncMock(return_value=scenes)
        orchestrator.video_generator.generate_scene = AsyncMock(
            return_value=[_video(cost=0.60)]  # One scene costs more than budget
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(return_value=[_qa()])

        result = await orchestrator._run_pilot_test("concept", pilot, tracker)

        # First scene costs $0.60 > $0.50 budget — so budget check kicks in
        # after first scene (remaining = 0.50 - 0.60 = -0.10 ≤ 0)
        assert len(result["scenes"]) <= 2

    @pytest.mark.asyncio
    async def test_no_videos_generated(self, orchestrator):
        """Handles case where video generation returns empty list."""
        pilot = _pilot_strategy(test_scenes=2)
        tracker = BudgetTracker(20.0)
        scenes = [_scene("s1"), _scene("s2")]

        orchestrator.script_writer.create_script = AsyncMock(return_value=scenes)
        orchestrator.video_generator.generate_scene = AsyncMock(return_value=[])
        orchestrator.qa_verifier.verify_batch = AsyncMock()

        result = await orchestrator._run_pilot_test("concept", pilot, tracker)

        assert len(result["scenes"]) == 0
        assert result["budget_spent"] == 0
        # QA should not be called when no videos
        orchestrator.qa_verifier.verify_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_selects_best_qa_variation(self, orchestrator):
        """When multiple variations, picks the one with highest QA."""
        pilot = _pilot_strategy(test_scenes=1)
        tracker = BudgetTracker(20.0)

        orchestrator.script_writer.create_script = AsyncMock(return_value=[_scene()])
        orchestrator.video_generator.generate_scene = AsyncMock(
            return_value=[_video("s1", 0, cost=0.5), _video("s1", 1, cost=0.5)]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            return_value=[_qa("s1", 60.0), _qa("s1", 95.0)]
        )

        result = await orchestrator._run_pilot_test("concept", pilot, tracker)

        assert len(result["scenes"]) == 1
        # Best QA is variation 1 with score 95.0
        assert result["scenes"][0].qa_score == 95.0
        assert result["scenes"][0].video_url == "https://mock/s1_v1.mp4"


# ============================================================
# _complete_pilot
# ============================================================

class TestCompletePilot:
    """Tests for the _complete_pilot method."""

    @pytest.mark.asyncio
    async def test_generates_remaining_scenes(self, orchestrator):
        """Completes production for remaining scenes after test phase."""
        pilot = _pilot_strategy(test_scenes=2, full_scenes=4)
        eval_result = _pilot_results(num_scenes=2, total_cost=2.0)
        tracker = BudgetTracker(20.0)

        orchestrator.script_writer.create_script = AsyncMock(
            return_value=[_scene("s3"), _scene("s4")]
        )
        orchestrator.video_generator.generate_scene = AsyncMock(
            side_effect=[[_video("s3", cost=1.0)], [_video("s4", cost=1.0)]]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            side_effect=[[_qa("s3", 88.0)], [_qa("s4", 82.0)]]
        )

        result = await orchestrator._complete_pilot(
            "concept", pilot, eval_result, tracker, max_budget=10.0
        )

        # Should now have 4 scenes total (2 test + 2 completion)
        assert len(result.scenes_generated) == 4
        assert result.total_cost > 2.0

    @pytest.mark.asyncio
    async def test_no_remaining_scenes(self, orchestrator):
        """If test_scene_count == full_scene_count, returns evaluation as-is."""
        pilot = _pilot_strategy(test_scenes=3, full_scenes=3)
        eval_result = _pilot_results(num_scenes=3)
        tracker = BudgetTracker(20.0)

        result = await orchestrator._complete_pilot(
            "concept", pilot, eval_result, tracker, max_budget=10.0
        )

        assert result is eval_result  # Returned unchanged

    @pytest.mark.asyncio
    async def test_budget_exhaustion_during_completion(self, orchestrator):
        """Stops generating when continuation budget runs out."""
        pilot = _pilot_strategy(test_scenes=1, full_scenes=5)
        eval_result = _pilot_results(num_scenes=1, total_cost=1.0)
        tracker = BudgetTracker(20.0)

        # 4 remaining scenes but only $1 budget
        orchestrator.script_writer.create_script = AsyncMock(
            return_value=[_scene(f"s{i}") for i in range(2, 6)]
        )
        orchestrator.video_generator.generate_scene = AsyncMock(
            return_value=[_video(cost=0.80)]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            return_value=[_qa(score=80.0)]
        )

        result = await orchestrator._complete_pilot(
            "concept", pilot, eval_result, tracker, max_budget=1.0
        )

        # Should stop before all 4 remaining scenes due to budget
        assert len(result.scenes_generated) < 5

    @pytest.mark.asyncio
    async def test_updates_avg_qa_score(self, orchestrator):
        """Avg QA score is recalculated including new scenes."""
        pilot = _pilot_strategy(test_scenes=1, full_scenes=2)
        eval_result = _pilot_results(num_scenes=1, total_cost=1.0)
        # Set initial QA to 60
        eval_result.scenes_generated[0] = _scene_result("s1", qa_score=60.0)
        eval_result.avg_qa_score = 60.0
        tracker = BudgetTracker(20.0)

        orchestrator.script_writer.create_script = AsyncMock(
            return_value=[_scene("s2")]
        )
        orchestrator.video_generator.generate_scene = AsyncMock(
            return_value=[_video("s2", cost=1.0)]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            return_value=[_qa("s2", 100.0)]
        )

        result = await orchestrator._complete_pilot(
            "concept", pilot, eval_result, tracker, max_budget=5.0
        )

        # Average of 60 and 100 = 80
        assert result.avg_qa_score == 80.0

    @pytest.mark.asyncio
    async def test_empty_videos_skipped(self, orchestrator):
        """Scenes that produce no videos are skipped without error."""
        pilot = _pilot_strategy(test_scenes=1, full_scenes=3)
        eval_result = _pilot_results(num_scenes=1, total_cost=1.0)
        tracker = BudgetTracker(20.0)

        orchestrator.script_writer.create_script = AsyncMock(
            return_value=[_scene("s2"), _scene("s3")]
        )
        # First scene generates nothing, second succeeds
        orchestrator.video_generator.generate_scene = AsyncMock(
            side_effect=[[], [_video("s3", cost=1.0)]]
        )
        orchestrator.qa_verifier.verify_batch = AsyncMock(
            return_value=[_qa("s3", 90.0)]
        )

        result = await orchestrator._complete_pilot(
            "concept", pilot, eval_result, tracker, max_budget=5.0
        )

        # 1 original + 1 new (the other was empty)
        assert len(result.scenes_generated) == 2


# ============================================================
# BudgetTracker Integration
# ============================================================

class TestBudgetTrackerIntegration:
    """Verify budget enforcement works correctly with the orchestrator."""

    def test_basic_tracking(self):
        tracker = BudgetTracker(10.0)
        tracker.record_spend("pilot_a", 3.0)
        tracker.record_spend("pilot_b", 4.0)

        assert tracker.get_total_spent() == 7.0
        assert tracker.get_remaining_budget() == 3.0

    def test_pilot_specific_tracking(self):
        tracker = BudgetTracker(20.0)
        tracker.record_spend("pilot_a", 5.0)
        tracker.record_spend("pilot_a", 3.0)

        assert tracker.get_pilot_spent("pilot_a") == 8.0
        assert tracker.get_pilot_spent("pilot_b") == 0.0

    def test_overhead_tracking(self):
        tracker = BudgetTracker(10.0)
        tracker.record_spend("pilot_a", 5.0)
        tracker.record_overhead(1.0, "Claude API")

        assert tracker.get_total_spent() == 6.0
        assert tracker.get_remaining_budget() == 4.0

    def test_overspend_goes_negative(self):
        tracker = BudgetTracker(5.0)
        tracker.record_spend("pilot_a", 6.0)

        assert tracker.get_remaining_budget() == -1.0

    def test_zero_budget(self):
        tracker = BudgetTracker(0.0)
        assert tracker.get_remaining_budget() == 0.0


# ============================================================
# Agent Call Order Verification
# ============================================================

class TestAgentCallOrder:
    """Verify agents are called in the correct sequence."""

    @pytest.mark.asyncio
    async def test_stage_order(self, orchestrator):
        """Verify: plan → script → generate → QA → critic → compare."""
        call_order = []

        async def mock_plan(*a, **kw):
            call_order.append("plan")
            return [_pilot_strategy()]

        async def mock_script(*a, **kw):
            call_order.append("script")
            return [_scene()]

        async def mock_generate(*a, **kw):
            call_order.append("generate")
            return [_video()]

        async def mock_qa(*a, **kw):
            call_order.append("qa")
            return [_qa()]

        async def mock_evaluate(*a, **kw):
            call_order.append("evaluate")
            return _pilot_results(approved=True, budget_remaining=5.0)

        def mock_compare(*a, **kw):
            call_order.append("compare")
            return _pilot_results()

        orchestrator.producer.analyze_and_plan = mock_plan
        orchestrator.producer.estimate_pilot_cost = MagicMock(return_value=2.0)
        orchestrator.script_writer.create_script = mock_script
        orchestrator.video_generator.generate_scene = mock_generate
        orchestrator.qa_verifier.verify_batch = mock_qa
        orchestrator.critic.evaluate_pilot = mock_evaluate
        orchestrator.critic.compare_pilots = mock_compare

        await orchestrator.produce_video("test", 20.0)

        # Plan must come first, compare must come last
        assert call_order[0] == "plan"
        assert call_order[-1] == "compare"
        # Script must come before generate
        assert call_order.index("script") < call_order.index("generate")
        # Generate must come before QA
        assert call_order.index("generate") < call_order.index("qa")
        # QA must come before evaluate
        assert call_order.index("qa") < call_order.index("evaluate")
