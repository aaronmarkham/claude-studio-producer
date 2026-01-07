"""
Main Orchestrator - Runs the full multi-pilot video production pipeline
Producer → ScriptWriter → VideoGenerator → QA → Critic → Winner Continues
"""

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass

from .claude_client import ClaudeClient
from .budget import BudgetTracker, ProductionTier
from agents.producer import ProducerAgent, PilotStrategy
from agents.critic import CriticAgent, SceneResult, PilotResults
from agents.script_writer import ScriptWriterAgent, Scene
from agents.video_generator import VideoGeneratorAgent, GeneratedVideo
from agents.qa_verifier import QAVerifierAgent, QAResult


@dataclass
class ProductionResult:
    """Final result from the production pipeline"""
    status: str  # "success", "partial", "failed"
    best_pilot: Optional[PilotResults]
    all_pilots: List[PilotResults]
    budget_used: float
    budget_remaining: float
    total_scenes: int


class StudioOrchestrator:
    """
    Full production orchestrator with Producer + Pilots + Critic workflow
    """
    
    def __init__(self, num_variations: int = 3, debug: bool = False, mock_mode: bool = True):
        """
        Args:
            num_variations: Number of video variations per scene
            debug: Enable debug output
            mock_mode: Use mock generation/QA (True for testing without API keys)
        """
        self.num_variations = num_variations
        self.debug = debug
        self.mock_mode = mock_mode

        # Shared Claude client
        self.claude = ClaudeClient(debug=debug)

        # Agents
        self.producer = ProducerAgent(claude_client=self.claude)
        self.critic = CriticAgent(claude_client=self.claude)
        self.script_writer = ScriptWriterAgent(claude_client=self.claude)
        self.video_generator = VideoGeneratorAgent(
            num_variations=num_variations,
            mock_mode=mock_mode
        )
        self.qa_verifier = QAVerifierAgent(
            claude_client=self.claude,
            mock_mode=mock_mode
        )
        
    async def produce_video(
        self,
        user_request: str,
        total_budget: float
    ) -> ProductionResult:
        """
        Full production pipeline:
        1. Producer plans pilots
        2. Run pilots in parallel (test scenes only)
        3. Critic evaluates each pilot
        4. Continue approved pilots to completion
        5. Return best result
        
        Args:
            user_request: Description of video to create
            total_budget: Total budget available
            
        Returns:
            ProductionResult with final video and metadata
        """
        
        print(f"\n{'='*60}")
        print(f"🎬 CLAUDE STUDIO PRODUCER")
        print(f"Budget: ${total_budget}")
        print(f"{'='*60}\n")
        
        budget_tracker = BudgetTracker(total_budget)
        
        # Stage 1: Producer Planning
        print("📋 Stage 1: Producer analyzing request and planning pilots...")
        pilots = await self.producer.analyze_and_plan(user_request, total_budget)
        
        print(f"\n   Planned {len(pilots)} pilots:")
        for pilot in pilots:
            est_cost = self.producer.estimate_pilot_cost(pilot, self.num_variations)
            print(f"   • {pilot.pilot_id}: {pilot.tier.value}")
            print(f"     Budget: ${pilot.allocated_budget}, Est. test: ~${est_cost}")
        
        # Stage 2: Parallel Pilot Test Execution
        print(f"\n🎥 Stage 2: Running {len(pilots)} pilots in parallel (test scenes)...")
        
        pilot_tasks = []
        for pilot in pilots:
            task = self._run_pilot_test(user_request, pilot, budget_tracker)
            pilot_tasks.append(task)
        
        test_results = await asyncio.gather(*pilot_tasks)
        
        # Stage 3: Critic Evaluation
        print(f"\n🔍 Stage 3: Critic evaluating pilot results...")
        
        evaluations = []
        for i, test_result in enumerate(test_results):
            print(f"\n   Evaluating {test_result['pilot_id']}...")
            
            evaluation = await self.critic.evaluate_pilot(
                original_request=user_request,
                pilot=pilots[i],
                scene_results=test_result['scenes'],
                budget_spent=test_result['budget_spent'],
                budget_allocated=pilots[i].allocated_budget
            )
            evaluations.append(evaluation)
            
            status = "✅ APPROVED" if evaluation.approved else "❌ CANCELLED"
            print(f"   {status} - Score: {evaluation.critic_score}/100")
            if evaluation.approved:
                print(f"   Budget continuation: ${evaluation.budget_remaining:.2f}")
            
            budget_tracker.record_spend(
                pilot_id=test_result['pilot_id'],
                amount=test_result['budget_spent']
            )
        
        # Stage 4: Continue Approved Pilots (with budget enforcement)
        approved_pilots = [
            (pilots[i], evaluations[i])
            for i in range(len(pilots))
            if evaluations[i].approved and evaluations[i].budget_remaining > 0
        ]
        
        if not approved_pilots:
            print("\n❌ No pilots approved or sufficient budget. Production stopped.")
            return ProductionResult(
                status="failed",
                best_pilot=None,
                all_pilots=evaluations,
                budget_used=budget_tracker.get_total_spent(),
                budget_remaining=budget_tracker.get_remaining_budget(),
                total_scenes=0
            )
        
        print(f"\n✅ Stage 4: {len(approved_pilots)} pilot(s) approved, continuing to full production...")
        
        final_results = []
        for pilot, evaluation in approved_pilots:
            remaining_budget = budget_tracker.get_remaining_budget()
            
            if remaining_budget <= 0:
                print(f"\n   ⚠️  No budget remaining, stopping {pilot.pilot_id}")
                # Use test results as final
                final_results.append(evaluation)
                continue
            
            # Cap continuation budget to what's actually available
            continuation_budget = min(evaluation.budget_remaining, remaining_budget)
            
            print(f"\n   Completing {pilot.pilot_id} with ${continuation_budget:.2f}...")
            
            # Complete production within budget
            full_result = await self._complete_pilot(
                user_request=user_request,
                pilot=pilot,
                evaluation=evaluation,
                budget_tracker=budget_tracker,
                max_budget=continuation_budget
            )
            final_results.append(full_result)
        
        # Stage 5: Select Best Pilot
        best_pilot = self.critic.compare_pilots(final_results)
        
        if best_pilot:
            print(f"\n🎬 Stage 5: Best pilot selected: {best_pilot.pilot_id}")
            print(f"   Score: {best_pilot.critic_score}/100")
            print(f"   Total cost: ${best_pilot.total_cost:.2f}")
        
        budget_tracker.print_status()
        
        print(f"{'='*60}")
        print(f"✅ PRODUCTION COMPLETE")
        print(f"{'='*60}\n")
        
        return ProductionResult(
            status="success",
            best_pilot=best_pilot,
            all_pilots=final_results,
            budget_used=budget_tracker.get_total_spent(),
            budget_remaining=budget_tracker.get_remaining_budget(),
            total_scenes=len(best_pilot.scenes_generated) if best_pilot else 0
        )
    
    async def _run_pilot_test(
        self,
        user_request: str,
        pilot: PilotStrategy,
        budget_tracker: BudgetTracker
    ) -> Dict:
        """
        Run a pilot's test phase using real agents:
        1. ScriptWriter creates scenes
        2. VideoGenerator generates videos
        3. QAVerifier scores quality
        """

        # Step 1: Generate script for test scenes
        # Create a focused request for just the test scenes
        test_duration = pilot.test_scene_count * 5.0  # Assume 5s per scene

        scenes = await self.script_writer.create_script(
            video_concept=user_request,
            target_duration=test_duration,
            production_tier=pilot.tier,
            num_scenes=pilot.test_scene_count
        )

        if self.debug:
            print(f"      Generated {len(scenes)} scenes for {pilot.pilot_id}")

        # Step 2 & 3: For each scene, generate video and run QA
        test_scenes = []
        total_cost = 0

        for scene in scenes:
            # Budget check before generating
            remaining = pilot.allocated_budget - total_cost
            if remaining <= 0:
                print(f"      Budget exhausted after {len(test_scenes)} scenes")
                break

            # Generate video variations
            videos = await self.video_generator.generate_scene(
                scene=scene,
                production_tier=pilot.tier,
                budget_limit=remaining,
                num_variations=self.num_variations
            )

            if not videos:
                if self.debug:
                    print(f"      No videos generated for {scene.scene_id}")
                continue

            # Run QA on all variations
            qa_results = await self.qa_verifier.verify_batch(
                scenes=[scene] * len(videos),
                videos=videos,
                original_request=user_request,
                production_tier=pilot.tier
            )

            # Select best variation based on QA score
            best_idx = max(range(len(qa_results)), key=lambda i: qa_results[i].overall_score)
            best_video = videos[best_idx]
            best_qa = qa_results[best_idx]

            # Track total cost (all variations + QA)
            generation_cost = sum(v.generation_cost for v in videos)
            scene_total_cost = generation_cost

            # Create SceneResult for Critic
            scene_result = SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=best_video.video_url,
                qa_score=best_qa.overall_score,
                generation_cost=scene_total_cost
            )

            test_scenes.append(scene_result)
            total_cost += scene_total_cost

            if self.debug:
                print(f"      {scene.scene_id}: QA {best_qa.overall_score:.1f}/100, Cost ${scene_total_cost:.2f}")

        return {
            "pilot_id": pilot.pilot_id,
            "scenes": test_scenes,
            "budget_spent": total_cost
        }
    
    async def _complete_pilot(
        self,
        user_request: str,
        pilot: PilotStrategy,
        evaluation: PilotResults,
        budget_tracker: BudgetTracker,
        max_budget: float
    ) -> PilotResults:
        """
        Complete full production for approved pilot using real agents
        Respects max_budget constraint
        """

        # Calculate remaining scenes to generate
        remaining_scenes = pilot.full_scene_count - pilot.test_scene_count

        if remaining_scenes <= 0:
            return evaluation

        # Generate script for remaining scenes
        remaining_duration = remaining_scenes * 5.0
        scenes = await self.script_writer.create_script(
            video_concept=user_request,
            target_duration=remaining_duration,
            production_tier=pilot.tier,
            num_scenes=remaining_scenes
        )

        all_scenes = list(evaluation.scenes_generated)
        additional_cost = 0

        for scene in scenes:
            # Budget check
            remaining_budget = max_budget - additional_cost
            if remaining_budget <= 0:
                print(f"      ⚠️  Budget exhausted after {len(all_scenes) - pilot.test_scene_count} additional scenes")
                break

            # Generate videos
            videos = await self.video_generator.generate_scene(
                scene=scene,
                production_tier=pilot.tier,
                budget_limit=remaining_budget,
                num_variations=self.num_variations
            )

            if not videos:
                continue

            # Run QA
            qa_results = await self.qa_verifier.verify_batch(
                scenes=[scene] * len(videos),
                videos=videos,
                original_request=user_request,
                production_tier=pilot.tier
            )

            # Select best variation
            best_idx = max(range(len(qa_results)), key=lambda i: qa_results[i].overall_score)
            best_video = videos[best_idx]
            best_qa = qa_results[best_idx]

            # Track costs
            generation_cost = sum(v.generation_cost for v in videos)
            scene_total_cost = generation_cost

            scene_result = SceneResult(
                scene_id=scene.scene_id,
                description=scene.description,
                video_url=best_video.video_url,
                qa_score=best_qa.overall_score,
                generation_cost=scene_total_cost
            )

            all_scenes.append(scene_result)
            additional_cost += scene_total_cost

        budget_tracker.record_spend(pilot.pilot_id, additional_cost)

        # Update evaluation with complete results
        evaluation.scenes_generated = all_scenes
        evaluation.total_cost += additional_cost
        evaluation.avg_qa_score = sum(s.qa_score for s in all_scenes) / len(all_scenes)

        return evaluation
