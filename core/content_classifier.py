"""
Content classification for document ingestion.

Thin wrapper around spiritwriter.classify.
"""

from spiritwriter.classify import (  # noqa: F401
    ContentClassifier,
    is_theme_candidate,
    is_institutional_name,
    is_venue_name,
    is_structural_noise,
    EXTRACTION_RULES,
)
