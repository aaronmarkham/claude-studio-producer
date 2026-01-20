"""
Multi-Tenant Namespace Builder

Defines the complete namespace hierarchy for Claude Studio Producer's
multi-tenant memory system. Supports:
- Platform-wide learnings (curated, cross-tenant)
- Organization-level learnings and config
- User-level learnings and preferences
- Session-level experiments

Compatible with:
- Local JSON storage (development)
- AWS AgentCore Memory (production)
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import re


class NamespaceLevel(Enum):
    """Hierarchy levels for learnings"""
    SESSION = "session"
    USER = "user"
    ORG = "org"
    PLATFORM = "platform"


class NamespaceType(Enum):
    """Types of namespaces"""
    LEARNINGS_GLOBAL = "learnings_global"
    LEARNINGS_PROVIDER = "learnings_provider"
    PREFERENCES = "preferences"
    CONFIG = "config"
    SESSIONS = "sessions"
    RUNS = "runs"
    SHARED = "shared"


@dataclass
class NamespaceContext:
    """Context for building namespaces"""
    org_id: str = "default"
    actor_id: str = "default"
    session_id: Optional[str] = None
    provider_id: Optional[str] = None
    run_id: Optional[str] = None

    @classmethod
    def local_dev(cls, session_id: Optional[str] = None) -> 'NamespaceContext':
        """Create context for local development (single user)"""
        return cls(
            org_id="local",
            actor_id="dev",
            session_id=session_id
        )


class MultiTenantNamespaceBuilder:
    """
    Builds namespaces following the multi-tenant hierarchy.

    Hierarchy:
        /platform/...                           - Platform-wide (curated)
        /org/{orgId}/...                        - Organization-level
        /org/{orgId}/actor/{actorId}/...        - User-level
        /org/{orgId}/actor/{actorId}/sessions/  - Session-level
    """

    # ==========================================================================
    # PLATFORM NAMESPACES (Cross-tenant, curated)
    # ==========================================================================

    PLATFORM_LEARNINGS_GLOBAL = "/platform/learnings/global"
    PLATFORM_LEARNINGS_PROVIDER = "/platform/learnings/provider/{providerId}"
    PLATFORM_CONFIG = "/platform/config"

    # ==========================================================================
    # ORGANIZATION NAMESPACES
    # ==========================================================================

    ORG_LEARNINGS_GLOBAL = "/org/{orgId}/learnings/global"
    ORG_LEARNINGS_PROVIDER = "/org/{orgId}/learnings/provider/{providerId}"
    ORG_CONFIG = "/org/{orgId}/config"
    ORG_SHARED = "/org/{orgId}/shared"

    # ==========================================================================
    # USER (ACTOR) NAMESPACES
    # ==========================================================================

    USER_LEARNINGS_GLOBAL = "/org/{orgId}/actor/{actorId}/learnings/global"
    USER_LEARNINGS_PROVIDER = "/org/{orgId}/actor/{actorId}/learnings/provider/{providerId}"
    USER_PREFERENCES = "/org/{orgId}/actor/{actorId}/preferences"
    USER_RUNS = "/org/{orgId}/actor/{actorId}/runs/{runId}"

    # ==========================================================================
    # SESSION NAMESPACES
    # ==========================================================================

    SESSION_LEARNINGS = "/org/{orgId}/actor/{actorId}/sessions/{sessionId}/learnings"
    SESSION_CONTEXT = "/org/{orgId}/actor/{actorId}/sessions/{sessionId}/context"

    # ==========================================================================
    # BUILDER METHODS
    # ==========================================================================

    @classmethod
    def build(cls, pattern: str, ctx: NamespaceContext = None, **kwargs) -> str:
        """
        Build a namespace from a pattern and context.

        Args:
            pattern: Namespace pattern with {placeholders}
            ctx: NamespaceContext with org_id, actor_id, etc.
            **kwargs: Additional placeholder values

        Returns:
            Fully resolved namespace string

        Example:
            >>> ctx = NamespaceContext(org_id="acme", actor_id="alice")
            >>> MultiTenantNamespaceBuilder.build(
            ...     MultiTenantNamespaceBuilder.USER_LEARNINGS_PROVIDER,
            ...     ctx,
            ...     providerId="luma"
            ... )
            '/org/acme/actor/alice/learnings/provider/luma'
        """
        if ctx is None:
            ctx = NamespaceContext()

        # Combine context and kwargs
        values = {
            "orgId": ctx.org_id,
            "actorId": ctx.actor_id,
            "sessionId": ctx.session_id,
            "providerId": ctx.provider_id,
            "runId": ctx.run_id,
            **kwargs
        }

        result = pattern
        for key, value in values.items():
            if value is not None:
                result = result.replace(f"{{{key}}}", str(value))

        # Check for unresolved placeholders
        unresolved = re.findall(r'\{(\w+)\}', result)
        if unresolved:
            raise ValueError(f"Unresolved placeholders in namespace: {unresolved}")

        return result

    @classmethod
    def for_provider_learnings(
        cls,
        provider: str,
        level: NamespaceLevel,
        ctx: NamespaceContext,
    ) -> str:
        """
        Get the namespace for provider learnings at a specific level.

        Args:
            provider: Provider ID (e.g., "luma", "runway")
            level: Namespace level (PLATFORM, ORG, USER, SESSION)
            ctx: Namespace context

        Returns:
            Namespace string
        """
        patterns = {
            NamespaceLevel.PLATFORM: cls.PLATFORM_LEARNINGS_PROVIDER,
            NamespaceLevel.ORG: cls.ORG_LEARNINGS_PROVIDER,
            NamespaceLevel.USER: cls.USER_LEARNINGS_PROVIDER,
            NamespaceLevel.SESSION: cls.SESSION_LEARNINGS,
        }

        pattern = patterns.get(level)
        if not pattern:
            raise ValueError(f"Invalid level for provider learnings: {level}")

        return cls.build(pattern, ctx, providerId=provider)

    @classmethod
    def for_global_learnings(
        cls,
        level: NamespaceLevel,
        ctx: NamespaceContext,
    ) -> str:
        """
        Get the namespace for global learnings at a specific level.
        """
        patterns = {
            NamespaceLevel.PLATFORM: cls.PLATFORM_LEARNINGS_GLOBAL,
            NamespaceLevel.ORG: cls.ORG_LEARNINGS_GLOBAL,
            NamespaceLevel.USER: cls.USER_LEARNINGS_GLOBAL,
        }

        pattern = patterns.get(level)
        if not pattern:
            raise ValueError(f"Invalid level for global learnings: {level}")

        return cls.build(pattern, ctx)

    @classmethod
    def get_retrieval_namespaces(
        cls,
        provider: str,
        ctx: NamespaceContext,
        include_session: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get all namespaces to query for learnings, with priority weights.

        Returns list of dicts with 'namespace', 'level', and 'priority' keys.
        Higher priority = more authoritative.
        """
        namespaces = []

        # Platform level (highest priority)
        namespaces.append({
            "namespace": cls.PLATFORM_LEARNINGS_GLOBAL,
            "level": NamespaceLevel.PLATFORM,
            "priority": 1.0,
            "type": "global",
        })
        namespaces.append({
            "namespace": cls.build(cls.PLATFORM_LEARNINGS_PROVIDER, ctx, providerId=provider),
            "level": NamespaceLevel.PLATFORM,
            "priority": 0.95,
            "type": "provider",
        })

        # Org level
        namespaces.append({
            "namespace": cls.build(cls.ORG_LEARNINGS_GLOBAL, ctx),
            "level": NamespaceLevel.ORG,
            "priority": 0.85,
            "type": "global",
        })
        namespaces.append({
            "namespace": cls.build(cls.ORG_LEARNINGS_PROVIDER, ctx, providerId=provider),
            "level": NamespaceLevel.ORG,
            "priority": 0.80,
            "type": "provider",
        })

        # User level
        namespaces.append({
            "namespace": cls.build(cls.USER_LEARNINGS_GLOBAL, ctx),
            "level": NamespaceLevel.USER,
            "priority": 0.70,
            "type": "global",
        })
        namespaces.append({
            "namespace": cls.build(cls.USER_LEARNINGS_PROVIDER, ctx, providerId=provider),
            "level": NamespaceLevel.USER,
            "priority": 0.65,
            "type": "provider",
        })

        # Session level (lowest priority, experimental)
        if include_session and ctx.session_id:
            namespaces.append({
                "namespace": cls.build(cls.SESSION_LEARNINGS, ctx),
                "level": NamespaceLevel.SESSION,
                "priority": 0.50,
                "type": "session",
            })

        return namespaces

    # ==========================================================================
    # PARSING & VALIDATION
    # ==========================================================================

    @classmethod
    def parse(cls, namespace: str) -> Dict[str, Any]:
        """
        Parse a namespace string to extract components.

        Returns:
            Dict with 'level', 'type', 'org_id', 'actor_id', etc.
        """
        result = {
            "level": None,
            "type": None,
            "org_id": None,
            "actor_id": None,
            "session_id": None,
            "provider_id": None,
            "run_id": None,
        }

        parts = namespace.strip("/").split("/")

        if not parts:
            return result

        # Determine level
        if parts[0] == "platform":
            result["level"] = NamespaceLevel.PLATFORM
        elif parts[0] == "org" and len(parts) >= 2:
            result["org_id"] = parts[1]
            if "actor" in parts:
                actor_idx = parts.index("actor")
                if actor_idx + 1 < len(parts):
                    result["actor_id"] = parts[actor_idx + 1]
                if "sessions" in parts:
                    result["level"] = NamespaceLevel.SESSION
                    session_idx = parts.index("sessions")
                    if session_idx + 1 < len(parts):
                        result["session_id"] = parts[session_idx + 1]
                else:
                    result["level"] = NamespaceLevel.USER
            else:
                result["level"] = NamespaceLevel.ORG

        # Determine type
        if "learnings" in parts:
            if "provider" in parts:
                result["type"] = NamespaceType.LEARNINGS_PROVIDER
                provider_idx = parts.index("provider")
                if provider_idx + 1 < len(parts):
                    result["provider_id"] = parts[provider_idx + 1]
            elif "global" in parts:
                result["type"] = NamespaceType.LEARNINGS_GLOBAL
        elif "preferences" in parts:
            result["type"] = NamespaceType.PREFERENCES
        elif "config" in parts:
            result["type"] = NamespaceType.CONFIG
        elif "runs" in parts:
            result["type"] = NamespaceType.RUNS
            run_idx = parts.index("runs")
            if run_idx + 1 < len(parts):
                result["run_id"] = parts[run_idx + 1]
        elif "shared" in parts:
            result["type"] = NamespaceType.SHARED

        return result

    @classmethod
    def get_level(cls, namespace: str) -> NamespaceLevel:
        """Get the level of a namespace"""
        parsed = cls.parse(namespace)
        return parsed.get("level")

    @classmethod
    def is_platform_namespace(cls, namespace: str) -> bool:
        """Check if namespace is platform-level"""
        return namespace.startswith("/platform/")

    @classmethod
    def is_org_namespace(cls, namespace: str, org_id: str) -> bool:
        """Check if namespace belongs to an org"""
        return namespace.startswith(f"/org/{org_id}/")

    @classmethod
    def is_user_namespace(cls, namespace: str, org_id: str, actor_id: str) -> bool:
        """Check if namespace belongs to a specific user"""
        return namespace.startswith(f"/org/{org_id}/actor/{actor_id}/")

    @classmethod
    def namespace_to_path(cls, namespace: str) -> str:
        """
        Convert a namespace to a file system path for local storage.

        Example:
            /org/acme/actor/alice/learnings/provider/luma
            -> org/acme/actor/alice/learnings/provider/luma.json
        """
        # Remove leading slash and convert to path
        path = namespace.strip("/")
        return f"{path}.json"

    @classmethod
    def validate_access(
        cls,
        namespace: str,
        actor_org_id: str,
        actor_id: str,
        action: str,  # "read", "write", "delete"
        roles: List[str],
    ) -> bool:
        """
        Validate if an actor can perform an action on a namespace.

        This is a client-side check. AgentCore IAM provides server-side enforcement.

        Args:
            namespace: Target namespace
            actor_org_id: Actor's organization
            actor_id: Actor's ID
            action: "read", "write", or "delete"
            roles: Actor's roles (e.g., ["org_member", "org_curator"])

        Returns:
            True if access is allowed
        """
        parsed = cls.parse(namespace)

        # Platform access
        if cls.is_platform_namespace(namespace):
            if action == "read":
                return True  # Everyone can read platform
            if action in ("write", "delete"):
                return "platform_admin" in roles or "platform_curator" in roles

        # Org access
        ns_org_id = parsed.get("org_id")
        if ns_org_id and ns_org_id != actor_org_id:
            return False  # Cannot access other orgs

        # User-level namespace
        ns_actor_id = parsed.get("actor_id")
        if ns_actor_id:
            if ns_actor_id == actor_id:
                return True  # Own namespace
            if action == "read" and "org_admin" in roles:
                return True  # Org admins can read others
            return False  # Cannot access other users

        # Org-level namespace
        if action == "read":
            return True  # Org members can read org learnings
        if action in ("write", "delete"):
            return "org_admin" in roles or "org_curator" in roles

        return False


# ==========================================================================
# PROMOTION RULES
# ==========================================================================

@dataclass
class PromotionRule:
    """Rule for automatic promotion of learnings"""
    from_level: NamespaceLevel
    to_level: NamespaceLevel
    min_validations: int
    min_confidence: float
    min_sources: int  # Number of users/orgs with same pattern
    similarity_threshold: float
    requires_approval: bool


PROMOTION_RULES = {
    "session_to_user": PromotionRule(
        from_level=NamespaceLevel.SESSION,
        to_level=NamespaceLevel.USER,
        min_validations=3,
        min_confidence=0.7,
        min_sources=1,
        similarity_threshold=0.0,
        requires_approval=False,
    ),
    "user_to_org": PromotionRule(
        from_level=NamespaceLevel.USER,
        to_level=NamespaceLevel.ORG,
        min_validations=5,
        min_confidence=0.8,
        min_sources=3,  # 3+ users
        similarity_threshold=0.9,
        requires_approval=True,
    ),
    "org_to_platform": PromotionRule(
        from_level=NamespaceLevel.ORG,
        to_level=NamespaceLevel.PLATFORM,
        min_validations=10,
        min_confidence=0.9,
        min_sources=3,  # 3+ orgs
        similarity_threshold=0.95,
        requires_approval=True,
    ),
}


def get_promotion_target(
    current_namespace: str,
    ctx: NamespaceContext,
    provider: Optional[str] = None,
) -> Optional[str]:
    """
    Get the target namespace for promoting a learning.

    Returns None if already at highest level.
    """
    ns = MultiTenantNamespaceBuilder
    parsed = ns.parse(current_namespace)
    current_level = parsed.get("level")

    if current_level == NamespaceLevel.SESSION:
        if provider:
            return ns.for_provider_learnings(provider, NamespaceLevel.USER, ctx)
        return ns.for_global_learnings(NamespaceLevel.USER, ctx)

    elif current_level == NamespaceLevel.USER:
        if provider:
            return ns.for_provider_learnings(provider, NamespaceLevel.ORG, ctx)
        return ns.for_global_learnings(NamespaceLevel.ORG, ctx)

    elif current_level == NamespaceLevel.ORG:
        if provider:
            return ns.for_provider_learnings(provider, NamespaceLevel.PLATFORM, ctx)
        return ns.for_global_learnings(NamespaceLevel.PLATFORM, ctx)

    return None  # Already at platform level
