"""
Studio Orchestrator - Multi-agent production pipeline

Orchestrates the full video production workflow using Strands-enabled agents:
1. Producer analyzes and creates pilot strategies
2. Pilots execute in parallel (test scenes)
3. Critic evaluates pilots
4. Approved pilots continue production
5. Editor creates final cuts

Uses native asyncio.gather for parallel execution with Strands agents.
"""

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass

from agents.producer import ProducerAgent, PilotStrategy
from agents.critic import CriticAgent, PilotResults, SceneResult
from agents.script_writer import ScriptWriterAgent, Scene
from agents.video_generator import VideoGeneratorAgent, GeneratedVideo
from agents.audio_generator import AudioGeneratorAgent
from agents.qa_verifier import QAVerifierAgent, QAResult
from agents.editor import EditorAgent, EditDecisionList
from core.budget import BudgetTracker, ProductionTier


@dataclass
class ProductionResult:
    """Result of full production pipeline"""
    status: str  # "success" or "failed"
    best_pilot: Optional[PilotResults]
    all_pilots: List[PilotResults]
    budget_used: float
    budget_remaining: float
    total_scenes: int
    edit_decision_list: Optional[EditDecisionList] = None


class StudioOrchestrator:
    """
    Main production orchestrator using Strands agents.

    Coordinates all agents through the production pipeline, executing
    pilots in parallel and selecting the best result.
    """

    def __init__(
        self,
        num_variations: int = 3,
        max_concurrent_pilots: int = 3,
        debug: bool = False
    ):
        """
        Initialize orchestrator with agent instances.

        Args:
            num_variations: Number of video variations per scene
            max_concurrent_pilots: Maximum pilots to run in parallel
            debug: Enable debug output
        """
        self.num_variations = num_variations
        self.max_concurrent_pilots = max_concurrent_pilots
        self.debug = debug

        # Initialize all Strands-enabled agents
        self.producer = ProducerAgent()
        self.critic = CriticAgent()
        self.script_writer = ScriptWriterAgent()
        self.video_generator = VideoGeneratorAgent(num_variations=num_variations)
        self.audio_generator = AudioGeneratorAgent()
        self.qa_verifier = QAVerifierAgent(mock_mode=True)
        self.editor = EditorAgent()

    async def run(
        self,
        user_request: str,
        total_budget: float
    ) -> ProductionResult:
        """
        Execute full production pipeline.

        Args:
            user_request: User's video concept/requirements
            total_budget: Total production budget

        Returns:
            ProductionResult with status and outputs
        """
        budget_tracker = BudgetTracker(total_budget)

        # Stage 1: Producer planning (sequential)
        print(f"\n[Stage 1] Producer analyzing request and planning pilots...")
        pilots = await self.producer.analyze_and_plan(user_request, total_budget)

        if not pilots:
            return self._failed_result(budget_tracker, "No pilot strategies generated")

        print(f"   Generated {len(pilots)} pilot strategies")
        for pilot in pilots:
            print(f"   - {pilot.pilot_id}: {pilot.tier.value} tier, ${pilot.allocated_budget:.2f}")

        # Stage 2: Run pilot tests in parallel
        print(f"\n[Stage 2] Running {len(pilots)} pilot tests in parallel...")
        test_results = await self._run_pilots_parallel(
            user_request=user_request,
            pilots=pilots,
            budget_tracker=budget_tracker
        )

        if not test_results:
            return self._failed_result(budget_tracker, "All pilots failed during testing")

        # Stage 3: Critic evaluates pilots in parallel
        print(f"\n[Stage 3] Critic evaluating {len(test_results)} pilots...")
        evaluations = await self._evaluate_pilots_parallel(
            user_request=user_request,
            pilots=pilots,
            test_results=test_results,
            budget_tracker=budget_tracker
        )

        approved = [eval for eval in evaluations if eval.approved]

        if not approved:
            print(f"   [X] No pilots approved (all below quality threshold)")
            return ProductionResult(
                status="failed",
                best_pilot=None,
                all_pilots=evaluations,
                budget_used=budget_tracker.get_total_spent(),
                budget_remaining=budget_tracker.get_remaining_budget(),
                total_scenes=0
            )

        print(f"   [OK] {len(approved)} pilots approved")
        for eval in approved:
            print(f"   - {eval.pilot_id}: critic_score={eval.critic_score}, qa={eval.avg_qa_score:.1f}")

        # Stage 4: Select best pilot
        best = self.critic.compare_pilots(evaluations)

        if not best:
            return self._failed_result(budget_tracker, "Failed to select best pilot")

        print(f"\n[WINNER] Best pilot selected: {best.pilot_id} ({best.tier})")

        return ProductionResult(
            status="success",
            best_pilot=best,
            all_pilots=evaluations,
            budget_used=budget_tracker.get_total_spent(),
            budget_remaining=budget_tracker.get_remaining_budget(),
            total_scenes=len(best.scenes_generated)
        )

    async def _run_pilots_parallel(
        self,
        user_request: str,
        pilots: List[PilotStrategy],
        budget_tracker: BudgetTracker
    ) -> List[Dict]:
        """
        Run pilot test phases in parallel using asyncio.gather.

        Returns list of successful pilot test results.
        """

        async def run_single_pilot(pilot: PilotStrategy) -> Optional[Dict]:
            """Execute a single pilot's test phase"""
            try:
                print(f"   [START] Starting pilot: {pilot.pilot_id}")

                # Generate script for test scenes
                scenes = await self.script_writer.create_script(
                    video_concept=user_request,
                    target_duration=60,
                    production_tier=pilot.tier,
                    num_scenes=pilot.test_scene_count
                )

                if not scenes:
                    print(f"   ⚠️  {pilot.pilot_id}: No scenes generated")
                    return None

                # Generate videos for test scenes
                test_budget = pilot.allocated_budget * 0.3  # 30% for testing
                all_videos = []

                for scene in scenes:
                    videos = await self.video_generator.generate_scene(
                        scene=scene,
                        production_tier=pilot.tier,
                        budget_limit=test_budget / len(scenes),
                        num_variations=min(2, self.num_variations)  # Fewer variations for test
                    )
                    all_videos.extend(videos)

                # Run QA on all videos
                qa_results = []
                for i, video in enumerate(all_videos):
                    scene = scenes[i // min(2, self.num_variations)]
                    qa = await self.qa_verifier.verify_video(
                        scene=scene,
                        generated_video=video,
                        original_request=user_request,
                        production_tier=pilot.tier
                    )
                    qa_results.append(qa)

                # Calculate cost
                total_cost = sum(v.generation_cost for v in all_videos)
                budget_tracker.record_spend(pilot.pilot_id, total_cost)

                print(f"   ✓ {pilot.pilot_id}: {len(all_videos)} videos, ${total_cost:.2f}")

                return {
                    "pilot_id": pilot.pilot_id,
                    "scenes": scenes,
                    "videos": all_videos,
                    "qa_results": qa_results,
                    "budget_spent": total_cost
                }

            except Exception as e:
                print(f"   [ERROR] {pilot.pilot_id} failed: {e}")
                if self.debug:
                    import traceback
                    traceback.print_exc()
                return None

        # Limit concurrency with semaphore
        semaphore = asyncio.Semaphore(self.max_concurrent_pilots)

        async def run_with_limit(pilot):
            async with semaphore:
                return await run_single_pilot(pilot)

        # Run all pilots in parallel with concurrency limit
        results = await asyncio.gather(
            *[run_with_limit(p) for p in pilots],
            return_exceptions=True
        )

        # Filter out None and exceptions
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"   ⚠️  Pilot exception: {result}")
            elif result is not None:
                valid_results.append(result)

        return valid_results

    async def _evaluate_pilots_parallel(
        self,
        user_request: str,
        pilots: List[PilotStrategy],
        test_results: List[Dict],
        budget_tracker: BudgetTracker
    ) -> List[PilotResults]:
        """Evaluate all pilots in parallel"""

        # Match results to pilots
        result_map = {r["pilot_id"]: r for r in test_results}

        async def evaluate_single(pilot: PilotStrategy) -> PilotResults:
            """Evaluate a single pilot"""
            result = result_map.get(pilot.pilot_id)

            if not result:
                return PilotResults(
                    pilot_id=pilot.pilot_id,
                    tier=pilot.tier.value,
                    scenes_generated=[],
                    total_cost=0,
                    avg_qa_score=0,
                    approved=False,
                    critic_reasoning="No test results available"
                )

            # Convert videos to SceneResult format for critic
            scene_results = []
            for i, video in enumerate(result["videos"]):
                qa = result["qa_results"][i] if i < len(result["qa_results"]) else None
                scene_results.append(SceneResult(
                    scene_id=video.scene_id,
                    description=result["scenes"][i // min(2, self.num_variations)].description,
                    video_url=video.video_url,
                    qa_score=qa.overall_score if qa else 0,
                    generation_cost=video.generation_cost
                ))

            return await self.critic.evaluate_pilot(
                original_request=user_request,
                pilot=pilot,
                scene_results=scene_results,
                budget_spent=result["budget_spent"],
                budget_allocated=pilot.allocated_budget
            )

        # Evaluate all in parallel
        evaluations = await asyncio.gather(
            *[evaluate_single(p) for p in pilots],
            return_exceptions=False
        )

        return evaluations

    def _failed_result(
        self,
        budget_tracker: BudgetTracker,
        reason: str
    ) -> ProductionResult:
        """Create a failed result"""
        print(f"   [ERROR] Production failed: {reason}")
        return ProductionResult(
            status="failed",
            best_pilot=None,
            all_pilots=[],
            budget_used=budget_tracker.get_total_spent(),
            budget_remaining=budget_tracker.get_remaining_budget(),
            total_scenes=0
        )
