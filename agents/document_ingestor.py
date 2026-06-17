"""Document ingestor — now sourced from spiritwriter (single source of truth).

The PyMuPDF + LLM ingestion pipeline was consolidated into
``spiritwriter.ingest.DocumentIngestor`` (a clean superset of the former local
implementation). This keeps a thin ``StudioAgent``-flavored adapter so CSP's
agent registry and the ``DocumentIngestorAgent(claude_client=..., mock_mode=...)``
constructor keep working; all ingestion behavior is inherited from spiritwriter.

``ExtractionResult`` is re-exported for callers that import it from here.

See claude-studio-producer#15 / spiritwriter-core#76.
"""

from typing import Optional

from spiritwriter.ingest import DocumentIngestor
from spiritwriter.ingest.extraction import ExtractionResult  # noqa: F401  (re-export)

from core.claude_client import ClaudeClient
from .base import StudioAgent


class DocumentIngestorAgent(StudioAgent, DocumentIngestor):
    """Thin CSP adapter over spiritwriter's ``DocumentIngestor``.

    Maps CSP's StudioAgent constructor (``claude_client=``) onto spiritwriter's
    (``llm_provider=``), wiring the StudioAgent client as the provider. All
    ingestion logic (``ingest``, extraction, classification, summaries) is
    inherited from ``DocumentIngestor``.
    """

    _is_stub = False

    def __init__(
        self,
        claude_client: Optional[ClaudeClient] = None,
        mock_mode: bool = False,
    ):
        StudioAgent.__init__(self, claude_client=claude_client)
        DocumentIngestor.__init__(self, llm_provider=self.claude, mock_mode=mock_mode)


__all__ = ["DocumentIngestorAgent", "ExtractionResult"]
