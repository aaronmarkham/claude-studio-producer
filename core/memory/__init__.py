"""Memory module for Claude Studio Producer"""

from core.memory.manager import MemoryManager
from core.memory.bootstrap import bootstrap_all_providers, INITIAL_PROVIDER_KNOWLEDGE

# Multi-tenant memory system
from core.memory.namespace import (
    MultiTenantNamespaceBuilder,
    NamespaceContext,
    NamespaceLevel,
    NamespaceType,
    PROMOTION_RULES,
    get_promotion_target,
)
from core.memory.backends.base import MemoryBackend, MemoryRecord, RetrievalResult
from core.memory.backends.local import LocalMemoryBackend
from core.memory.multi_tenant_manager import (
    MultiTenantMemoryManager,
    MultiTenantConfig,
    MemoryMode,
    LearningRecord,
    get_memory_manager,
    reset_memory_manager,
)

# Global singleton instance (legacy)
memory_manager = MemoryManager()

__all__ = [
    # Legacy memory manager
    "MemoryManager",
    "memory_manager",
    "bootstrap_all_providers",
    "INITIAL_PROVIDER_KNOWLEDGE",
    # Multi-tenant namespace
    "MultiTenantNamespaceBuilder",
    "NamespaceContext",
    "NamespaceLevel",
    "NamespaceType",
    "PROMOTION_RULES",
    "get_promotion_target",
    # Backend interfaces
    "MemoryBackend",
    "MemoryRecord",
    "RetrievalResult",
    "LocalMemoryBackend",
    # Multi-tenant manager
    "MultiTenantMemoryManager",
    "MultiTenantConfig",
    "MemoryMode",
    "LearningRecord",
    "get_memory_manager",
    "reset_memory_manager",
]
