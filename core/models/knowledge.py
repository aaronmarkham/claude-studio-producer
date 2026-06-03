"""Knowledge models — now sourced from spiritwriter (single source of truth).

These models were consolidated into spiritwriter and are identical to the
former local copy. This module re-exports them so existing
``core.models.knowledge`` import sites keep working; new code should import
from ``spiritwriter.models.knowledge`` directly. Each importer migrates to
the spiritwriter path as its own module is ported.

See claude-studio-producer#15 / spiritwriter-core#76.
"""

from spiritwriter.models.knowledge import (
    SourceType,
    KnowledgeSource,
    CrossSourceLink,
    Note,
    Connection,
    KnowledgeGraph,
    KnowledgeProject,
    generate_id,
)

__all__ = [
    "SourceType",
    "KnowledgeSource",
    "CrossSourceLink",
    "Note",
    "Connection",
    "KnowledgeGraph",
    "KnowledgeProject",
    "generate_id",
]
