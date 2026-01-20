"""
AWS AgentCore Memory backend for production.

Uses AWS Bedrock AgentCore Memory for:
- Semantic search with embeddings
- IAM-based access control
- Scalable multi-tenant storage

This backend is only used when AWS_REGION and AgentCore credentials are configured.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from core.memory.backends.base import MemoryBackend, MemoryRecord, RetrievalResult

logger = logging.getLogger(__name__)


class AgentCoreMemoryBackend(MemoryBackend):
    """
    AWS AgentCore Memory backend for production multi-tenant deployment.

    Features:
    - Semantic search with automatic embedding generation
    - IAM policy-based namespace access control
    - Scalable cloud storage
    - Cross-account sharing for platform learnings

    Prerequisites:
    - AWS credentials with AgentCore permissions
    - Memory instance ID configured
    - IAM roles for different access levels

    Note: This is a placeholder implementation. The actual AgentCore API
    will need to be integrated when deploying to AWS.
    """

    def __init__(
        self,
        memory_id: str,
        region: str = "us-east-1",
        org_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ):
        """
        Initialize AgentCore backend.

        Args:
            memory_id: AgentCore Memory instance ID
            region: AWS region
            org_id: Organization ID (from IAM principal tag)
            actor_id: Actor ID (from IAM principal tag)
        """
        self.memory_id = memory_id
        self.region = region
        self.org_id = org_id
        self.actor_id = actor_id
        self._client = None

    def _get_client(self):
        """Lazy initialization of AgentCore client"""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    'bedrock-agentcore',
                    region_name=self.region
                )
            except ImportError:
                raise ImportError(
                    "boto3 is required for AgentCore backend. "
                    "Install with: pip install boto3"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to initialize AgentCore client: {e}")
        return self._client

    async def create(self, record: MemoryRecord) -> str:
        """
        Create a new memory record in AgentCore.

        Uses CreateMemoryRecord API with namespace as the key.
        """
        client = self._get_client()

        # Build request
        request = {
            "memoryId": self.memory_id,
            "namespace": record.namespace,
            "content": {
                "record_id": record.record_id,
                "content": record.content,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "created_by": record.created_by,
                "validations": record.validations,
                "confidence": record.confidence,
                "promoted_from": record.promoted_from,
                "tags": record.tags,
            }
        }

        # Add text content for semantic indexing
        if record.text_content:
            request["textContent"] = record.text_content

        try:
            response = client.create_memory_record(**request)
            return response.get("recordId", record.record_id)
        except Exception as e:
            logger.error(f"Failed to create record in AgentCore: {e}")
            raise

    async def get(self, namespace: str, record_id: str) -> Optional[MemoryRecord]:
        """Get a specific record by ID from AgentCore"""
        client = self._get_client()

        try:
            response = client.get_memory_record(
                memoryId=self.memory_id,
                namespace=namespace,
                recordId=record_id
            )

            if response and "content" in response:
                return self._response_to_record(response, namespace)
            return None

        except client.exceptions.ResourceNotFoundException:
            return None
        except Exception as e:
            logger.error(f"Failed to get record from AgentCore: {e}")
            raise

    async def update(self, record: MemoryRecord) -> bool:
        """Update an existing record in AgentCore"""
        client = self._get_client()

        request = {
            "memoryId": self.memory_id,
            "namespace": record.namespace,
            "recordId": record.record_id,
            "content": {
                "record_id": record.record_id,
                "content": record.content,
                "updated_at": datetime.utcnow().isoformat(),
                "validations": record.validations,
                "confidence": record.confidence,
                "tags": record.tags,
            }
        }

        if record.text_content:
            request["textContent"] = record.text_content

        try:
            client.update_memory_record(**request)
            return True
        except client.exceptions.ResourceNotFoundException:
            return False
        except Exception as e:
            logger.error(f"Failed to update record in AgentCore: {e}")
            raise

    async def delete(self, namespace: str, record_id: str) -> bool:
        """Delete a record from AgentCore"""
        client = self._get_client()

        try:
            client.delete_memory_record(
                memoryId=self.memory_id,
                namespace=namespace,
                recordId=record_id
            )
            return True
        except client.exceptions.ResourceNotFoundException:
            return False
        except Exception as e:
            logger.error(f"Failed to delete record from AgentCore: {e}")
            raise

    async def list(
        self,
        namespace: str,
        limit: int = 100,
        offset: int = 0,
        tags: Optional[List[str]] = None,
    ) -> List[MemoryRecord]:
        """List records in a namespace"""
        client = self._get_client()

        request = {
            "memoryId": self.memory_id,
            "namespace": namespace,
            "maxResults": limit,
        }

        if tags:
            request["filters"] = {"tags": tags}

        try:
            records = []
            paginator = client.get_paginator('list_memory_records')

            for page in paginator.paginate(**request):
                for item in page.get("records", []):
                    records.append(self._response_to_record(item, namespace))

            # Apply offset (pagination should handle this, but fallback)
            return records[offset:offset + limit]

        except Exception as e:
            logger.error(f"Failed to list records from AgentCore: {e}")
            raise

    async def search(
        self,
        namespaces: List[str],
        query: str,
        top_k: int = 10,
        tags: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        """
        Search for records using AgentCore's semantic search.

        AgentCore automatically generates embeddings for textContent
        and performs vector similarity search.
        """
        client = self._get_client()

        results = []

        for namespace in namespaces:
            request = {
                "memoryId": self.memory_id,
                "namespace": namespace,
                "query": query,
                "topK": top_k,
            }

            if tags:
                request["filters"] = {"tags": tags}

            try:
                response = client.retrieve_memory_records(**request)

                for item in response.get("records", []):
                    record = self._response_to_record(item, namespace)
                    score = item.get("score", 1.0)

                    results.append(RetrievalResult(
                        record=record,
                        score=score,
                        source_namespace=namespace,
                    ))

            except client.exceptions.ResourceNotFoundException:
                # Namespace doesn't exist, skip
                continue
            except Exception as e:
                logger.warning(f"Search failed for namespace {namespace}: {e}")
                continue

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def namespace_exists(self, namespace: str) -> bool:
        """Check if a namespace has any records"""
        try:
            records = await self.list(namespace, limit=1)
            return len(records) > 0
        except Exception:
            return False

    async def delete_namespace(self, namespace: str) -> int:
        """Delete all records in a namespace"""
        records = await self.list(namespace, limit=10000)
        count = 0

        for record in records:
            if await self.delete(namespace, record.record_id):
                count += 1

        return count

    def _response_to_record(
        self,
        response: Dict[str, Any],
        namespace: str
    ) -> MemoryRecord:
        """Convert AgentCore response to MemoryRecord"""
        content = response.get("content", {})

        return MemoryRecord(
            record_id=content.get("record_id", response.get("recordId", "")),
            namespace=namespace,
            content=content.get("content", {}),
            created_at=datetime.fromisoformat(content["created_at"])
            if content.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(content["updated_at"])
            if content.get("updated_at") else datetime.utcnow(),
            created_by=content.get("created_by"),
            text_content=response.get("textContent"),
            validations=content.get("validations", 0),
            confidence=content.get("confidence", 0.0),
            promoted_from=content.get("promoted_from"),
            promotion_history=content.get("promotion_history", []),
            tags=content.get("tags", []),
        )


def create_agentcore_backend(
    memory_id: Optional[str] = None,
    region: Optional[str] = None,
) -> Optional[AgentCoreMemoryBackend]:
    """
    Factory function to create AgentCore backend if configured.

    Returns None if AWS is not configured.
    """
    import os

    memory_id = memory_id or os.environ.get("AGENTCORE_MEMORY_ID")
    region = region or os.environ.get("AWS_REGION", "us-east-1")

    if not memory_id:
        return None

    try:
        return AgentCoreMemoryBackend(
            memory_id=memory_id,
            region=region,
            org_id=os.environ.get("AGENTCORE_ORG_ID"),
            actor_id=os.environ.get("AGENTCORE_ACTOR_ID"),
        )
    except Exception as e:
        logger.warning(f"Failed to create AgentCore backend: {e}")
        return None
