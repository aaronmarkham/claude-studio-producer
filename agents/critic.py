"""Critic Agent - Evaluates pilot results and makes budget decisions"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from strands import tool
from core.claude_client import ClaudeClient, JSONExtractor
from core.models.memory import ProviderLearning
from .base import StudioAgent


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


class CriticAgent(StudioAgent):
    """
    Evaluates pilot results against original intent
    Makes budget continuation/cancellation decisions
    """

    _is_stub = False

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        super().__init__(claude_client=claude_client)
        self.quality_threshold = 65  # Minimum score to continue

    @tool
    async def evaluate_pilot(
        self,
        original_request: str,
        pilot,  # PilotStrategy from agents.producer
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
    
    @tool
    def compare_pilots(self, results: List[PilotResults]) -> Optional[PilotResults]:
        """
        Compare multiple pilot results and select the best

        Args:
            results: List of pilot results to compare

        Returns:
            The best pilot result, or None if none are approved
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

    @tool
    async def analyze_provider_performance(
        self,
        scenes: List[Any],  # Scene objects
        videos: List[Any],  # GeneratedVideo objects
        qa_results: List[Any],  # QA results
        provider: str,
        run_id: str,
        concept: str
    ) -> ProviderLearning:
        """
        Analyze how well the provider performed and extract learnings.
        Uses Claude to compare prompts vs results and identify patterns.

        Args:
            scenes: List of Scene objects with descriptions
            videos: List of GeneratedVideo objects
            qa_results: List of QA verification results
            provider: Provider name (e.g., "luma", "runway")
            run_id: Current run ID
            concept: Original concept description

        Returns:
            ProviderLearning with insights about what worked and didn't
        """
        # Format scenes and results for analysis
        scene_analysis = self._format_scenes_for_provider_analysis(scenes, videos, qa_results)

        prompt = f"""You are analyzing AI video generation results to extract learnings about the provider.

PROVIDER: {provider}
CONCEPT: {concept}

SCENES AND RESULTS:
{scene_analysis}

Analyze what worked and what didn't. Consider:
1. Did the videos match the scene descriptions/prompts?
2. What types of prompts produced good results?
3. What types of prompts failed or produced unexpected results?
4. Any patterns in successful vs unsuccessful generations?
5. What should we do differently next time with this provider?

Return ONLY valid JSON:
{{
    "overall_success": true,
    "adherence_score": 75,
    "quality_score": 80,
    "effective_patterns": ["pattern that worked well", "another good pattern"],
    "strengths_observed": ["what the provider did well"],
    "ineffective_patterns": ["pattern that didn't work"],
    "weaknesses_observed": ["what the provider struggled with"],
    "prompt_tips": ["specific actionable tip for future prompts"],
    "avoid_list": ["things to avoid in prompts"],
    "concept_type": "demo",
    "prompt_analysis": [
        {{"prompt": "the prompt used", "result": "good", "notes": "why it worked/failed"}}
    ]
}}

Be specific and actionable. Focus on patterns that can help improve future prompts."""

        response = await self.claude.query(prompt)
        data = JSONExtractor.extract(response)

        # Build ProviderLearning from response
        return ProviderLearning(
            provider=provider,
            run_id=run_id,
            timestamp=datetime.now(timezone.utc),
            overall_success=data.get("overall_success", True),
            adherence_score=data.get("adherence_score", 70),
            quality_score=data.get("quality_score", 70),
            effective_patterns=data.get("effective_patterns", []),
            strengths_observed=data.get("strengths_observed", []),
            ineffective_patterns=data.get("ineffective_patterns", []),
            weaknesses_observed=data.get("weaknesses_observed", []),
            prompt_tips=data.get("prompt_tips", []),
            avoid_list=data.get("avoid_list", []),
            concept_type=data.get("concept_type", ""),
            prompt_samples=data.get("prompt_analysis", [])
        )

    def _format_scenes_for_provider_analysis(
        self,
        scenes: List[Any],
        videos: List[Any],
        qa_results: List[Any]
    ) -> str:
        """Format scenes, videos, and QA results for provider analysis"""
        lines = []

        # Create lookup dicts
        video_lookup = {}
        for video in videos:
            scene_id = getattr(video, 'scene_id', None)
            if scene_id:
                if scene_id not in video_lookup:
                    video_lookup[scene_id] = []
                video_lookup[scene_id].append(video)

        qa_lookup = {}
        for qa in qa_results:
            scene_id = getattr(qa, 'scene_id', None)
            if scene_id:
                qa_lookup[scene_id] = qa

        for i, scene in enumerate(scenes, 1):
            scene_id = getattr(scene, 'scene_id', f'scene_{i}')
            description = getattr(scene, 'description', '')
            title = getattr(scene, 'title', '')
            prompt_hints = getattr(scene, 'prompt_hints', [])

            lines.append(f"\n=== Scene {i}: {title} ===")
            lines.append(f"PROMPT/DESCRIPTION: {description}")
            if prompt_hints:
                lines.append(f"HINTS: {', '.join(prompt_hints)}")

            # Add video results
            scene_videos = video_lookup.get(scene_id, [])
            if scene_videos:
                for j, video in enumerate(scene_videos):
                    quality = getattr(video, 'quality_score', None)
                    cost = getattr(video, 'generation_cost', 0)
                    lines.append(f"  Video {j+1}: Quality={quality}/100, Cost=${cost:.2f}")
            else:
                lines.append("  No videos generated")

            # Add QA result
            qa = qa_lookup.get(scene_id)
            if qa:
                passed = getattr(qa, 'passed', False)
                score = getattr(qa, 'overall_score', 0)
                feedback = getattr(qa, 'feedback', '')
                lines.append(f"  QA: {'PASSED' if passed else 'FAILED'} (Score: {score})")
                if feedback:
                    lines.append(f"  QA Feedback: {feedback[:200]}")

        return "\n".join(lines)
