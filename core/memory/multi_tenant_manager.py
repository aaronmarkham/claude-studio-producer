"""
Multi-Tenant Memory Manager

Provides a high-level API for storing and retrieving learnings across
the namespace hierarchy. Supports:
- Local mode: JSON file storage for development
- Hosted mode: AWS AgentCore with IAM access control

The manager automatically handles:
- Namespace resolution based on context
- Priority-based retrieval across namespaces
- Learning promotion between levels
- Access control validation
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from core.memory.namespace import (
    MultiTenantNamespaceBuilder,
    NamespaceContext,
    NamespaceLevel,
    PromotionRule,
    PROMOTION_RULES,
    get_promotion_target,
)
from core.memory.backends.base import MemoryBackend, MemoryRecord, RetrievalResult
from core.memory.backends.local import LocalMemoryBackend

logger = logging.getLogger(__name__)


class MemoryMode(Enum):
    """Operating mode for memory system"""
    LOCAL = "local"      # JSON file storage (development)
    HOSTED = "hosted"    # AWS AgentCore (production)


@dataclass
class MultiTenantConfig:
    """Configuration for multi-tenant memory"""
    mode: MemoryMode = MemoryMode.LOCAL
    base_path: str = "artifacts/memory"

    # Default context for local development
    default_org_id: str = "local"
    default_actor_id: str = "dev"

    # AgentCore settings (for hosted mode)
    agentcore_memory_id: Optional[str] = None
    aws_region: str = "us-east-1"

    # Role for local mode (all permissions)
    local_roles: List[str] = field(default_factory=lambda: [
        "platform_admin", "org_admin", "org_curator", "org_member"
    ])

    @classmethod
    def from_env(cls) -> 'MultiTenantConfig':
        """Create config from environment variables"""
        memory_id = os.environ.get("AGENTCORE_MEMORY_ID")
        mode = MemoryMode.HOSTED if memory_id else MemoryMode.LOCAL

        return cls(
            mode=mode,
            base_path=os.environ.get("MEMORY_BASE_PATH", "artifacts/memory"),
            default_org_id=os.environ.get("MEMORY_ORG_ID", "local"),
            default_actor_id=os.environ.get("MEMORY_ACTOR_ID", "dev"),
            agentcore_memory_id=memory_id,
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        )


@dataclass
class LearningRecord:
    """A learning record with full context"""
    record: MemoryRecord
    namespace: str
    level: NamespaceLevel
    priority: float = 1.0

    @property
    def content(self) -> Dict[str, Any]:
        return self.record.content

    @property
    def text(self) -> Optional[str]:
        return self.record.text_content


class MultiTenantMemoryManager:
    """
    High-level manager for multi-tenant memory operations.

    Provides methods for:
    - Storing learnings at appropriate namespace level
    - Retrieving learnings with priority-based merging
    - Promoting learnings between levels
    - Managing user preferences and config

    Example usage:
        # Local development
        manager = MultiTenantMemoryManager()
        ctx = manager.get_context()

        # Store a provider learning
        await manager.store_provider_learning(
            provider="luma",
            learning={
                "pattern": "Use concrete nouns",
                "effectiveness": 0.85,
            },
            level=NamespaceLevel.USER,
            ctx=ctx
        )

        # Retrieve learnings for a provider
        learnings = await manager.get_provider_learnings(
            provider="luma",
            ctx=ctx
        )
    """

    def __init__(self, config: Optional[MultiTenantConfig] = None):
        """
        Initialize the multi-tenant manager.

        Args:
            config: Configuration (defaults to auto-detect from environment)
        """
        self.config = config or MultiTenantConfig.from_env()
        self._backend: Optional[MemoryBackend] = None
        self._ns = MultiTenantNamespaceBuilder

    @property
    def backend(self) -> MemoryBackend:
        """Lazy initialization of storage backend"""
        if self._backend is None:
            if self.config.mode == MemoryMode.HOSTED:
                from core.memory.backends.agentcore import AgentCoreMemoryBackend
                self._backend = AgentCoreMemoryBackend(
                    memory_id=self.config.agentcore_memory_id,
                    region=self.config.aws_region,
                )
            else:
                self._backend = LocalMemoryBackend(
                    base_path=self.config.base_path
                )
        return self._backend

    def get_context(
        self,
        org_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> NamespaceContext:
        """
        Get a namespace context for operations.

        Args:
            org_id: Organization ID (uses default if not specified)
            actor_id: Actor/user ID (uses default if not specified)
            session_id: Optional session ID for session-scoped operations

        Returns:
            NamespaceContext for building namespaces
        """
        return NamespaceContext(
            org_id=org_id or self.config.default_org_id,
            actor_id=actor_id or self.config.default_actor_id,
            session_id=session_id,
        )

    # ==========================================================================
    # PROVIDER LEARNINGS
    # ==========================================================================

    async def store_provider_learning(
        self,
        provider: str,
        learning: Dict[str, Any],
        level: NamespaceLevel = NamespaceLevel.USER,
        ctx: Optional[NamespaceContext] = None,
        text_content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Store a learning about a provider.

        Args:
            provider: Provider ID (e.g., "luma", "runway")
            learning: Learning content dict
            level: Namespace level to store at
            ctx: Namespace context
            text_content: Searchable text representation
            tags: Optional tags for filtering

        Returns:
            Record ID of stored learning
        """
        ctx = ctx or self.get_context()
        namespace = self._ns.for_provider_learnings(provider, level, ctx)

        # Build text content for search if not provided
        if text_content is None:
            text_content = self._learning_to_text(learning)

        record = MemoryRecord(
            namespace=namespace,
            content=learning,
            text_content=text_content,
            created_by=ctx.actor_id,
            tags=tags or [provider, "learning"],
        )

        return await self.backend.create(record)

    async def get_provider_learnings(
        self,
        provider: str,
        ctx: Optional[NamespaceContext] = None,
        include_session: bool = False,
        top_k: int = 20,
    ) -> List[LearningRecord]:
        """
        Get learnings for a provider from all applicable namespaces.

        Returns learnings merged by priority:
        1. Platform learnings (highest)
        2. Org learnings
        3. User learnings
        4. Session learnings (lowest, if included)

        Args:
            provider: Provider ID
            ctx: Namespace context
            include_session: Include session-scoped experimental learnings
            top_k: Maximum results

        Returns:
            List of LearningRecord sorted by priority
        """
        ctx = ctx or self.get_context()
        namespaces = self._ns.get_retrieval_namespaces(
            provider, ctx, include_session=include_session
        )

        results = []

        for ns_info in namespaces:
            try:
                records = await self.backend.list(
                    ns_info["namespace"],
                    limit=top_k,
                    tags=[provider]
                )

                for record in records:
                    results.append(LearningRecord(
                        record=record,
                        namespace=ns_info["namespace"],
                        level=ns_info["level"],
                        priority=ns_info["priority"],
                    ))
            except Exception as e:
                logger.debug(f"Could not load namespace {ns_info['namespace']}: {e}")
                continue

        # Sort by priority (descending) then by confidence
        results.sort(key=lambda r: (r.priority, r.record.confidence), reverse=True)

        return results[:top_k]

    async def search_learnings(
        self,
        query: str,
        provider: Optional[str] = None,
        ctx: Optional[NamespaceContext] = None,
        include_session: bool = False,
        top_k: int = 10,
    ) -> List[LearningRecord]:
        """
        Search for learnings matching a query.

        Args:
            query: Search query
            provider: Optional provider filter
            ctx: Namespace context
            include_session: Include session learnings
            top_k: Maximum results

        Returns:
            List of matching LearningRecord
        """
        ctx = ctx or self.get_context()

        # Build list of namespaces to search
        if provider:
            ns_infos = self._ns.get_retrieval_namespaces(
                provider, ctx, include_session=include_session
            )
        else:
            # Search all global learnings
            ns_infos = [
                {"namespace": self._ns.PLATFORM_LEARNINGS_GLOBAL, "level": NamespaceLevel.PLATFORM, "priority": 1.0},
                {"namespace": self._ns.build(self._ns.ORG_LEARNINGS_GLOBAL, ctx), "level": NamespaceLevel.ORG, "priority": 0.85},
                {"namespace": self._ns.build(self._ns.USER_LEARNINGS_GLOBAL, ctx), "level": NamespaceLevel.USER, "priority": 0.70},
            ]

        namespaces = [ns["namespace"] for ns in ns_infos]
        ns_info_map = {ns["namespace"]: ns for ns in ns_infos}

        # Search
        results = await self.backend.search(
            namespaces=namespaces,
            query=query,
            top_k=top_k,
            tags=[provider] if provider else None,
        )

        # Convert to LearningRecord with priority
        learning_results = []
        for result in results:
            ns_info = ns_info_map.get(result.source_namespace, {})
            learning_results.append(LearningRecord(
                record=result.record,
                namespace=result.source_namespace,
                level=ns_info.get("level", NamespaceLevel.USER),
                priority=result.score * ns_info.get("priority", 1.0),
            ))

        return learning_results

    # ==========================================================================
    # LEARNING PROMOTION
    # ==========================================================================

    async def promote_learning(
        self,
        record_id: str,
        from_namespace: str,
        ctx: Optional[NamespaceContext] = None,
        provider: Optional[str] = None,
        promoted_by: Optional[str] = None,
        reason: str = "manual",
    ) -> Optional[str]:
        """
        Promote a learning to the next level.

        Args:
            record_id: ID of record to promote
            from_namespace: Current namespace
            ctx: Namespace context
            provider: Provider ID (for provider learnings)
            promoted_by: Actor who promoted (or "system")
            reason: Promotion reason

        Returns:
            New record ID if promoted, None otherwise
        """
        ctx = ctx or self.get_context()

        # Get the original record
        original = await self.backend.get(from_namespace, record_id)
        if not original:
            logger.warning(f"Record {record_id} not found in {from_namespace}")
            return None

        # Get target namespace
        target_namespace = get_promotion_target(from_namespace, ctx, provider)
        if not target_namespace:
            logger.info(f"Record {record_id} already at highest level")
            return None

        # Create promoted record
        promoted = MemoryRecord(
            namespace=target_namespace,
            content=original.content,
            text_content=original.text_content,
            created_by=promoted_by or ctx.actor_id,
            promoted_from=original.record_id,
            promotion_history=[
                *original.promotion_history,
                {
                    "from_namespace": from_namespace,
                    "from_record_id": original.record_id,
                    "promoted_at": datetime.utcnow().isoformat(),
                    "promoted_by": promoted_by or ctx.actor_id,
                    "reason": reason,
                    "validations_at_promotion": original.validations,
                    "confidence_at_promotion": original.confidence,
                }
            ],
            tags=original.tags,
            validations=original.validations,
            confidence=original.confidence,
        )

        new_id = await self.backend.create(promoted)
        logger.info(f"Promoted learning from {from_namespace} to {target_namespace}")

        return new_id

    async def check_auto_promotion(
        self,
        record_id: str,
        namespace: str,
        ctx: Optional[NamespaceContext] = None,
    ) -> bool:
        """
        Check if a record should be auto-promoted based on rules.

        Args:
            record_id: Record to check
            namespace: Current namespace
            ctx: Namespace context

        Returns:
            True if promoted
        """
        ctx = ctx or self.get_context()

        record = await self.backend.get(namespace, record_id)
        if not record:
            return False

        parsed = self._ns.parse(namespace)
        current_level = parsed.get("level")

        # Find applicable promotion rule
        rule_map = {
            NamespaceLevel.SESSION: "session_to_user",
            NamespaceLevel.USER: "user_to_org",
            NamespaceLevel.ORG: "org_to_platform",
        }

        rule_name = rule_map.get(current_level)
        if not rule_name or rule_name not in PROMOTION_RULES:
            return False

        rule = PROMOTION_RULES[rule_name]

        # Check promotion criteria
        if record.validations < rule.min_validations:
            return False
        if record.confidence < rule.min_confidence:
            return False
        if rule.requires_approval:
            return False  # Manual approval required

        # Auto-promote
        provider = parsed.get("provider_id")
        new_id = await self.promote_learning(
            record_id=record_id,
            from_namespace=namespace,
            ctx=ctx,
            provider=provider,
            promoted_by="system",
            reason="auto_promotion",
        )

        return new_id is not None

    # ==========================================================================
    # PREFERENCES & CONFIG
    # ==========================================================================

    async def get_preferences(
        self,
        ctx: Optional[NamespaceContext] = None,
    ) -> Dict[str, Any]:
        """Get user preferences"""
        ctx = ctx or self.get_context()
        namespace = self._ns.build(self._ns.USER_PREFERENCES, ctx)

        records = await self.backend.list(namespace, limit=1)
        if records:
            return records[0].content

        return {}

    async def set_preferences(
        self,
        preferences: Dict[str, Any],
        ctx: Optional[NamespaceContext] = None,
    ) -> str:
        """Set user preferences"""
        ctx = ctx or self.get_context()
        namespace = self._ns.build(self._ns.USER_PREFERENCES, ctx)

        # Check for existing preferences
        records = await self.backend.list(namespace, limit=1)

        if records:
            # Update existing
            record = records[0]
            record.content.update(preferences)
            record.updated_at = datetime.utcnow()
            await self.backend.update(record)
            return record.record_id
        else:
            # Create new
            record = MemoryRecord(
                namespace=namespace,
                content=preferences,
                created_by=ctx.actor_id,
                tags=["preferences"],
            )
            return await self.backend.create(record)

    async def get_org_config(
        self,
        ctx: Optional[NamespaceContext] = None,
    ) -> Dict[str, Any]:
        """Get organization config"""
        ctx = ctx or self.get_context()
        namespace = self._ns.build(self._ns.ORG_CONFIG, ctx)

        records = await self.backend.list(namespace, limit=1)
        if records:
            return records[0].content

        return {}

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    def _learning_to_text(self, learning: Dict[str, Any]) -> str:
        """Convert learning dict to searchable text"""
        parts = []

        # Extract string values
        for key, value in learning.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        parts.append(item)

        return " ".join(parts)

    async def validate_learning(
        self,
        record_id: str,
        namespace: str,
        success: bool = True,
    ) -> Optional[MemoryRecord]:
        """
        Validate a learning (increment counter and update confidence).

        Args:
            record_id: Record to validate
            namespace: Record's namespace
            success: Whether the learning was successful

        Returns:
            Updated record
        """
        record = await self.backend.increment_validation(
            namespace, record_id, success
        )

        if record:
            # Check for auto-promotion
            await self.check_auto_promotion(record_id, namespace)

        return record

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        if isinstance(self.backend, LocalMemoryBackend):
            return await self.backend.get_stats()

        return {
            "mode": self.config.mode.value,
            "backend": type(self.backend).__name__,
        }


# ==========================================================================
# GLOBAL INSTANCE
# ==========================================================================

_manager: Optional[MultiTenantMemoryManager] = None


def get_memory_manager() -> MultiTenantMemoryManager:
    """Get the global multi-tenant memory manager"""
    global _manager
    if _manager is None:
        _manager = MultiTenantMemoryManager()
    return _manager


def reset_memory_manager():
    """Reset the global manager (for testing)"""
    global _manager
    _manager = None
