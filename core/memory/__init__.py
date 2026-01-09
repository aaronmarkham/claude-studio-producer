"""Memory module for Claude Studio Producer"""

from core.memory.manager import MemoryManager
from core.memory.bootstrap import bootstrap_all_providers, INITIAL_PROVIDER_KNOWLEDGE

# Global singleton instance
memory_manager = MemoryManager()

__all__ = [
    "MemoryManager",
    "memory_manager",
    "bootstrap_all_providers",
    "INITIAL_PROVIDER_KNOWLEDGE",
]
