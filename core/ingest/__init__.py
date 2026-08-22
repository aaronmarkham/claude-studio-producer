"""Personal media ingestion — Google Timeline exports and photo folders.

See docs/specs/PERSONAL_TIMELINE_PRODUCTION.md. The pipeline is:

    timeline.py  ─┐
                  ├─► trip_join.py ─► TripKnowledge ─► (script generation, Phase 2)
    photos.py   ──┘

Every module here is deterministic and offline: no LLM, no network, no API keys.
"""
