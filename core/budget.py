"""Budget tracking and cost models with realistic pricing"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict


class ProductionTier(Enum):
    """Video production quality tiers"""
    STATIC_IMAGES = "static_images"
    MOTION_GRAPHICS = "motion_graphics"
    ANIMATED = "animated"
    PHOTOREALISTIC = "photorealistic"


@dataclass
class CostModel:
    """Cost estimates for a production tier"""
    tier: ProductionTier
    cost_per_second: float
    cost_per_variation: float
    claude_tokens_estimate: int
    quality_ceiling: float
    
    # Real-world context
    provider_examples: str = ""
    typical_use_cases: str = ""
    

# Updated with real 2025 pricing
COST_MODELS = {
    ProductionTier.STATIC_IMAGES: CostModel(
        tier=ProductionTier.STATIC_IMAGES,
        cost_per_second=0.04,  # Updated: More realistic for quality images
        cost_per_variation=0.02,
        claude_tokens_estimate=5000,
        quality_ceiling=75,
        provider_examples="DALL-E 3, Midjourney, Stable Diffusion",
        typical_use_cases="Presentations, slideshows, simple explainers"
    ),
    
    ProductionTier.MOTION_GRAPHICS: CostModel(
        tier=ProductionTier.MOTION_GRAPHICS,
        cost_per_second=0.15,  # Updated: Accounts for template licensing + rendering
        cost_per_variation=0.10,
        claude_tokens_estimate=8000,
        quality_ceiling=85,
        provider_examples="Remotion, Lottie animations, template-based",
        typical_use_cases="Product demos, explainer videos, infographics"
    ),
    
    ProductionTier.ANIMATED: CostModel(
        tier=ProductionTier.ANIMATED,
        cost_per_second=0.25,  # Updated: Realistic for Pika/Gen-2 quality
        cost_per_variation=0.20,
        claude_tokens_estimate=10000,
        quality_ceiling=90,
        provider_examples="Pika Labs, Runway Gen-2, Stability AI Video",
        typical_use_cases="Storytelling, character animation, branded content"
    ),
    
    ProductionTier.PHOTOREALISTIC: CostModel(
        tier=ProductionTier.PHOTOREALISTIC,
        cost_per_second=0.50,  # Updated: Premium pricing for best quality
        cost_per_variation=0.40,
        claude_tokens_estimate=15000,
        quality_ceiling=95,
        provider_examples="Runway Gen-3 Alpha, Sora (when available)",
        typical_use_cases="High-end commercials, realistic scenes, premium content"
    )
}


class BudgetTracker:
    """Track spending across pilots in real-time"""
    
    def __init__(self, total_budget: float):
        self.total_budget = total_budget
        self.pilot_spending: Dict[str, float] = {}
        self.overhead_spending: float = 0  # Claude API, failed generations, etc.
        
    def record_spend(self, pilot_id: str, amount: float):
        """Record spending for a pilot"""
        if pilot_id not in self.pilot_spending:
            self.pilot_spending[pilot_id] = 0
        self.pilot_spending[pilot_id] += amount
    
    def record_overhead(self, amount: float, reason: str = ""):
        """Record overhead costs (Claude API, etc.)"""
        self.overhead_spending += amount
        
    def get_remaining_budget(self) -> float:
        """Get total remaining budget"""
        total_spent = sum(self.pilot_spending.values()) + self.overhead_spending
        return self.total_budget - total_spent
    
    def get_pilot_spent(self, pilot_id: str) -> float:
        """Get amount spent by specific pilot"""
        return self.pilot_spending.get(pilot_id, 0)
    
    def get_total_spent(self) -> float:
        """Get total amount spent"""
        return sum(self.pilot_spending.values()) + self.overhead_spending
    
    def print_status(self):
        """Print detailed budget status"""
        print("\n" + "="*60)
        print("BUDGET STATUS")
        print("="*60)
        print(f"Total Budget:     ${self.total_budget:.2f}")
        print(f"\nPilot Spending:")
        for pilot_id, spent in self.pilot_spending.items():
            pct = (spent / self.total_budget) * 100
            print(f"  {pilot_id:12} ${spent:6.2f}  ({pct:.1f}%)")
        print(f"\nOverhead:         ${self.overhead_spending:.2f}")
        print(f"Total Spent:      ${self.get_total_spent():.2f}")
        print(f"Remaining:        ${self.get_remaining_budget():.2f}")
        print("="*60 + "\n")


def estimate_realistic_cost(
    tier: ProductionTier,
    num_scenes: int,
    num_variations: int = 3,
    avg_scene_duration: float = 5.0,
    include_overhead: bool = True
) -> Dict[str, float]:
    """
    Estimate realistic production costs with breakdown
    
    Args:
        tier: Production quality tier
        num_scenes: Number of scenes to generate
        num_variations: Variations per scene (for selection)
        avg_scene_duration: Average duration per scene in seconds
        include_overhead: Include Claude API and overhead costs
        
    Returns:
        Dict with cost breakdown
    """
    cost_model = COST_MODELS[tier]
    
    # Base video generation cost
    total_seconds = num_scenes * avg_scene_duration * num_variations
    video_cost = total_seconds * cost_model.cost_per_second
    
    # Claude API costs (prompt engineering + QA)
    claude_cost = 0
    if include_overhead:
        # Script writing, prompt generation, QA verification
        tokens_per_scene = cost_model.claude_tokens_estimate
        total_tokens = tokens_per_scene * num_scenes
        # $3 per 1M input tokens, $15 per 1M output tokens (Claude Sonnet)
        claude_cost = (total_tokens * 0.003 / 1000) + (total_tokens * 0.5 * 0.015 / 1000)
    
    # Failed generation buffer (20% failure rate is realistic)
    failure_buffer = video_cost * 0.20
    
    total = video_cost + claude_cost + failure_buffer
    
    return {
        "video_generation": round(video_cost, 2),
        "claude_api": round(claude_cost, 2),
        "failure_buffer": round(failure_buffer, 2),
        "total": round(total, 2),
        "cost_per_scene": round(total / num_scenes, 2)
    }
