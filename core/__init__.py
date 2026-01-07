"""Claude Studio Producer - Core components"""

from .budget import (
    ProductionTier,
    CostModel,
    COST_MODELS,
    BudgetTracker,
    estimate_realistic_cost
)
from .claude_client import ClaudeClient, JSONExtractor
from .producer import ProducerAgent, PilotStrategy
from .critic import CriticAgent, SceneResult, PilotResults
from .orchestrator import StudioOrchestrator, ProductionResult

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
    
    # Agents
    "ProducerAgent",
    "PilotStrategy",
    "CriticAgent",
    "SceneResult",
    "PilotResults",
    
    # Orchestrator
    "StudioOrchestrator",
    "ProductionResult",
]
