"""Producer Agent - Budget planning and pilot strategy"""

from dataclasses import dataclass
from typing import List, Optional
from strands import tool
from core.budget import ProductionTier, COST_MODELS
from core.claude_client import ClaudeClient, JSONExtractor
from core.models.memory import ProviderKnowledge
from .base import StudioAgent


@dataclass
class PilotStrategy:
    """A pilot production strategy"""
    pilot_id: str
    tier: ProductionTier
    allocated_budget: float
    test_scene_count: int
    full_scene_count: int
    rationale: str


class ProducerAgent(StudioAgent):
    """
    Analyzes requests and budgets, creates multi-pilot strategies
    """

    _is_stub = False

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
        """
        super().__init__(claude_client=claude_client)

    @tool
    async def analyze_and_plan(
        self,
        user_request: str,
        total_budget: float,
        provider_knowledge: Optional[ProviderKnowledge] = None
    ) -> List[PilotStrategy]:
        """
        Analyze request to determine production strategy

        Args:
            user_request: Description of the video to create
            total_budget: Total budget available
            provider_knowledge: Optional learned knowledge about the video provider

        Returns:
            List of pilot strategies to test
        """
        # Build provider guidelines section if we have knowledge
        provider_guidelines = ""
        if provider_knowledge:
            provider_guidelines = f"""
IMPORTANT - PROVIDER LEARNINGS (from {provider_knowledge.total_runs} previous runs with {provider_knowledge.provider}):

Provider Strengths (leverage these):
{self._format_list(provider_knowledge.known_strengths)}

Provider Weaknesses (avoid these):
{self._format_list(provider_knowledge.known_weaknesses)}

Prompt Guidelines (follow these):
{self._format_list(provider_knowledge.prompt_guidelines)}

Things to Avoid:
{self._format_list(provider_knowledge.avoid_list)}

Average Quality Score: {provider_knowledge.avg_quality:.0f}/100
Average Prompt Adherence: {provider_knowledge.avg_adherence:.0f}/100

Consider these learnings when planning the production strategy.
"""

        prompt = f"""You are a video production planner.

REQUEST: {user_request}
BUDGET: ${total_budget}
{provider_guidelines}
Available production tiers:
- static_images: $0.02/sec - Slideshows (quality ceiling: 75/100)
- motion_graphics: $0.08/sec - Explainers, infographics (quality ceiling: 85/100)
- animated: $0.15/sec - Storytelling, characters (quality ceiling: 90/100)
- photorealistic: $0.25/sec - Highest quality video (quality ceiling: 95/100)

Create 2-3 pilot strategies with different tiers for competitive testing.
Each pilot gets initial budget and produces 2-4 test scenes first.
Assume ~60 second video = 10-15 scenes total.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "total_scenes_estimated": 12,
  "pilots": [
    {{
      "pilot_id": "pilot_a",
      "tier": "motion_graphics",
      "rationale": "Cost-effective baseline",
      "allocated_budget": 60.0,
      "test_scene_count": 3
    }}
  ]
}}"""

        response = await self.claude.query(prompt)
        plan_data = JSONExtractor.extract(response)

        # Convert to PilotStrategy objects
        pilots = []
        for p in plan_data["pilots"]:
            pilots.append(PilotStrategy(
                pilot_id=p["pilot_id"],
                tier=ProductionTier(p["tier"]),
                allocated_budget=p["allocated_budget"],
                test_scene_count=p["test_scene_count"],
                full_scene_count=plan_data["total_scenes_estimated"],
                rationale=p["rationale"]
            ))

        return pilots

    @tool
    def estimate_pilot_cost(
        self,
        pilot: PilotStrategy,
        num_variations: int = 3,
        avg_duration_per_scene: float = 5.0
    ) -> float:
        """
        Estimate cost for pilot's test phase

        Args:
            pilot: The pilot strategy
            num_variations: Number of video variations per scene
            avg_duration_per_scene: Average seconds per scene

        Returns:
            Estimated cost in USD
        """
        cost_model = COST_MODELS[pilot.tier]

        video_cost = (
            pilot.test_scene_count *
            avg_duration_per_scene *
            num_variations *
            cost_model.cost_per_second
        )

        claude_cost = (
            cost_model.claude_tokens_estimate *
            pilot.test_scene_count *
            0.003 / 1000
        )

        return round(video_cost + claude_cost, 2)

    def _format_list(self, items: List[str]) -> str:
        """Format a list of items as bullet points"""
        if not items:
            return "  (none yet)"
        return "\n".join(f"  - {item}" for item in items[:10])  # Limit to 10 items
