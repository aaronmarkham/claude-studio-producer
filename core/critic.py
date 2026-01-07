"""Critic Agent - Evaluates pilot results and makes budget decisions"""

from dataclasses import dataclass
from typing import List, Dict
from .producer import PilotStrategy
from .claude_client import ClaudeClient, JSONExtractor


@dataclass
class SceneResult:
    """Result from a generated scene"""
    scene_id: str
    description: str
    video_url: str
    qa_score: float  # 0-100
    generation_cost: float


@dataclass
class PilotResults:
    """Results from a pilot's test phase"""
    pilot_id: str
    tier: str
    scenes_generated: List[SceneResult]
    total_cost: float
    avg_qa_score: float
    
    # Critic's evaluation
    critic_score: float = 0  # Overall score 0-100
    approved: bool = False
    budget_remaining: float = 0
    gap_analysis: Dict = None
    critic_reasoning: str = ""
    adjustments_needed: List[str] = None


class CriticAgent:
    """
    Evaluates pilot results against original intent
    Makes budget continuation/cancellation decisions
    """
    
    def __init__(self, claude_client: ClaudeClient = None):
        self.claude = claude_client or ClaudeClient()
        self.quality_threshold = 65  # Minimum score to continue
        
    async def evaluate_pilot(
        self,
        original_request: str,
        pilot: PilotStrategy,
        scene_results: List[SceneResult],
        budget_spent: float,
        budget_allocated: float
    ) -> PilotResults:
        """
        Deep analysis comparing generated scenes to original intent
        
        Args:
            original_request: The original video request
            pilot: The pilot strategy being evaluated
            scene_results: Results from test scene generation
            budget_spent: Amount spent so far
            budget_allocated: Total budget allocated to this pilot
            
        Returns:
            PilotResults with critic's evaluation and decision
        """
        
        # Calculate average QA score
        avg_qa = sum(s.qa_score for s in scene_results) / len(scene_results)
        
        # Prepare scene summaries for analysis
        scene_summaries = []
        for scene in scene_results:
            scene_summaries.append({
                "scene_id": scene.scene_id,
                "description": scene.description,
                "qa_score": scene.qa_score,
                "cost": scene.generation_cost
            })
        
        prompt = f"""You are a production critic evaluating test scenes from a video pilot.

ORIGINAL REQUEST:
{original_request}

PILOT DETAILS:
- ID: {pilot.pilot_id}
- Tier: {pilot.tier.value}
- Budget allocated: ${budget_allocated}
- Budget spent: ${budget_spent}
- Scenes produced: {len(scene_results)}

TEST SCENE RESULTS:
{self._format_scene_results(scene_summaries)}

AVERAGE QA SCORE: {avg_qa:.1f}/100

YOUR TASK:
Perform a gap analysis between the original request and what was generated.

1. How well do these scenes match the creative intent?
2. What's missing or incorrectly interpreted?
3. Is the quality acceptable for this tier?
4. Should we continue this pilot with more budget?

SCORING RUBRIC:
- 90-100: Excellent match, continue with 100% remaining budget
- 75-89:  Good match, continue with 75% remaining budget
- 65-74:  Acceptable, continue with 50% remaining budget
- Below 65: Poor match, CANCEL pilot and reallocate budget

Return ONLY valid JSON:
{{
  "overall_score": 85,
  "gap_analysis": {{
    "matched_elements": ["element1", "element2"],
    "missing_elements": ["element3"],
    "quality_issues": ["issue1"]
  }},
  "decision": "continue",
  "budget_multiplier": 0.75,
  "reasoning": "Good execution but needs adjustment in X",
  "adjustments_needed": ["adjustment1", "adjustment2"]
}}"""

        response = await self.claude.query(prompt)
        critique_data = JSONExtractor.extract(response)
        
        # Calculate budget continuation
        decision = critique_data["decision"]
        approved = decision == "continue"
        
        budget_remaining = budget_allocated - budget_spent
        
        if approved:
            multiplier = critique_data.get("budget_multiplier", 1.0)
            recommended_budget = budget_remaining * multiplier
        else:
            recommended_budget = 0
        
        # Build result
        result = PilotResults(
            pilot_id=pilot.pilot_id,
            tier=pilot.tier.value,
            scenes_generated=scene_results,
            total_cost=budget_spent,
            avg_qa_score=avg_qa,
            critic_score=critique_data["overall_score"],
            approved=approved,
            budget_remaining=recommended_budget,
            gap_analysis=critique_data["gap_analysis"],
            critic_reasoning=critique_data["reasoning"],
            adjustments_needed=critique_data.get("adjustments_needed", [])
        )
        
        return result
    
    def _format_scene_results(self, scenes: List[Dict]) -> str:
        """Format scene results for the prompt"""
        lines = []
        for i, scene in enumerate(scenes, 1):
            lines.append(f"Scene {i}:")
            lines.append(f"  ID: {scene['scene_id']}")
            lines.append(f"  Description: {scene['description']}")
            lines.append(f"  QA Score: {scene['qa_score']}/100")
            lines.append(f"  Cost: ${scene['cost']:.2f}")
        return "\n".join(lines)
    
    def compare_pilots(self, results: List[PilotResults]) -> PilotResults:
        """
        Compare multiple pilot results and select the best
        
        Args:
            results: List of pilot results to compare
            
        Returns:
            The best pilot result
        """
        # Filter to approved pilots only
        approved = [r for r in results if r.approved]
        
        if not approved:
            return None
        
        # Sort by critic score, then by cost efficiency
        best = max(approved, key=lambda r: (
            r.critic_score,
            r.avg_qa_score / r.total_cost  # Quality per dollar
        ))
        
        return best
