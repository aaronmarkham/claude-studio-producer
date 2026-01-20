"""
Abstract base class for memory storage backends.

Supports both local JSON storage and AWS AgentCore Memory.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid


@dataclass
class MemoryRecord:
    """
    A single memory record that can be stored in any backend.

    Compatible with AgentCore Memory record format.
    """
    # Core fields
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    namespace: str = ""
    content: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None  # Actor ID

    # For semantic search (optional)
    text_content: Optional[str] = None  # Searchable text representation
    embedding: Optional[List[float]] = None  # Vector embedding

    # Validation/promotion tracking
    validations: int = 0
    confidence: float = 0.0
    promoted_from: Optional[str] = None  # Original record_id if promoted
    promotion_history: List[Dict[str, Any]] = field(default_factory=list)

    # Tags for filtering
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "record_id": self.record_id,
            "namespace": self.namespace,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "text_content": self.text_content,
            "validations": self.validations,
            "confidence": self.confidence,
            "promoted_from": self.promoted_from,
            "promotion_history": self.promotion_history,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryRecord':
        """Deserialize from dict"""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.utcnow()

        return cls(
            record_id=data.get("record_id", str(uuid.uuid4())),
            namespace=data.get("namespace", ""),
            content=data.get("content", {}),
            created_at=created_at,
            updated_at=updated_at,
            created_by=data.get("created_by"),
            text_content=data.get("text_content"),
            embedding=data.get("embedding"),
            validations=data.get("validations", 0),
            confidence=data.get("confidence", 0.0),
            promoted_from=data.get("promoted_from"),
            promotion_history=data.get("promotion_history", []),
            tags=data.get("tags", []),
        )


@dataclass
class RetrievalResult:
    """Result from a memory retrieval operation"""
    record: MemoryRecord
    score: float = 1.0  # Relevance score (1.0 for exact match, lower for semantic)
    source_namespace: str = ""


class MemoryBackend(ABC):
    """
    Abstract base class for memory storage backends.

    Implementations:
    - LocalMemoryBackend: JSON file storage for development
    - AgentCoreMemoryBackend: AWS AgentCore Memory for production
    """

    @abstractmethod
    async def create(self, record: MemoryRecord) -> str:
        """
        Create a new memory record.

        Args:
            record: The record to create

        Returns:
            The record_id of the created record
        """
        pass

    @abstractmethod
    async def get(self, namespace: str, record_id: str) -> Optional[MemoryRecord]:
        """
        Get a specific record by ID.

        Args:
            namespace: The namespace to look in
            record_id: The record ID to retrieve

        Returns:
            The record if found, None otherwise
        """
        pass

    @abstractmethod
    async def update(self, record: MemoryRecord) -> bool:
        """
        Update an existing record.

        Args:
            record: The record with updated values

        Returns:
            True if updated, False if not found
        """
        pass

    @abstractmethod
    async def delete(self, namespace: str, record_id: str) -> bool:
        """
        Delete a record.

        Args:
            namespace: The namespace containing the record
            record_id: The record ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def list(
        self,
        namespace: str,
        limit: int = 100,
        offset: int = 0,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryRecord]:
        """
        List records in a namespace.

        Args:
            namespace: The namespace to list
            limit: Maximum records to return
            offset: Number of records to skip
            tags: Optional tag filter

        Returns:
            List of matching records
        """
        pass

    @abstractmethod
    async def search(
        self,
        namespaces: List[str],
        query: str,
        top_k: int = 10,
        tags: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        """
        Search for records across namespaces.

        For local backend, this is a text search.
        For AgentCore, this uses semantic search with embeddings.

        Args:
            namespaces: Namespaces to search
            query: Search query
            top_k: Maximum results to return
            tags: Optional tag filter

        Returns:
            List of matching results with scores
        """
        pass

    @abstractmethod
    async def namespace_exists(self, namespace: str) -> bool:
        """
        Check if a namespace has any records.

        Args:
            namespace: The namespace to check

        Returns:
            True if namespace exists and has records
        """
        pass

    @abstractmethod
    async def delete_namespace(self, namespace: str) -> int:
        """
        Delete all records in a namespace.

        Args:
            namespace: The namespace to delete

        Returns:
            Number of records deleted
        """
        pass

    # ==========================================================================
    # HELPER METHODS (implemented in base class)
    # ==========================================================================

    async def get_or_create(
        self,
        namespace: str,
        content: Dict[str, Any],
        match_fields: List[str],
        **kwargs
    ) -> tuple[MemoryRecord, bool]:
        """
        Get an existing record or create a new one.

        Args:
            namespace: Namespace for the record
            content: Record content
            match_fields: Fields to match on for finding existing record
            **kwargs: Additional fields for MemoryRecord

        Returns:
            Tuple of (record, created) where created is True if new
        """
        # Try to find existing record
        existing = await self.list(namespace, limit=100)
        for record in existing:
            if all(
                record.content.get(field) == content.get(field)
                for field in match_fields
            ):
                return record, False

        # Create new record
        record = MemoryRecord(
            namespace=namespace,
            content=content,
            **kwargs
        )
        await self.create(record)
        return record, True

    async def increment_validation(
        self,
        namespace: str,
        record_id: str,
        success: bool = True
    ) -> Optional[MemoryRecord]:
        """
        Increment the validation count for a record.

        Args:
            namespace: Namespace of the record
            record_id: ID of the record
            success: Whether this was a successful validation

        Returns:
            Updated record if found
        """
        record = await self.get(namespace, record_id)
        if not record:
            return None

        record.validations += 1
        if record.validations > 0:
            # Update confidence based on success rate
            # Simple model: each success adds, each failure subtracts
            if success:
                record.confidence = min(1.0, record.confidence + 0.1)
            else:
                record.confidence = max(0.0, record.confidence - 0.1)

        record.updated_at = datetime.utcnow()
        await self.update(record)
        return record
