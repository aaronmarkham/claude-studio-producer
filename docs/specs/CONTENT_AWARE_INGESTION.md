# Content-Aware Ingestion

> Status: Ready for Implementation
> Priority: High — directly impacts KB quality, which cascades to every downstream production
> Depends on: Existing document_ingestor.py, knowledge.py, document.py
> Date: February 7, 2026

## Problem

The KB ingestion pipeline treats all documents identically. A scientific paper and a news article go through the same LLM classification prompt, the same atom creation logic, and the same theme extraction. This causes three concrete problems:

### 1. Metadata pollutes key concepts

Author affiliations, department names, and university names leak into `topics` and then into `key_themes`:

```
Key Themes:
  ✓ "precise positioning method"
  ✓ "enclosed environments"
  ✓ "northwestern polytechnical university"   ← biographical metadata, not a concept
  ✓ "xihang university"                       ← biographical metadata
  ✓ "electronic engineering"                   ← department name
```

This happens because:
- The LLM classifies affiliation blocks as having topics (the prompt says "topics can be empty" for authors — soft hint, not enforced)
- The type mapping collapses `"affiliations"` → `PARAGRAPH` (document_ingestor.py:381), so downstream filters can't distinguish them
- Theme extraction is frequency-based (kb.py:187) with no semantic filtering — university names appear in multiple blocks (author, footer, acknowledgments) so they score high
- `STRUCTURAL_NOISE_TERMS` catches "affiliations" the word but not "Northwestern Polytechnical University" the value

### 2. No content-type-aware segmentation

A paper's "Methods" section, a news article's byline, and a dataset's column schema all get the same treatment. The ingestion doesn't know:
- That an "Acknowledgments" section in a paper is low-value metadata
- That a news article's dateline ("WASHINGTON, Feb 7 —") is temporal metadata, not content
- That author bios at the end of an article are provenance, not substance
- That a dataset README's "License" section shouldn't generate topics

### 3. `SourceType` exists but is never used

`KnowledgeSource.source_type` is an enum with PAPER, ARTICLE, NOTE, DATASET, URL — but it's hardcoded to `PAPER` on every add (kb.py:369). The document ingestor doesn't receive or use it. The graph builder doesn't filter by it.

---

## Design

### Core Idea: Classify First, Then Segment Accordingly

```
Document → ContentClassifier → ContentProfile
                                     │
                                     ├── document_type: "scientific_paper"
                                     ├── structural_zones: [metadata, abstract, body, references, ...]
                                     └── extraction_rules: {what to extract topics from, what's metadata}
                                             │
                                             ▼
                            DocumentIngestorAgent (uses profile to guide LLM)
                                             │
                                             ▼
                            DocumentGraph (with clean topic/entity separation)
```

The classifier runs before the LLM analysis phase. It uses lightweight heuristics on the raw extraction (Phase 1 output) to determine what kind of document this is and where the structural boundaries are. The LLM prompt is then tailored to the document type.

---

## Component 1: ContentProfile

A data model describing what the classifier learned about the document.

```python
# In core/models/document.py — add alongside existing models

class DocumentType(str, Enum):
    """What kind of document this is."""
    SCIENTIFIC_PAPER = "scientific_paper"
    NEWS_ARTICLE = "news_article"
    BLOG_POST = "blog_post"
    TECHNICAL_REPORT = "technical_report"
    DATASET_README = "dataset_readme"
    GOVERNMENT_DOCUMENT = "government_document"
    GENERIC = "generic"                     # Fallback


class ZoneRole(str, Enum):
    """
    What role a document zone plays.

    Zones are contiguous regions of the document. A zone's role
    determines how its atoms are treated during extraction.
    """
    FRONT_MATTER = "front_matter"           # Title, authors, affiliations, abstract
    BODY = "body"                           # Main content — full topic extraction
    BACK_MATTER = "back_matter"             # References, acknowledgments, appendix
    BIOGRAPHICAL = "biographical"           # Author bios, institutional info
    BOILERPLATE = "boilerplate"             # Headers, footers, page numbers, copyright


@dataclass
class DocumentZone:
    """A contiguous region of the document with a known role."""
    role: ZoneRole
    start_block: int                        # First block index (inclusive)
    end_block: int                          # Last block index (inclusive)
    label: str = ""                         # e.g., "Author Affiliations", "Methods", "References"


@dataclass
class ContentProfile:
    """
    What the classifier learned about this document.

    Produced by ContentClassifier, consumed by DocumentIngestorAgent
    to guide LLM analysis.
    """
    document_type: DocumentType
    confidence: float                       # 0-1, how sure the classifier is

    zones: List[DocumentZone] = field(default_factory=list)

    # Detected metadata (extracted early, before LLM)
    detected_authors: List[str] = field(default_factory=list)
    detected_institutions: List[str] = field(default_factory=list)
    detected_doi: Optional[str] = None
    detected_date: Optional[str] = None

    # Extraction rules derived from document type
    # These tell the ingestor what to do with each zone
    topic_extraction_zones: List[ZoneRole] = field(default_factory=list)  # Only extract topics from these
    entity_extraction_zones: List[ZoneRole] = field(default_factory=list) # Extract entities from these
    metadata_zones: List[ZoneRole] = field(default_factory=list)          # Store as metadata, not content

    def is_metadata_block(self, block_index: int) -> bool:
        """Check if a block is in a metadata zone."""
        for zone in self.zones:
            if zone.start_block <= block_index <= zone.end_block:
                return zone.role in self.metadata_zones
        return False

    def get_zone_for_block(self, block_index: int) -> Optional[DocumentZone]:
        """Get the zone a block belongs to."""
        for zone in self.zones:
            if zone.start_block <= block_index <= zone.end_block:
                return zone
        return None
```

### Default Rules by Document Type

```python
# In core/content_classifier.py

EXTRACTION_RULES = {
    DocumentType.SCIENTIFIC_PAPER: {
        "topic_zones": [ZoneRole.BODY],                          # Only body gets topics
        "entity_zones": [ZoneRole.BODY, ZoneRole.FRONT_MATTER],  # Entities from body + abstract
        "metadata_zones": [ZoneRole.BIOGRAPHICAL, ZoneRole.BOILERPLATE, ZoneRole.BACK_MATTER],
    },
    DocumentType.NEWS_ARTICLE: {
        "topic_zones": [ZoneRole.BODY],
        "entity_zones": [ZoneRole.BODY, ZoneRole.FRONT_MATTER],
        "metadata_zones": [ZoneRole.BIOGRAPHICAL, ZoneRole.BOILERPLATE],
    },
    DocumentType.BLOG_POST: {
        "topic_zones": [ZoneRole.BODY],
        "entity_zones": [ZoneRole.BODY],
        "metadata_zones": [ZoneRole.BIOGRAPHICAL, ZoneRole.BOILERPLATE],
    },
    DocumentType.DATASET_README: {
        "topic_zones": [ZoneRole.BODY],
        "entity_zones": [ZoneRole.BODY],
        "metadata_zones": [ZoneRole.BIOGRAPHICAL, ZoneRole.BOILERPLATE, ZoneRole.BACK_MATTER],
    },
    DocumentType.GENERIC: {
        "topic_zones": [ZoneRole.BODY, ZoneRole.FRONT_MATTER],   # Permissive fallback
        "entity_zones": [ZoneRole.BODY, ZoneRole.FRONT_MATTER],
        "metadata_zones": [ZoneRole.BOILERPLATE],
    },
}
```

---

## Component 2: ContentClassifier

A deterministic module (no LLM) that examines the raw PyMuPDF extraction to classify the document and identify zones.

```python
# NEW — core/content_classifier.py

class ContentClassifier:
    """
    Classifies document type and identifies structural zones.

    This is NOT an LLM agent. It uses heuristics on the raw extraction
    output (text blocks, font sizes, positions, PDF metadata) to make
    fast, deterministic decisions before the expensive LLM phase.
    """

    def classify(self, extraction: ExtractionResult) -> ContentProfile:
        """
        Classify a document and identify its structural zones.

        Args:
            extraction: Raw PyMuPDF extraction result

        Returns:
            ContentProfile describing the document
        """
        doc_type, confidence = self._detect_document_type(extraction)
        zones = self._identify_zones(extraction, doc_type)
        metadata = self._extract_early_metadata(extraction, zones)
        rules = EXTRACTION_RULES.get(doc_type, EXTRACTION_RULES[DocumentType.GENERIC])

        return ContentProfile(
            document_type=doc_type,
            confidence=confidence,
            zones=zones,
            detected_authors=metadata.get("authors", []),
            detected_institutions=metadata.get("institutions", []),
            detected_doi=metadata.get("doi"),
            detected_date=metadata.get("date"),
            topic_extraction_zones=[ZoneRole(z) for z in rules["topic_zones"]],
            entity_extraction_zones=[ZoneRole(z) for z in rules["entity_zones"]],
            metadata_zones=[ZoneRole(z) for z in rules["metadata_zones"]],
        )
```

### Document Type Detection Heuristics

These operate on the raw text blocks, PDF metadata, and structural cues — no LLM needed.

```python
def _detect_document_type(self, extraction: ExtractionResult) -> Tuple[DocumentType, float]:
    """
    Detect document type from structural signals.

    Signals checked (in priority order):
    1. PDF metadata (keywords, subject, creator)
    2. Structural markers (Abstract, References, DOI, byline patterns)
    3. Font distribution (papers have more font variation than articles)
    4. Content patterns (equations → paper, dateline → news)
    """
    signals = {}
    text_blocks = extraction.text_blocks
    metadata = extraction.metadata
    full_text = " ".join(b["text"] for b in text_blocks[:30])  # First 30 blocks
    full_text_lower = full_text.lower()

    # --- Signal: DOI or arXiv ---
    if _has_doi(full_text) or "arxiv" in full_text_lower:
        signals["doi"] = ("scientific_paper", 0.9)

    # --- Signal: "Abstract" section ---
    if _has_abstract_header(text_blocks):
        signals["abstract"] = ("scientific_paper", 0.7)

    # --- Signal: "References" or "Bibliography" section near end ---
    if _has_references_section(text_blocks):
        signals["references"] = ("scientific_paper", 0.6)

    # --- Signal: Dateline pattern (CITY, Month Day —) ---
    if _has_dateline(text_blocks):
        signals["dateline"] = ("news_article", 0.8)

    # --- Signal: AP/Reuters/byline pattern ---
    if _has_news_byline(text_blocks):
        signals["byline"] = ("news_article", 0.7)

    # --- Signal: Dataset/schema indicators ---
    if any(w in full_text_lower for w in ["columns:", "schema:", "csv", "json", "dataset description"]):
        signals["dataset"] = ("dataset_readme", 0.7)

    # --- Signal: Equations (LaTeX remnants, numbered equations) ---
    if _count_equations(text_blocks) > 3:
        signals["equations"] = ("scientific_paper", 0.5)

    # --- Vote ---
    if not signals:
        return DocumentType.GENERIC, 0.3

    # Take highest confidence signal
    best_type, best_conf = max(signals.values(), key=lambda x: x[1])
    return DocumentType(best_type), best_conf
```

### Zone Identification

Zones are identified by structural markers specific to each document type.

```python
def _identify_zones(
    self,
    extraction: ExtractionResult,
    doc_type: DocumentType,
) -> List[DocumentZone]:
    """
    Identify structural zones in the document.

    For papers:
      front_matter:  blocks 0..first_body_section
      body:          first_body_section..references_section
      back_matter:   references_section..end
      biographical:  author/affiliation blocks (detected by font/position)

    For news:
      front_matter:  headline + byline
      body:          main text
      biographical:  author bio at end
      boilerplate:   dateline, copyright
    """
```

The key zone detection patterns for **scientific papers**:

| Zone | Detection Method |
|---|---|
| **Front matter** (title→abstract) | Blocks before first `SECTION_HEADER` with body content. Includes title (largest font, page 1), author blocks (multi-column, small font, contains "@" or university names), abstract (explicitly labeled or first long paragraph) |
| **Body** (intro→conclusion) | Blocks between first body section header and references section. This is where content lives. |
| **Biographical** | Author name blocks (detected by position: page 1, between title and abstract), affiliation blocks (contain university/institute/department patterns), and author bios (often at document end, small font, "received his/her PhD" patterns) |
| **Back matter** | Everything after "References" / "Bibliography" header |
| **Boilerplate** | Page headers/footers (detected by position: top/bottom of page, repeating across pages), copyright notices |

The key zone detection patterns for **news articles**:

| Zone | Detection Method |
|---|---|
| **Front matter** | Headline (largest font, page 1), subhead, byline ("By Author Name") |
| **Body** | Everything between byline and end-of-article markers |
| **Biographical** | "About the author" section, contributor bios |
| **Boilerplate** | Dateline, copyright, publication info, "Related articles" |

### Early Metadata Extraction

For the biographical zone, we extract structured metadata *before* the LLM runs:

```python
def _extract_early_metadata(
    self,
    extraction: ExtractionResult,
    zones: List[DocumentZone],
) -> Dict[str, Any]:
    """
    Extract author/institution metadata from biographical zones.

    This runs before the LLM phase. The extracted data goes into
    DocumentGraph.authors and KnowledgeSource.authors — NOT into
    atom topics.
    """
    metadata = {"authors": [], "institutions": [], "doi": None, "date": None}

    for zone in zones:
        if zone.role != ZoneRole.BIOGRAPHICAL:
            continue

        for i in range(zone.start_block, zone.end_block + 1):
            if i >= len(extraction.text_blocks):
                break
            text = extraction.text_blocks[i]["text"]

            # Extract institution names
            institutions = _extract_institutions(text)
            metadata["institutions"].extend(institutions)

            # Extract author names (from biographical zone)
            authors = _extract_author_names(text)
            metadata["authors"].extend(authors)

    # DOI from anywhere in the document
    for block in extraction.text_blocks:
        doi = _extract_doi(block["text"])
        if doi:
            metadata["doi"] = doi
            break

    return metadata
```

#### Institution Detection

```python
# Patterns that identify institutional affiliation text
INSTITUTION_PATTERNS = [
    r"(?:university|universit[ée]|universidad)\s+(?:of\s+)?[\w\s]+",
    r"(?:institute|institut)\s+(?:of|for|de)\s+[\w\s]+",
    r"(?:school|college|faculty|department|dept\.?)\s+of\s+[\w\s]+",
    r"(?:laboratory|lab|centre|center)\s+(?:of|for)\s+[\w\s]+",
    r"[\w\s]+(?:polytechnic|polytechnical)\s+[\w\s]*",
]

# These are METADATA, not topics — they describe who, not what
INSTITUTION_INDICATOR_WORDS = {
    "university", "institute", "school", "college", "department",
    "faculty", "laboratory", "centre", "center", "hospital",
    "corporation", "inc", "ltd", "gmbh", "polytechnic",
}
```

---

## Component 3: Integration with DocumentIngestorAgent

The classifier output feeds into the existing LLM analysis phase, modifying two things:

### 1. The LLM prompt is document-type-aware

Currently `_build_structure_prompt()` is generic. With the ContentProfile, it becomes:

```python
def _build_structure_prompt(self, text_context: str, metadata: Dict, profile: ContentProfile) -> str:
    """Build document-type-aware prompt for LLM structure analysis."""

    # Type-specific classification guidance
    if profile.document_type == DocumentType.SCIENTIFIC_PAPER:
        type_guidance = """
This is a SCIENTIFIC PAPER. Classification specifics:
- Author names and affiliations → type "author" (DO NOT extract topics from these)
- Abstract → type "abstract"
- Section headers (Introduction, Methods, Results, etc.) → type "section_header"
- Acknowledgments, funding info → type "metadata" (no topics)
- References/bibliography → type "citation" (no topics)

CRITICAL: University names, department names, and institutional affiliations are NOT topics.
They are author metadata. Do NOT extract them as topics.
- BAD topic: "northwestern polytechnical university", "electronic engineering", "school of computing"
- GOOD topic: "indoor positioning", "Kalman filter", "UWB ranging"
"""
    elif profile.document_type == DocumentType.NEWS_ARTICLE:
        type_guidance = """
This is a NEWS ARTICLE. Classification specifics:
- Headline → type "title"
- Byline ("By Author Name") → type "author" (no topics)
- Dateline ("WASHINGTON, Feb 7 —") → type "date" (no topics)
- Article body → type "paragraph"
- Author bio at end → type "author" (no topics)

Entities should include: people quoted, organizations mentioned, locations relevant to the story.
Authors of the article are metadata, not entities.
"""
    # ... similar for other types

    # Zone-aware instructions
    if profile.zones:
        zone_hints = "\n".join(
            f"- Blocks {z.start_block}-{z.end_block}: {z.role.value} zone ({z.label})"
            for z in profile.zones
        )
        zone_guidance = f"""
DOCUMENT ZONES (detected from structure):
{zone_hints}

For blocks in biographical/boilerplate zones: set topics=[] and entities=[].
Only extract topics from body and front_matter zones.
"""
    else:
        zone_guidance = ""

    return f"""Analyze this document's structure...
{type_guidance}
{zone_guidance}
... (rest of existing prompt)
"""
```

### 2. Post-LLM topic filtering uses zone awareness

Even with a better prompt, the LLM may still leak metadata into topics. A hard filter after LLM analysis catches what the prompt missed:

```python
# In DocumentIngestorAgent._llm_analyze(), after creating atoms:

def _apply_zone_filters(self, atoms: Dict[str, DocumentAtom], profile: ContentProfile):
    """
    Post-LLM cleanup: remove topics from non-content zones.

    This is the hard filter that catches what the prompt didn't.
    """
    for atom_id, atom in atoms.items():
        zone = profile.get_zone_for_block(atom.source_block_index)
        if zone is None:
            continue

        # Biographical and boilerplate zones: strip all topics
        if zone.role in profile.metadata_zones:
            # Move any extracted topics to entities (they might be useful as metadata)
            # but they are NOT content topics
            atom.entities.extend(atom.topics)
            atom.topics = []
            atom.importance_score = min(atom.importance_score, 0.3)

        # Institution/university filter on ALL zones
        # Even in body text, "Northwestern Polytechnical University" is not a topic
        atom.topics = [
            t for t in atom.topics
            if not _is_institutional_name(t)
        ]
```

### 3. Entity typing

Currently entities are flat strings. We add a lightweight type tag:

```python
# Extend DocumentAtom — add typed_entities alongside existing flat entities

@dataclass
class TypedEntity:
    """An entity with a semantic type tag."""
    name: str
    entity_type: str  # "person", "institution", "algorithm", "dataset", "location", "organization"
    role: str = ""    # "author", "cited", "subject", "funder"

# On DocumentAtom:
typed_entities: List[TypedEntity] = field(default_factory=list)
# Keep flat `entities: List[str]` for backward compatibility
```

This means the graph can distinguish:
- `TypedEntity("Dr. Zhang", "person", "author")` — provenance metadata
- `TypedEntity("Kalman filter", "algorithm", "subject")` — content entity
- `TypedEntity("Northwestern Polytechnical University", "institution", "author_affiliation")` — biographical metadata

The `entity_type` and `role` tags are populated by the LLM during classification (added to the prompt) and validated by zone-aware post-processing.

---

## Component 4: Theme Extraction Upgrade

Replace the frequency-only theme extraction in `_rebuild_knowledge_graph()` with a two-pass approach:

### Pass 1: Filter by atom zone (hard rules)

```python
# In kb.py _rebuild_knowledge_graph() — replace topic_index building

# Build topic index, but only from content-bearing atoms
for atom_id, atom in all_atoms.items():
    # Skip atoms that were in metadata zones (importance <= 0.3 from zone filter)
    if atom.importance_score <= 0.3:
        continue

    # Skip atoms whose type is inherently non-content
    if atom.atom_type in (AtomType.AUTHOR, AtomType.DATE, AtomType.CITATION, AtomType.KEYWORD):
        continue

    for topic in atom.topics:
        topic_key = topic.lower().strip()
        if topic_key not in topic_index:
            topic_index[topic_key] = []
        topic_index[topic_key].append(atom_id)
```

### Pass 2: Semantic noise filter (pattern + heuristic)

```python
def _is_theme_candidate(topic: str, entity_index: Dict) -> bool:
    """
    Determine if a topic is a legitimate theme vs. metadata noise.

    Rejects:
    - Institutional names (university, department, school of...)
    - Author names (if they appear in entity_index as persons)
    - Geographic locations that are affiliations not content
    - Journal/conference names
    """
    topic_lower = topic.lower()

    # Institutional name detection
    if _is_institutional_name(topic_lower):
        return False

    # Journal/conference name detection
    if any(w in topic_lower for w in [
        "journal", "proceedings", "conference", "symposium",
        "transactions", "letters", "ieee", "acm", "springer",
    ]):
        return False

    # Geographic-only (just a place name with no technical content)
    # "Beijing" alone is noise; "Beijing traffic dataset" is content
    if _is_pure_geographic(topic_lower):
        return False

    return True


def _is_institutional_name(text: str) -> bool:
    """Check if text is an institutional/organizational name rather than a concept."""
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in INSTITUTION_INDICATOR_WORDS)
```

---

## Component 5: Source Type Auto-Detection

Wire the classifier's `document_type` into `KnowledgeSource.source_type`:

```python
# In cli/kb.py _add_paper() — replace hardcoded SourceType.PAPER

# Map document type to source type
DOC_TYPE_TO_SOURCE_TYPE = {
    DocumentType.SCIENTIFIC_PAPER: SourceType.PAPER,
    DocumentType.NEWS_ARTICLE: SourceType.ARTICLE,
    DocumentType.BLOG_POST: SourceType.ARTICLE,
    DocumentType.TECHNICAL_REPORT: SourceType.PAPER,
    DocumentType.DATASET_README: SourceType.DATASET,
    DocumentType.GOVERNMENT_DOCUMENT: SourceType.PAPER,  # closest match
    DocumentType.GENERIC: SourceType.PAPER,  # safe default
}

source = KnowledgeSource(
    source_id=source_id,
    source_type=DOC_TYPE_TO_SOURCE_TYPE.get(profile.document_type, SourceType.PAPER),
    ...
)
```

This also feeds into CONTENT_MODEL_EXPANSION's `SourceAttribution.source_type` — when the classifier knows it's a news article, the StructuredScript can automatically set `SourceType.NEWS` on its source attributions.

---

## Implementation

### What to Change

| File | Change | Priority |
|---|---|---|
| `core/models/document.py` | Add `DocumentType`, `ZoneRole`, `DocumentZone`, `ContentProfile`, `TypedEntity` | P0 |
| NEW `core/content_classifier.py` | ContentClassifier with detection heuristics and zone identification | P0 |
| `agents/document_ingestor.py` | Call classifier before LLM phase; use profile in prompt and post-LLM filter | P0 |
| `agents/document_ingestor.py` | Fix type_mapping: `"affiliations"` → `AtomType.AUTHOR`, not `PARAGRAPH` | P0 |
| `cli/kb.py` | Use profile.document_type for source_type; filter topic_index by atom zone | P1 |
| `cli/kb.py` | Upgrade `_rebuild_knowledge_graph()` theme extraction with semantic filter | P1 |
| `cli/kb.py` | Add `--reclassify` flag to `kb add` for re-running classifier on existing sources | P2 |
| `tests/test_content_classifier.py` | Tests for each document type detection and zone identification | P1 |

### What NOT to Change

- `ContentLibrary`, `ContentLibrarian` — no changes, already content-type agnostic
- `StructuredScript` — no changes, reads from DocumentGraph which will now be cleaner
- `core/dop.py` — no changes, reads intents not topics
- `cli/produce_video.py` — no changes, reads structured script not raw KB

### Phased Rollout

**Phase A: Fix the immediate bleed (1-2 hours)**
1. Fix `type_mapping` in document_ingestor.py: `"affiliations"` → `"author"`, `"authors"` → `"author"`
2. Add institutional name filter to `_calculate_topic_quality()` and theme extraction in kb.py
3. Strip topics from atoms with `atom_type` in `{AUTHOR, DATE, CITATION, KEYWORD}`

This alone fixes the "Northwestern Polytechnical University in key themes" problem without any new modules.

**Phase B: ContentClassifier module (half day)**
1. Create `core/content_classifier.py` with document type detection
2. Create `ContentProfile` model
3. Add zone identification for scientific papers (most common input)

**Phase C: Integration (half day)**
1. Wire classifier into `DocumentIngestorAgent.ingest()`
2. Make LLM prompt document-type-aware
3. Add post-LLM zone filtering
4. Wire source type auto-detection into `kb add`

**Phase D: Extend to other document types (ongoing)**
1. Add zone patterns for news articles
2. Add zone patterns for blog posts, dataset READMEs
3. Add `TypedEntity` to DocumentAtom
4. Add `--reclassify` CLI flag

---

## Validation

After implementation, run `kb inspect --quality` on existing KBs. Expected changes:

**Before:**
```
Key Themes:
  ✓ "precise positioning method"
  ✓ "enclosed environments"
  ✓ "northwestern polytechnical university"    ← noise
  ✓ "xihang university"                        ← noise
  ✓ "electronic engineering"                    ← noise
  ✓ "filter"
  ✓ "interference"

Topic Quality: 72/100
```

**After:**
```
Key Themes:
  ✓ "precise positioning method"
  ✓ "enclosed environments"
  ✓ "uwb ranging"
  ✓ "kalman filter"
  ✓ "gps-denied navigation"
  ✓ "sensor fusion"
  ✓ "interference mitigation"

Topic Quality: 94/100

Document Metadata (not in themes):
  Authors: Dr. Zhang, Dr. Li
  Institutions: Northwestern Polytechnical University, Xihang University
  DOI: 10.1109/ACCESS.2024.xxxxx
```

---

## Interaction with Other Specs

| Spec | How This Helps |
|---|---|
| CONTENT_MODEL_EXPANSION | `SourceAttribution.source_type` gets auto-populated from classifier |
| UNIFIED_PRODUCTION_ARCHITECTURE | Cleaner key_themes → better Script Writer prompts → better scripts |
| PODCAST_TRAINING_PIPELINE | Training script references cleaner concepts, not university names |
| KNOWLEDGE_TO_VIDEO | Multi-source productions benefit from typed entities for citation overlays |
