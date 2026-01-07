"""Core components - orchestration, budget, and infrastructure"""

from .budget import (
    ProductionTier,
    CostModel,
    COST_MODELS,
    BudgetTracker,
    estimate_realistic_cost
)
from .claude_client import ClaudeClient, JSONExtractor

# Note: StudioOrchestrator is NOT imported here to avoid circular imports
# Import it directly: from core.orchestrator import StudioOrchestrator

__all__ = [
    # Budget
    "ProductionTier",
    "CostModel",
    "COST_MODELS",
    "BudgetTracker",
    "estimate_realistic_cost",
    
    # Claude client
    "ClaudeClient",
    "JSONExtractor",
]
