"""Document models — now sourced from spiritwriter (single source of truth).

These models were consolidated into spiritwriter and are identical to the
former local copy. This module re-exports them so existing
``core.models.document`` import sites keep working; new code should import
from ``spiritwriter.models.document`` directly. Each importer migrates to
the spiritwriter path as its own module is ported.

See claude-studio-producer#15 / spiritwriter-core#76.
"""

from spiritwriter.models.document import (  # noqa: F401
    AtomType,
    DocumentType,
    ZoneRole,
    DocumentZone,
    ContentProfile,
    DocumentAtom,
    DocumentGraph,
)
