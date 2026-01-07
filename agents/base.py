"""
Base Agent Classes for Claude Studio Producer

Provides base classes that extend Strands SDK for agent orchestration
while maintaining backward compatibility with standalone usage.
"""

from typing import Optional
from strands import Agent
from core.claude_client import ClaudeClient


class StudioAgent(Agent):
    """
    Base class for all Claude Studio Producer agents.

    Extends strands.Agent to provide:
    - Common ClaudeClient initialization
    - Shared utilities for all agents
    - Backward compatibility for standalone usage

    All studio agents should inherit from this class and use @tool
    decorators for their main methods to enable Strands orchestration.
    """

    def __init__(self, claude_client: Optional[ClaudeClient] = None, **kwargs):
        """
        Initialize studio agent.

        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
            **kwargs: Additional arguments passed to strands.Agent
        """
        super().__init__(**kwargs)
        self.claude = claude_client or ClaudeClient()

    def _format_budget(self, amount: float) -> str:
        """Format budget amount as currency string"""
        return f"${amount:.2f}"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to readable string"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"

    def _truncate_text(self, text: str, max_length: int = 100) -> str:
        """Truncate text to max length with ellipsis"""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
