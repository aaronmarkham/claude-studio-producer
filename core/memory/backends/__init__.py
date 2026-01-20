"""Memory storage backends"""

from core.memory.backends.base import MemoryBackend, MemoryRecord
from core.memory.backends.local import LocalMemoryBackend

__all__ = [
    "MemoryBackend",
    "MemoryRecord",
    "LocalMemoryBackend",
]

# AgentCore backend will be imported conditionally when AWS dependencies are available
