"""Mock QA provider for testing without frame extraction/vision API"""

import asyncio
import random
from typing import Dict, Any, List
from core.budget import ProductionTier, COST_MODELS


class MockQAProvider:
    """
    Mock QA provider that simulates video quality analysis.

    Generates realistic scores based on production tier quality ceilings
    without requiring actual frame extraction or vision API calls.
    """

    def __init__(self):
        self.verification_count = 0

    async def analyze_video(
        self,
        video_url: str,
        scene_description: str,
        visual_elements: List[str],
        production_tier: ProductionTier,
        duration: float
    ) -> Dict[str, Any]:
        """
        Simulate video quality analysis.

        Args:
            video_url: URL of video to analyze
            scene_description: Expected scene description
            visual_elements: Expected visual elements
            production_tier: Expected quality tier
            duration: Expected duration

        Returns:
            Dictionary with QA scores and feedback
        """
        # Simulate analysis delay
        await asyncio.sleep(random.uniform(0.3, 0.8))

        self.verification_count += 1

        # Get quality ceiling for this tier
        cost_model = COST_MODELS[production_tier]
        quality_ceiling = cost_model.quality_ceiling

        # Generate scores that respect the quality ceiling
        # Add some randomness but stay within reasonable bounds
        base_score = quality_ceiling - random.uniform(5, 15)

        # Individual scores vary slightly from base
        visual_accuracy = min(100, base_score + random.uniform(-3, 5))
        style_consistency = min(100, base_score + random.uniform(-5, 3))
        technical_quality = min(100, base_score + random.uniform(-4, 4))
        narrative_fit = min(100, base_score + random.uniform(-2, 6))

        # Calculate overall score
        overall_score = (
            visual_accuracy * 0.30 +
            style_consistency * 0.25 +
            technical_quality * 0.25 +
            narrative_fit * 0.20
        )

        # Generate realistic issues and suggestions based on score
        issues = []
        suggestions = []

        if overall_score < 80:
            issues.append("Some visual elements could be more prominent")
            suggestions.append("Emphasize key visual elements in the prompt")

        if technical_quality < 85:
            issues.append("Minor rendering artifacts detected")
            suggestions.append("Consider regenerating with higher quality settings")

        if style_consistency < 80:
            issues.append(f"Style doesn't fully match {production_tier.value} tier")
            suggestions.append("Add more specific style guidance in prompt")

        if narrative_fit < 85:
            issues.append("Scene flow could be improved")
            suggestions.append("Adjust pacing or transitions")

        return {
            "overall_score": round(overall_score, 1),
            "visual_accuracy": round(visual_accuracy, 1),
            "style_consistency": round(style_consistency, 1),
            "technical_quality": round(technical_quality, 1),
            "narrative_fit": round(narrative_fit, 1),
            "issues": issues if issues else ["No significant issues detected"],
            "suggestions": suggestions if suggestions else ["Video meets quality standards"]
        }

    def reset(self):
        """Reset verification counter"""
        self.verification_count = 0
