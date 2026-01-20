"""
Local JSON file storage backend for development.

Stores memory records as JSON files following the namespace hierarchy:
    artifacts/memory/platform/learnings/global.json
    artifacts/memory/org/acme/learnings/provider/luma.json
    etc.

This allows:
- Same namespace logic in local and production
- Easy migration to AgentCore
- File-based inspection during development
- Git-trackable platform learnings (seed data)
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

from core.memory.backends.base import MemoryBackend, MemoryRecord, RetrievalResult
from core.memory.namespace import MultiTenantNamespaceBuilder


class LocalMemoryBackend(MemoryBackend):
    """
    Local file-based memory backend using JSON files.

    Stores each namespace as a JSON file containing an array of records.
    Thread-safe via asyncio locks.
    """

    def __init__(self, base_path: str = "artifacts/memory"):
        """
        Initialize local backend.

        Args:
            base_path: Base directory for memory files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cache: Dict[str, List[MemoryRecord]] = {}

    def _get_lock(self, namespace: str) -> asyncio.Lock:
        """Get or create a lock for a namespace"""
        if namespace not in self._locks:
            self._locks[namespace] = asyncio.Lock()
        return self._locks[namespace]

    def _namespace_to_path(self, namespace: str) -> Path:
        """Convert namespace to file path"""
        # Remove leading slash and convert to path
        path_str = namespace.strip("/")
        return self.base_path / f"{path_str}.json"

    async def _load_namespace(self, namespace: str) -> List[MemoryRecord]:
        """Load all records from a namespace file"""
        file_path = self._namespace_to_path(namespace)

        if not file_path.exists():
            return []

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            if isinstance(data, list):
                return [MemoryRecord.from_dict(d) for d in data]
            elif isinstance(data, dict) and "records" in data:
                return [MemoryRecord.from_dict(d) for d in data["records"]]
            else:
                # Legacy format - single record
                return [MemoryRecord.from_dict(data)]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Error loading {file_path}: {e}")
            return []

    async def _save_namespace(self, namespace: str, records: List[MemoryRecord]):
        """Save all records to a namespace file"""
        file_path = self._namespace_to_path(namespace)

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "namespace": namespace,
            "updated_at": datetime.utcnow().isoformat(),
            "record_count": len(records),
            "records": [r.to_dict() for r in records]
        }

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        # Update cache
        self._cache[namespace] = records

    async def create(self, record: MemoryRecord) -> str:
        """Create a new memory record"""
        async with self._get_lock(record.namespace):
            records = await self._load_namespace(record.namespace)

            # Ensure unique ID
            existing_ids = {r.record_id for r in records}
            while record.record_id in existing_ids:
                import uuid
                record.record_id = str(uuid.uuid4())

            record.created_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            records.append(record)

            await self._save_namespace(record.namespace, records)
            return record.record_id

    async def get(self, namespace: str, record_id: str) -> Optional[MemoryRecord]:
        """Get a specific record by ID"""
        records = await self._load_namespace(namespace)
        for record in records:
            if record.record_id == record_id:
                return record
        return None

    async def update(self, record: MemoryRecord) -> bool:
        """Update an existing record"""
        async with self._get_lock(record.namespace):
            records = await self._load_namespace(record.namespace)

            for i, r in enumerate(records):
                if r.record_id == record.record_id:
                    record.updated_at = datetime.utcnow()
                    records[i] = record
                    await self._save_namespace(record.namespace, records)
                    return True

            return False

    async def delete(self, namespace: str, record_id: str) -> bool:
        """Delete a record"""
        async with self._get_lock(namespace):
            records = await self._load_namespace(namespace)
            initial_count = len(records)

            records = [r for r in records if r.record_id != record_id]

            if len(records) < initial_count:
                await self._save_namespace(namespace, records)
                return True

            return False

    async def list(
        self,
        namespace: str,
        limit: int = 100,
        offset: int = 0,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryRecord]:
        """List records in a namespace"""
        records = await self._load_namespace(namespace)

        # Filter by tags if specified
        if tags:
            records = [
                r for r in records
                if any(tag in r.tags for tag in tags)
            ]

        # Sort by created_at descending (newest first)
        records.sort(key=lambda r: r.created_at or datetime.min, reverse=True)

        # Apply pagination
        return records[offset:offset + limit]

    async def search(
        self,
        namespaces: List[str],
        query: str,
        top_k: int = 10,
        tags: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        """
        Search for records across namespaces using text matching.

        For local backend, this does simple text search on text_content and content.
        For semantic search, use AgentCore backend.
        """
        results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for namespace in namespaces:
            try:
                records = await self._load_namespace(namespace)
            except Exception:
                continue

            for record in records:
                # Filter by tags if specified
                if tags and not any(tag in record.tags for tag in tags):
                    continue

                # Calculate relevance score based on text matching
                score = self._calculate_relevance(record, query_lower, query_words)

                if score > 0:
                    results.append(RetrievalResult(
                        record=record,
                        score=score,
                        source_namespace=namespace,
                    ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:top_k]

    def _calculate_relevance(
        self,
        record: MemoryRecord,
        query_lower: str,
        query_words: set
    ) -> float:
        """Calculate relevance score for a record"""
        score = 0.0

        # Check text_content
        if record.text_content:
            text_lower = record.text_content.lower()
            if query_lower in text_lower:
                score += 1.0  # Exact match
            else:
                # Word overlap
                text_words = set(text_lower.split())
                overlap = len(query_words & text_words)
                if overlap > 0:
                    score += 0.5 * (overlap / len(query_words))

        # Check content dict (recursive search)
        content_text = self._extract_text_from_content(record.content).lower()
        if content_text:
            if query_lower in content_text:
                score += 0.8
            else:
                content_words = set(content_text.split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    score += 0.3 * (overlap / len(query_words))

        # Check tags
        for tag in record.tags:
            if query_lower in tag.lower():
                score += 0.2

        return min(1.0, score)

    def _extract_text_from_content(self, content: Any, max_depth: int = 3) -> str:
        """Recursively extract text from content dict"""
        if max_depth <= 0:
            return ""

        if isinstance(content, str):
            return content
        elif isinstance(content, dict):
            parts = []
            for value in content.values():
                parts.append(self._extract_text_from_content(value, max_depth - 1))
            return " ".join(parts)
        elif isinstance(content, list):
            parts = []
            for item in content[:10]:  # Limit list items
                parts.append(self._extract_text_from_content(item, max_depth - 1))
            return " ".join(parts)
        else:
            return str(content) if content else ""

    async def namespace_exists(self, namespace: str) -> bool:
        """Check if a namespace has any records"""
        file_path = self._namespace_to_path(namespace)
        if not file_path.exists():
            return False

        records = await self._load_namespace(namespace)
        return len(records) > 0

    async def delete_namespace(self, namespace: str) -> int:
        """Delete all records in a namespace"""
        async with self._get_lock(namespace):
            file_path = self._namespace_to_path(namespace)

            if not file_path.exists():
                return 0

            records = await self._load_namespace(namespace)
            count = len(records)

            file_path.unlink()

            # Clear cache
            if namespace in self._cache:
                del self._cache[namespace]

            return count

    # ==========================================================================
    # LOCAL-SPECIFIC METHODS
    # ==========================================================================

    async def list_namespaces(self, prefix: str = "") -> List[str]:
        """
        List all namespaces (for debugging/admin).

        Args:
            prefix: Optional namespace prefix to filter

        Returns:
            List of namespace strings
        """
        namespaces = []

        for json_file in self.base_path.rglob("*.json"):
            # Convert path back to namespace
            rel_path = json_file.relative_to(self.base_path)
            namespace = "/" + str(rel_path.with_suffix("")).replace("\\", "/")

            if prefix and not namespace.startswith(prefix):
                continue

            namespaces.append(namespace)

        return sorted(namespaces)

    async def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Export all records for backup/migration.

        Returns:
            Dict mapping namespace to list of record dicts
        """
        result = {}
        namespaces = await self.list_namespaces()

        for namespace in namespaces:
            records = await self._load_namespace(namespace)
            result[namespace] = [r.to_dict() for r in records]

        return result

    async def import_all(self, data: Dict[str, List[Dict[str, Any]]]):
        """
        Import records from backup/migration.

        Args:
            data: Dict mapping namespace to list of record dicts
        """
        for namespace, records in data.items():
            for record_data in records:
                record = MemoryRecord.from_dict(record_data)
                record.namespace = namespace
                await self.create(record)

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        namespaces = await self.list_namespaces()
        total_records = 0
        total_size = 0

        namespace_stats = []
        for namespace in namespaces:
            file_path = self._namespace_to_path(namespace)
            records = await self._load_namespace(namespace)
            size = file_path.stat().st_size if file_path.exists() else 0

            total_records += len(records)
            total_size += size

            namespace_stats.append({
                "namespace": namespace,
                "record_count": len(records),
                "size_bytes": size,
            })

        return {
            "total_namespaces": len(namespaces),
            "total_records": total_records,
            "total_size_bytes": total_size,
            "namespaces": namespace_stats,
        }
