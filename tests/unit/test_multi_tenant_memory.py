"""Unit tests for multi-tenant memory system"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from core.memory.namespace import (
    MultiTenantNamespaceBuilder,
    NamespaceContext,
    NamespaceLevel,
    NamespaceType,
    PromotionRule,
    PROMOTION_RULES,
    get_promotion_target,
)
from core.memory.backends.base import MemoryRecord, RetrievalResult, MemoryBackend
from core.memory.backends.local import LocalMemoryBackend
from core.memory.multi_tenant_manager import (
    MultiTenantMemoryManager,
    MultiTenantConfig,
    MemoryMode,
    LearningRecord,
    get_memory_manager,
    reset_memory_manager,
)


# =============================================================================
# NAMESPACE TESTS
# =============================================================================


class TestNamespaceContext:
    """Tests for NamespaceContext"""

    def test_context_creation(self):
        """Test creating a namespace context"""
        ctx = NamespaceContext(org_id="acme", actor_id="user123")

        assert ctx.org_id == "acme"
        assert ctx.actor_id == "user123"
        assert ctx.session_id is None

    def test_context_with_session(self):
        """Test context with session ID"""
        ctx = NamespaceContext(
            org_id="acme",
            actor_id="user123",
            session_id="sess-456"
        )

        assert ctx.session_id == "sess-456"

    def test_local_dev_factory(self):
        """Test local development context factory"""
        ctx = NamespaceContext.local_dev()

        assert ctx.org_id == "local"
        assert ctx.actor_id == "dev"

    def test_local_dev_with_session(self):
        """Test local dev context with session"""
        ctx = NamespaceContext.local_dev(session_id="test-session")

        assert ctx.org_id == "local"
        assert ctx.session_id == "test-session"


class TestNamespaceBuilder:
    """Tests for MultiTenantNamespaceBuilder"""

    def test_build_platform_namespace(self):
        """Test building platform-level namespace"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.build(ns.PLATFORM_LEARNINGS_GLOBAL, ctx)

        assert result == "/platform/learnings/global"

    def test_build_org_namespace(self):
        """Test building org-level namespace"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.build(ns.ORG_LEARNINGS_GLOBAL, ctx)

        assert result == "/org/acme/learnings/global"

    def test_build_user_namespace(self):
        """Test building user-level namespace"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.build(ns.USER_LEARNINGS_GLOBAL, ctx)

        assert result == "/org/acme/actor/user1/learnings/global"

    def test_build_provider_namespace(self):
        """Test building provider-specific namespace"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.for_provider_learnings("luma", NamespaceLevel.USER, ctx)

        assert result == "/org/acme/actor/user1/learnings/provider/luma"

    def test_build_provider_namespace_org_level(self):
        """Test building provider namespace at org level"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.for_provider_learnings("runway", NamespaceLevel.ORG, ctx)

        assert result == "/org/acme/learnings/provider/runway"

    def test_build_provider_namespace_platform_level(self):
        """Test building provider namespace at platform level"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        result = ns.for_provider_learnings("luma", NamespaceLevel.PLATFORM, ctx)

        assert result == "/platform/learnings/provider/luma"

    def test_get_retrieval_namespaces(self):
        """Test getting retrieval namespaces with priorities"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")
        ns = MultiTenantNamespaceBuilder

        namespaces = ns.get_retrieval_namespaces("luma", ctx, include_session=False)

        # Platform (global + provider), Org (global + provider), User (global + provider)
        assert len(namespaces) == 6

        # Check priorities are correct - find by type and level
        platform_global = next(n for n in namespaces if n["level"] == NamespaceLevel.PLATFORM and n["type"] == "global")
        platform_provider = next(n for n in namespaces if n["level"] == NamespaceLevel.PLATFORM and n["type"] == "provider")
        org_global = next(n for n in namespaces if n["level"] == NamespaceLevel.ORG and n["type"] == "global")
        user_provider = next(n for n in namespaces if n["level"] == NamespaceLevel.USER and n["type"] == "provider")

        assert platform_global["priority"] == 1.0
        assert platform_provider["priority"] == 0.95
        assert org_global["priority"] == 0.85
        assert user_provider["priority"] == 0.65

    def test_get_retrieval_namespaces_with_session(self):
        """Test retrieval namespaces include session when specified"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1", session_id="sess1")
        ns = MultiTenantNamespaceBuilder

        namespaces = ns.get_retrieval_namespaces("luma", ctx, include_session=True)

        # Platform (global + provider), Org (global + provider), User (global + provider), Session
        assert len(namespaces) == 7
        levels = [n["level"] for n in namespaces]
        assert NamespaceLevel.SESSION in levels

    def test_parse_namespace(self):
        """Test parsing namespace into components"""
        ns = MultiTenantNamespaceBuilder

        result = ns.parse("/org/acme/actor/user1/learnings/provider/luma")

        assert result["level"] == NamespaceLevel.USER
        assert result["type"] == NamespaceType.LEARNINGS_PROVIDER
        assert result["org_id"] == "acme"
        assert result["actor_id"] == "user1"
        assert result["provider_id"] == "luma"

    def test_parse_platform_namespace(self):
        """Test parsing platform namespace"""
        ns = MultiTenantNamespaceBuilder

        result = ns.parse("/platform/learnings/global")

        assert result["level"] == NamespaceLevel.PLATFORM
        assert result["type"] == NamespaceType.LEARNINGS_GLOBAL

    def test_validate_access_platform_admin(self):
        """Test platform admin has full access"""
        ns = MultiTenantNamespaceBuilder

        # Platform admin can read platform learnings
        assert ns.validate_access(
            "/platform/learnings/global",
            actor_org_id="acme",
            actor_id="admin1",
            action="read",
            roles=["platform_admin"],
        )

        # Platform admin can write platform learnings
        assert ns.validate_access(
            "/platform/learnings/global",
            actor_org_id="acme",
            actor_id="admin1",
            action="write",
            roles=["platform_admin"],
        )

    def test_validate_access_org_member(self):
        """Test org member access restrictions"""
        ns = MultiTenantNamespaceBuilder

        # Can read platform learnings
        assert ns.validate_access(
            "/platform/learnings/global",
            actor_org_id="acme",
            actor_id="user1",
            action="read",
            roles=["org_member"],
        )

        # Cannot write to platform
        assert not ns.validate_access(
            "/platform/learnings/global",
            actor_org_id="acme",
            actor_id="user1",
            action="write",
            roles=["org_member"],
        )

        # Can write to own user namespace
        assert ns.validate_access(
            "/org/acme/actor/user1/learnings/global",
            actor_org_id="acme",
            actor_id="user1",
            action="write",
            roles=["org_member"],
        )

    def test_validate_access_wrong_org(self):
        """Test cross-org access is denied"""
        ns = MultiTenantNamespaceBuilder

        # Cannot read other org's data
        assert not ns.validate_access(
            "/org/other_org/learnings/global",
            actor_org_id="acme",
            actor_id="user1",
            action="read",
            roles=["org_member"],
        )


class TestPromotionRules:
    """Tests for learning promotion rules"""

    def test_promotion_rules_exist(self):
        """Test that promotion rules are defined"""
        assert "session_to_user" in PROMOTION_RULES
        assert "user_to_org" in PROMOTION_RULES
        assert "org_to_platform" in PROMOTION_RULES

    def test_promotion_rule_thresholds(self):
        """Test promotion thresholds increase at higher levels"""
        session_rule = PROMOTION_RULES["session_to_user"]
        user_rule = PROMOTION_RULES["user_to_org"]
        org_rule = PROMOTION_RULES["org_to_platform"]

        # Higher level promotions require more validations
        assert session_rule.min_validations <= user_rule.min_validations
        assert user_rule.min_validations <= org_rule.min_validations

    def test_org_to_platform_requires_approval(self):
        """Test that platform promotion requires approval"""
        org_rule = PROMOTION_RULES["org_to_platform"]

        assert org_rule.requires_approval is True

    def test_get_promotion_target(self):
        """Test getting promotion target namespace"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")

        # User -> Org promotion
        target = get_promotion_target(
            "/org/acme/actor/user1/learnings/provider/luma",
            ctx,
            provider="luma"
        )

        assert target == "/org/acme/learnings/provider/luma"

    def test_get_promotion_target_platform_returns_none(self):
        """Test that platform level has no promotion target"""
        ctx = NamespaceContext(org_id="acme", actor_id="user1")

        target = get_promotion_target(
            "/platform/learnings/provider/luma",
            ctx,
            provider="luma"
        )

        assert target is None


# =============================================================================
# MEMORY RECORD TESTS
# =============================================================================


class TestMemoryRecord:
    """Tests for MemoryRecord dataclass"""

    def test_record_creation(self):
        """Test creating a memory record"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"key": "value"},
            created_by="user1",
        )

        assert record.namespace == "/test/namespace"
        assert record.content == {"key": "value"}
        assert record.created_by == "user1"
        assert record.validations == 0
        assert record.confidence == 0.0

    def test_record_serialization(self):
        """Test record serialization to dict"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"pattern": "test pattern"},
            text_content="searchable text",
            tags=["tag1", "tag2"],
        )

        data = record.to_dict()

        assert data["namespace"] == "/test/namespace"
        assert data["content"] == {"pattern": "test pattern"}
        assert data["text_content"] == "searchable text"
        assert data["tags"] == ["tag1", "tag2"]

    def test_record_deserialization(self):
        """Test record deserialization from dict"""
        data = {
            "record_id": "test-id",
            "namespace": "/test/namespace",
            "content": {"key": "value"},
            "validations": 5,
            "confidence": 0.8,
            "tags": ["learning"],
        }

        record = MemoryRecord.from_dict(data)

        assert record.record_id == "test-id"
        assert record.namespace == "/test/namespace"
        assert record.validations == 5
        assert record.confidence == 0.8

    def test_record_with_promotion_history(self):
        """Test record with promotion history"""
        record = MemoryRecord(
            namespace="/org/acme/learnings/global",
            content={"pattern": "promoted pattern"},
            promoted_from="original-id",
            promotion_history=[
                {
                    "from_namespace": "/org/acme/actor/user1/learnings/global",
                    "promoted_at": "2024-01-01T00:00:00",
                    "promoted_by": "system",
                }
            ],
        )

        assert record.promoted_from == "original-id"
        assert len(record.promotion_history) == 1


# =============================================================================
# LOCAL BACKEND TESTS
# =============================================================================


class TestLocalMemoryBackend:
    """Tests for LocalMemoryBackend"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def backend(self, temp_dir):
        """Create a backend with temporary storage"""
        return LocalMemoryBackend(base_path=temp_dir)

    @pytest.mark.asyncio
    async def test_create_record(self, backend):
        """Test creating a record"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"key": "value"},
        )

        record_id = await backend.create(record)

        assert record_id is not None
        assert len(record_id) > 0

    @pytest.mark.asyncio
    async def test_get_record(self, backend):
        """Test retrieving a record"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"key": "value"},
        )
        record_id = await backend.create(record)

        retrieved = await backend.get("/test/namespace", record_id)

        assert retrieved is not None
        assert retrieved.content == {"key": "value"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_record(self, backend):
        """Test getting a record that doesn't exist"""
        result = await backend.get("/test/namespace", "nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_record(self, backend):
        """Test updating a record"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"key": "original"},
        )
        record_id = await backend.create(record)

        # Update the record
        record.content = {"key": "updated"}
        success = await backend.update(record)

        assert success is True

        # Verify update
        retrieved = await backend.get("/test/namespace", record_id)
        assert retrieved.content == {"key": "updated"}

    @pytest.mark.asyncio
    async def test_delete_record(self, backend):
        """Test deleting a record"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"key": "value"},
        )
        record_id = await backend.create(record)

        success = await backend.delete("/test/namespace", record_id)

        assert success is True

        # Verify deletion
        retrieved = await backend.get("/test/namespace", record_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_records(self, backend):
        """Test listing records in a namespace"""
        # Create multiple records
        for i in range(5):
            record = MemoryRecord(
                namespace="/test/namespace",
                content={"index": i},
            )
            await backend.create(record)

        records = await backend.list("/test/namespace")

        assert len(records) == 5

    @pytest.mark.asyncio
    async def test_list_with_tags(self, backend):
        """Test listing records filtered by tags"""
        record1 = MemoryRecord(
            namespace="/test/namespace",
            content={"name": "record1"},
            tags=["important", "luma"],
        )
        record2 = MemoryRecord(
            namespace="/test/namespace",
            content={"name": "record2"},
            tags=["luma"],
        )
        record3 = MemoryRecord(
            namespace="/test/namespace",
            content={"name": "record3"},
            tags=["runway"],
        )

        await backend.create(record1)
        await backend.create(record2)
        await backend.create(record3)

        # Filter by tag
        records = await backend.list("/test/namespace", tags=["important"])

        assert len(records) == 1
        assert records[0].content["name"] == "record1"

    @pytest.mark.asyncio
    async def test_search_records(self, backend):
        """Test searching records by text"""
        record1 = MemoryRecord(
            namespace="/test/namespace",
            content={"pattern": "use concrete nouns"},
            text_content="use concrete nouns for better results",
        )
        record2 = MemoryRecord(
            namespace="/test/namespace",
            content={"pattern": "avoid abstract concepts"},
            text_content="avoid abstract concepts in prompts",
        )

        await backend.create(record1)
        await backend.create(record2)

        results = await backend.search(
            namespaces=["/test/namespace"],
            query="concrete nouns"
        )

        assert len(results) >= 1
        # First result should be the one with "concrete nouns"
        assert "concrete" in results[0].record.text_content

    @pytest.mark.asyncio
    async def test_namespace_exists(self, backend):
        """Test checking if namespace exists"""
        # Should not exist initially
        exists = await backend.namespace_exists("/test/new_namespace")
        assert exists is False

        # Create a record
        record = MemoryRecord(
            namespace="/test/new_namespace",
            content={"key": "value"},
        )
        await backend.create(record)

        # Should exist now
        exists = await backend.namespace_exists("/test/new_namespace")
        assert exists is True

    @pytest.mark.asyncio
    async def test_delete_namespace(self, backend):
        """Test deleting all records in a namespace"""
        # Create records
        for i in range(3):
            record = MemoryRecord(
                namespace="/test/to_delete",
                content={"index": i},
            )
            await backend.create(record)

        count = await backend.delete_namespace("/test/to_delete")

        assert count == 3

        # Verify deletion
        records = await backend.list("/test/to_delete")
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_increment_validation(self, backend):
        """Test incrementing validation count"""
        record = MemoryRecord(
            namespace="/test/namespace",
            content={"pattern": "test"},
        )
        record_id = await backend.create(record)

        # Increment validation
        updated = await backend.increment_validation("/test/namespace", record_id)

        assert updated.validations == 1
        assert updated.confidence > 0

    @pytest.mark.asyncio
    async def test_list_namespaces(self, backend):
        """Test listing all namespaces"""
        # Create records in different namespaces
        await backend.create(MemoryRecord(
            namespace="/platform/learnings",
            content={"key": "value"},
        ))
        await backend.create(MemoryRecord(
            namespace="/org/acme/learnings",
            content={"key": "value"},
        ))

        namespaces = await backend.list_namespaces()

        assert len(namespaces) >= 2
        assert "/platform/learnings" in namespaces
        assert "/org/acme/learnings" in namespaces


# =============================================================================
# MULTI-TENANT MANAGER TESTS
# =============================================================================


class TestMultiTenantConfig:
    """Tests for MultiTenantConfig"""

    def test_default_config(self):
        """Test default configuration"""
        config = MultiTenantConfig()

        assert config.mode == MemoryMode.LOCAL
        assert config.default_org_id == "local"
        assert config.default_actor_id == "dev"

    def test_config_from_env_local(self, monkeypatch):
        """Test config from environment (local mode)"""
        # Ensure no AgentCore env var
        monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)

        config = MultiTenantConfig.from_env()

        assert config.mode == MemoryMode.LOCAL


class TestMultiTenantMemoryManager:
    """Tests for MultiTenantMemoryManager"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create a manager with temporary storage"""
        config = MultiTenantConfig(
            mode=MemoryMode.LOCAL,
            base_path=temp_dir,
            default_org_id="test_org",
            default_actor_id="test_user",
        )
        return MultiTenantMemoryManager(config)

    def test_get_context(self, manager):
        """Test getting namespace context"""
        ctx = manager.get_context()

        assert ctx.org_id == "test_org"
        assert ctx.actor_id == "test_user"

    def test_get_context_override(self, manager):
        """Test getting context with overrides"""
        ctx = manager.get_context(org_id="other_org", actor_id="other_user")

        assert ctx.org_id == "other_org"
        assert ctx.actor_id == "other_user"

    @pytest.mark.asyncio
    async def test_store_provider_learning(self, manager):
        """Test storing a provider learning"""
        ctx = manager.get_context()

        record_id = await manager.store_provider_learning(
            provider="luma",
            learning={
                "pattern": "use concrete nouns",
                "effectiveness": 0.85,
            },
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        assert record_id is not None

    @pytest.mark.asyncio
    async def test_get_provider_learnings(self, manager):
        """Test retrieving provider learnings"""
        ctx = manager.get_context()

        # Store a learning
        await manager.store_provider_learning(
            provider="luma",
            learning={"pattern": "test pattern"},
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        # Retrieve learnings
        learnings = await manager.get_provider_learnings("luma", ctx)

        assert len(learnings) >= 1
        assert learnings[0].content.get("pattern") == "test pattern"

    @pytest.mark.asyncio
    async def test_search_learnings(self, manager):
        """Test searching learnings"""
        ctx = manager.get_context()

        # Store learnings
        await manager.store_provider_learning(
            provider="luma",
            learning={"pattern": "concrete nouns work best"},
            text_content="concrete nouns work best for video generation",
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        # Search
        results = await manager.search_learnings(
            query="concrete nouns",
            provider="luma",
            ctx=ctx,
        )

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_learning_record_has_priority(self, manager):
        """Test that learning records have priority from namespace level"""
        ctx = manager.get_context()

        await manager.store_provider_learning(
            provider="luma",
            learning={"pattern": "test"},
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        learnings = await manager.get_provider_learnings("luma", ctx)

        # User level provider namespace has priority 0.65
        assert learnings[0].level == NamespaceLevel.USER
        assert learnings[0].priority == 0.65

    @pytest.mark.asyncio
    async def test_preferences(self, manager):
        """Test storing and retrieving preferences"""
        ctx = manager.get_context()

        # Set preferences
        await manager.set_preferences(
            {"default_provider": "luma", "quality": "high"},
            ctx=ctx,
        )

        # Get preferences
        prefs = await manager.get_preferences(ctx)

        assert prefs.get("default_provider") == "luma"
        assert prefs.get("quality") == "high"

    @pytest.mark.asyncio
    async def test_validate_learning(self, manager):
        """Test validating a learning"""
        ctx = manager.get_context()

        # Store a learning
        record_id = await manager.store_provider_learning(
            provider="luma",
            learning={"pattern": "test"},
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        namespace = MultiTenantNamespaceBuilder.for_provider_learnings(
            "luma", NamespaceLevel.USER, ctx
        )

        # Validate it
        updated = await manager.validate_learning(
            record_id=record_id,
            namespace=namespace,
            success=True,
        )

        assert updated is not None
        assert updated.validations == 1
        assert updated.confidence > 0

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        """Test getting memory stats"""
        ctx = manager.get_context()

        # Create some records
        await manager.store_provider_learning(
            provider="luma",
            learning={"pattern": "test1"},
            level=NamespaceLevel.USER,
            ctx=ctx,
        )
        await manager.store_provider_learning(
            provider="runway",
            learning={"pattern": "test2"},
            level=NamespaceLevel.USER,
            ctx=ctx,
        )

        stats = await manager.get_stats()

        assert "total_namespaces" in stats
        assert "total_records" in stats
        assert stats["total_records"] >= 2


class TestGlobalManager:
    """Tests for global manager singleton"""

    def test_get_memory_manager(self):
        """Test getting global manager"""
        reset_memory_manager()

        manager = get_memory_manager()

        assert manager is not None
        assert isinstance(manager, MultiTenantMemoryManager)

    def test_manager_is_singleton(self):
        """Test that manager is a singleton"""
        reset_memory_manager()

        manager1 = get_memory_manager()
        manager2 = get_memory_manager()

        assert manager1 is manager2

    def test_reset_manager(self):
        """Test resetting the global manager"""
        reset_memory_manager()
        manager1 = get_memory_manager()

        reset_memory_manager()
        manager2 = get_memory_manager()

        assert manager1 is not manager2
