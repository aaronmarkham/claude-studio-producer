"""
Main Orchestrator - Runs the full multi-pilot video production pipeline
Producer → Parallel Pilots → Critic → Winner Continues
"""

import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass

from .claude_client import ClaudeClient
from .producer import ProducerAgent, PilotStrategy
from .critic import CriticAgent, SceneResult, PilotResults
from .budget import BudgetTracker, ProductionTier


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
    
    def __init__(self, num_variations: int = 3, debug: bool = False):
        """
        Args:
            num_variations: Number of video variations per scene
            debug: Enable debug output
        """
        self.num_variations = num_variations
        self.debug = debug
        
        # Shared Claude client
        self.claude = ClaudeClient(debug=debug)
        
        # Agents
        self.producer = ProducerAgent(claude_client=self.claude)
        self.critic = CriticAgent(claude_client=self.claude)
        
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
        Run a pilot's test phase (limited scenes)
        In real implementation, this would call actual video generation APIs
        """
        
        # Simulate scene generation
        import random
        
        test_scenes = []
        total_cost = 0
        
        for i in range(pilot.test_scene_count):
            # Simulate scene generation cost
            from .budget import COST_MODELS
            cost_model = COST_MODELS[pilot.tier]
            scene_cost = 5.0 * cost_model.cost_per_second * self.num_variations
            
            # Simulate QA score (better tiers get higher scores on average)
            base_score = 70 + (cost_model.quality_ceiling - 70) * 0.3
            qa_score = base_score + random.uniform(-10, 15)
            qa_score = min(100, max(60, qa_score))
            
            scene = SceneResult(
                scene_id=f"{pilot.pilot_id}_scene_{i+1}",
                description=f"Test scene {i+1} for {pilot.pilot_id}",
                video_url=f"https://example.com/{pilot.pilot_id}/scene{i+1}.mp4",
                qa_score=qa_score,
                generation_cost=scene_cost
            )
            
            test_scenes.append(scene)
            total_cost += scene_cost
        
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
        Complete full production for approved pilot
        Respects max_budget constraint
        """
        
        # Calculate how many more scenes we can afford
        from .budget import COST_MODELS
        cost_model = COST_MODELS[pilot.tier]
        cost_per_scene = 5.0 * cost_model.cost_per_second * self.num_variations
        
        remaining_scenes = pilot.full_scene_count - pilot.test_scene_count
        affordable_scenes = int(max_budget / cost_per_scene)
        scenes_to_generate = min(remaining_scenes, affordable_scenes)
        
        if scenes_to_generate < remaining_scenes:
            print(f"      ⚠️  Budget limits: generating {scenes_to_generate}/{remaining_scenes} scenes")
        
        # Generate scenes
        import random
        
        all_scenes = list(evaluation.scenes_generated)
        additional_cost = 0
        
        for i in range(scenes_to_generate):
            scene_cost = cost_per_scene
            
            # Check if we still have budget
            if additional_cost + scene_cost > max_budget:
                print(f"      ⚠️  Budget exhausted after {i} scenes")
                break
            
            # Adjust QA scores based on critic feedback
            base_score = evaluation.avg_qa_score + random.uniform(-5, 10)
            qa_score = min(100, max(60, base_score))
            
            scene = SceneResult(
                scene_id=f"{pilot.pilot_id}_scene_{pilot.test_scene_count + i + 1}",
                description=f"Scene {pilot.test_scene_count + i + 1}",
                video_url=f"https://example.com/{pilot.pilot_id}/scene{pilot.test_scene_count + i + 1}.mp4",
                qa_score=qa_score,
                generation_cost=scene_cost
            )
            
            all_scenes.append(scene)
            additional_cost += scene_cost
        
        budget_tracker.record_spend(pilot.pilot_id, additional_cost)
        
        # Update evaluation with complete results
        evaluation.scenes_generated = all_scenes
        evaluation.total_cost += additional_cost
        evaluation.avg_qa_score = sum(s.qa_score for s in all_scenes) / len(all_scenes)
        
        return evaluation
