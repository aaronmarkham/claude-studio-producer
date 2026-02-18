---
layout: default
title: Knowledge Base Deep Dive
---

# Knowledge Base Deep Dive

How Claude Studio Producer transforms PDFs into rich, queryable knowledge graphs.

---

## Table of Contents

1. [Overview](#overview)
2. [The Ingestion Pipeline](#the-ingestion-pipeline)
3. [What Is an Atom?](#what-is-an-atom)
4. [Atom Types](#atom-types)
5. [Real Atom Examples](#real-atom-examples)
6. [Document Graphs](#document-graphs)
7. [Content Classification](#content-classification)
8. [Figure Extraction](#figure-extraction)
9. [The Unified Knowledge Graph](#the-unified-knowledge-graph)
10. [Cross-Source Linking](#cross-source-linking)
11. [Quality Metrics](#quality-metrics)
12. [From KB to Production](#from-kb-to-production)

---

## Overview

When you run `cs kb add my-project --paper paper.pdf`, a multi-phase pipeline breaks the PDF into **atoms** — the smallest meaningful units of knowledge. These atoms carry semantic metadata (topics, entities, importance scores, source locations) and are assembled into a **DocumentGraph** with hierarchy, reading order, and LLM-generated summaries. When multiple papers are added, their atoms merge into a **unified KnowledgeGraph** with cross-source links and shared topic/entity indices.

A typical 11-page academic paper produces ~153 atoms across 14 types, 88 indexed topics, 42 indexed entities, and 11 extracted figures — all queryable, inspectable, and ready for script generation or video production.

---

## The Ingestion Pipeline

```
PDF File
  │
  ▼
┌─────────────────────────────────────────────────┐
│  Phase 1: PyMuPDF Extraction                     │
│  ├─ Text blocks (with bbox, font, bold flags)    │
│  ├─ Rendered figures (2x zoom, caption-guided)   │
│  └─ PDF metadata (title, authors, DOI)           │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  Phase 1.5: Content Classification               │
│  ├─ Document type (paper, news, blog, etc.)      │
│  ├─ Zone identification (front, body, back)      │
│  ├─ Early metadata extraction (institutions)     │
│  └─ Extraction rules (what to pull from where)   │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  Phase 2: LLM Semantic Analysis (Claude)         │
│  ├─ Block type classification (chunked, ~30/req) │
│  ├─ Topic extraction (1-3 per block)             │
│  ├─ Entity extraction (algorithms, systems)      │
│  ├─ Importance scoring (0.0-1.0)                 │
│  ├─ Figure description (Claude Vision)           │
│  └─ Document summaries (1-sentence to full)      │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  Phase 3: Graph Assembly                         │
│  ├─ Build DocumentAtom objects                   │
│  ├─ Establish hierarchy (sections → paragraphs)  │
│  ├─ Set reading order (flow)                     │
│  ├─ Store figure PNGs to disk                    │
│  └─ Save DocumentGraph JSON                      │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  Phase 4: Knowledge Graph Rebuild                │
│  ├─ Merge all sources' atoms                     │
│  ├─ Build topic_index and entity_index           │
│  ├─ Detect cross-source entity links             │
│  ├─ Extract key themes (noise-filtered)          │
│  └─ Save unified KnowledgeGraph JSON             │
└─────────────────────────────────────────────────┘
```

---

## What Is an Atom?

An **atom** is the smallest unit of extracted knowledge. Every piece of information from the PDF — a paragraph, a figure, an equation, an author name, a section header — becomes an atom with rich metadata attached.

### Atom Fields

| Field | Type | Description |
|-------|------|-------------|
| `atom_id` | string | Globally unique ID (e.g., `doc_a565_atom_014`) |
| `atom_type` | enum | One of 14 types (see below) |
| `content` | string | The text content or description |
| `raw_data` | bytes | Image data for figures (stored as PNG, not serialized to JSON) |
| `source_page` | int | Page number in the original PDF (0-indexed) |
| `source_location` | (x0,y0,x1,y1) | Bounding box in PDF coordinates |
| `topics` | list[str] | 1-3 semantic concepts (LLM-extracted) |
| `entities` | list[str] | Named algorithms, systems, datasets, acronyms |
| `relationships` | list[str] | Atom IDs this atom references |
| `importance_score` | float | 0.0-1.0 centrality to the document |
| `caption` | string | For figures/tables: the caption text |
| `figure_number` | string | e.g., "FIGURE 1", "Table 2" |
| `data_summary` | string | LLM-generated description of visual content |

### Importance Score Guidelines

| Score | Used For |
|-------|----------|
| **1.0** | Title, key findings |
| **0.8** | Abstract, section headers, conclusions |
| **0.7** | Figures with key results |
| **0.5** | Body paragraphs, keywords |
| **0.4** | Equations |
| **0.3** | Citations, author info, metadata, boilerplate |

---

## Atom Types

The system recognizes **14 atom types** across three categories:

### Text Atoms

| Type | Description | Example |
|------|-------------|---------|
| `title` | Document title | "Precise Positioning Method of UAV..." |
| `abstract` | Full abstract text | "This study addresses the challenge..." |
| `section_header` | Section/subsection heading with intro text | "I. INTRODUCTION With the rapid..." |
| `paragraph` | Body paragraph | Multi-sentence content block |
| `quote` | Notable quoted text | Direct quotes from sources |
| `citation` | References, DOIs, licensing info | "Digital Object Identifier 10.1109/..." |

### Visual Atoms

| Type | Description | Example |
|------|-------------|---------|
| `figure` | Extracted figure with AI-generated description | Flowchart of particle filter algorithm |
| `chart` | Data charts/graphs | Bar charts, line graphs |
| `table` | Tabular data | Comparison tables |
| `equation` | Mathematical expressions | "E[Wk] = 0" |
| `diagram` | Technical diagrams | System architecture diagrams |

### Meta Atoms

| Type | Description | Example |
|------|-------------|---------|
| `author` | Author names and affiliations | "YANGMEI ZHANG, School of Electronic..." |
| `date` | Publication/submission dates | "Received 26 October 2025, accepted..." |
| `keyword` | Author-specified keywords | "Dynamic environment, Kalman filter..." |

---

## Real Atom Examples

These are actual atoms from the `aerial-vehicle-positioning` knowledge base (153 atoms from an 11-page IEEE paper):

### Title Atom (importance: 1.0)
```json
{
  "atom_id": "doc_a5654cad96dc_atom_002",
  "atom_type": "title",
  "content": "Precise Positioning Method of Unmanned Aerial Vehicle in Enclosed
    Environments by Integrating Multi-Sensor Information...",
  "source_page": 0,
  "source_location": [36.17, 149.18, 449.81, 272.32],
  "topics": ["UAV positioning", "multi-sensor fusion", "Kalman filter", "particle filter"],
  "entities": ["Kalman Filter", "Particle Filter"],
  "importance_score": 1.0
}
```

### Abstract Atom (importance: 0.8)
```json
{
  "atom_id": "doc_a5654cad96dc_atom_007",
  "atom_type": "abstract",
  "content": "ABSTRACT This study addresses the challenge of the precise positioning
    of Unmanned Aerial Vehicles (UAVs) in enclosed environments...",
  "source_page": 0,
  "topics": ["UAV positioning", "Kalman filter", "particle filter",
             "multi-sensor fusion", "dynamic environment adaptation"],
  "entities": ["IKF-PF", "Kalman Filter", "Particle Filter", "ROS",
               "Gazebo", "LOS", "NLOS", "GPS"],
  "importance_score": 0.8
}
```

### Figure Atom (importance: 0.7, with AI description)
```json
{
  "atom_id": "doc_a5654cad96dc_fig_000",
  "atom_type": "figure",
  "content": "This flowchart illustrates the iterative process of a particle
    filter algorithm used for UAV positioning in enclosed environments. The
    process begins with initialization, then cycles through importance sampling,
    weight normalization, and resampling steps...",
  "source_page": 3,
  "importance_score": 0.7,
  "caption": "FIGURE 1. The principle of the PF algorithm.",
  "figure_number": "FIGURE 1",
  "data_summary": "This flowchart illustrates the iterative process of a
    particle filter algorithm..."
}
```
The `content` and `data_summary` are generated by **Claude Vision** — the actual figure PNG is stored separately in `sources/{source_id}/figures/{atom_id}.png`.

### Body Paragraph Atom (importance: 0.5)
```json
{
  "atom_id": "doc_a5654cad96dc_atom_014",
  "atom_type": "paragraph",
  "content": "delivery, environmental monitoring, emergency rescue, and indoor
    inspection have become increasingly widespread. The precise positioning
    capability of UAVs is one of the critical factors...",
  "source_page": 1,
  "source_location": [36.17, 65.49, 277.38, 614.12],
  "topics": ["UAV positioning", "GPS limitations", "multi-sensor fusion"],
  "entities": ["GPS", "IMU", "UWB"],
  "importance_score": 0.5
}
```

### Equation Atom (importance: 0.4)
```json
{
  "atom_id": "doc_a5654cad96dc_atom_023",
  "atom_type": "equation",
  "content": "E[Wk] = 0,",
  "source_page": 2,
  "source_location": [110.26, 705.76, 157.88, 717.84],
  "topics": ["expected value"],
  "importance_score": 0.4
}
```

### Metadata Atom (importance: 0.3, topics suppressed)
```json
{
  "atom_id": "doc_a5654cad96dc_atom_004",
  "atom_type": "author",
  "content": "1School of Electronic Engineering, Xihang University, Xi'an 710077...",
  "source_page": 0,
  "topics": [],
  "entities": ["Xihang University"],
  "importance_score": 0.3
}
```
Note: **topics are empty** for author/affiliation atoms. The content classifier identifies these as `BIOGRAPHICAL` zone blocks and suppresses topic extraction to prevent institutional names from polluting the topic index.

---

## Document Graphs

A **DocumentGraph** wraps all atoms from a single source with structural metadata:

```
DocumentGraph
├── document_id: "doc_a5654cad96dc"
├── source_path: "/path/to/paper.pdf"
├── title: "Precise Positioning Method of UAV..."
├── authors: ["YANGMEI ZHANG", "YANG BI", ...]
├── page_count: 11
│
├── atoms: {atom_id → DocumentAtom}          # All 153 atoms
│
├── hierarchy:                                # Section → children
│   ├── atom_011 (I. INTRODUCTION) → [atom_014, atom_015, ...]
│   ├── atom_025 (II. METHODS)     → [atom_026, atom_027, ...]
│   └── atom_080 (III. RESULTS)    → [atom_081, atom_082, ...]
│
├── flow: [atom_000, atom_001, ..., atom_152]  # Reading order
│
├── one_sentence: "This study proposes an IKF-PF fusion model..."
├── one_paragraph: "The paper addresses precise UAV positioning..."
├── full_summary: "..." (multi-paragraph)
│
├── figures: [fig_000, fig_001, ..., fig_010]   # 11 figure atom IDs
├── tables: []
└── key_quotes: []
```

### Hierarchy

The hierarchy tracks parent-child relationships between atoms. When the LLM identifies a `section_header`, all subsequent `paragraph`, `equation`, `quote`, and `figure` atoms become its children until the next section header. This lets you query "give me everything in the Methods section" programmatically:

```python
methods_atoms = doc_graph.get_section("Methods")
# Returns all child atoms under the Methods header
```

### Summaries

The LLM generates three levels of summary from an abbreviated context (first 15 + last 10 blocks, ~15KB):

- **one_sentence**: Single-sentence thesis/finding
- **one_paragraph**: Key contributions and approach
- **full_summary**: Comprehensive multi-paragraph overview

---

## Content Classification

Before sending anything to the LLM, a **ContentClassifier** performs fast, deterministic pre-analysis. This is critical for quality — it prevents metadata from contaminating the topic index.

### Document Type Detection

The classifier checks signals in priority order:

| Signal | Detected Type | Confidence |
|--------|--------------|------------|
| DOI or arXiv pattern | `SCIENTIFIC_PAPER` | 0.9 |
| "Abstract" header | `SCIENTIFIC_PAPER` | 0.7 |
| "References" section near end | `SCIENTIFIC_PAPER` | 0.6 |
| Dateline (CITY, Month Day) | `NEWS_ARTICLE` | 0.8 |
| AP/Reuters/byline pattern | `NEWS_ARTICLE` | 0.7 |
| Dataset keywords (columns, schema) | `DATASET_README` | 0.7 |
| Multiple equations (>3) | `SCIENTIFIC_PAPER` | 0.5 |

### Zone Identification

For a **scientific paper**, the classifier divides the document into zones:

```
Page 0-1:  FRONT_MATTER   (title, authors, abstract, affiliations)
Page 1-8:  BODY           (introduction through conclusion)
Page 8-9:  BIOGRAPHICAL   (author bios, institution details)
Page 9-11: BACK_MATTER    (references, acknowledgments)
```

### How Zones Affect Extraction

| Zone | Topics Extracted? | Entities Extracted? | Treated As |
|------|-------------------|--------------------| -----------|
| `BODY` | Yes | Yes | Main content |
| `FRONT_MATTER` | Yes | Yes | Key context |
| `BIOGRAPHICAL` | **No** | Limited | Metadata only |
| `BACK_MATTER` | **No** | **No** | References |
| `BOILERPLATE` | **No** | **No** | Ignored |

This is why author affiliations like "Northwestern Polytechnical University" appear in entities but never in topics — the classifier knows they're biographical metadata, not paper content.

### Theme Candidate Filtering

Even within body zones, a `is_theme_candidate()` filter rejects:
- **Institutional names**: university, institute, department, laboratory, school, hospital
- **Journal/venue names**: IEEE, ACM, Springer, workshop, proceedings, symposium
- **Too-short terms**: Single words under 6 characters
- **Pure numbers**: Digit-only strings

---

## Figure Extraction

The system uses two strategies for extracting figures, with the rendered approach as default for academic PDFs.

### Rendered Figure Extraction (Primary)

1. Render each PDF page at **2x zoom** using PyMuPDF
2. Scan for caption patterns: `FIGURE`, `Fig.`, `TABLE`, `Table` followed by a number
3. For each caption found, clip a region **400 points above** the caption
4. Export the clipped region as PNG
5. Send to **Claude Vision** for description (2-3 sentences)
6. Parse `figure_number` from caption text

This approach is superior for academic PDFs because figures are often composed from multiple sub-images that are separate elements in the PDF but form a single logical figure.

### Embedded Image Extraction (Fallback)

1. Use `page.get_images()` to find raw embedded images
2. Extract via `doc.extract_image(xref)`
3. Deduplicate by xref ID
4. Filter out tiny images (<150px or <5KB) and oversized images (>10,000px)

### Figure Atoms

Each extracted figure becomes an atom with:
- `content`: Claude Vision's description of what the figure shows
- `caption`: The parsed caption text (e.g., "FIGURE 1. The principle of the PF algorithm.")
- `figure_number`: The parsed identifier (e.g., "FIGURE 1")
- `data_summary`: Same as content (AI-generated description)
- `raw_data`: PNG bytes (stored to disk, not serialized in JSON)

---

## The Unified Knowledge Graph

When a project has multiple sources, all DocumentGraphs are merged into a single **KnowledgeGraph**:

```
KnowledgeGraph
├── project_id: "kb_735f1cffaff7"
│
├── atoms: {all atoms from all sources}
├── atom_sources: {atom_id → source_id}     # Track provenance
│
├── topic_index:                              # Fast lookup
│   ├── "particle filter" → [27 atom IDs]
│   ├── "Kalman filter"   → [13 atom IDs]
│   ├── "sensor fusion"   → [8 atom IDs]
│   └── ... (88 topics total)
│
├── entity_index:
│   ├── "PF"  → [atom IDs]
│   ├── "IMU" → [atom IDs]
│   └── ... (42 entities total)
│
├── cross_links: [CrossSourceLink, ...]       # Inter-source connections
│
├── key_themes: ["particle filter", "Kalman filter", "state estimation", ...]
└── unified_summary: "..."
```

### Topic Index

The topic index maps every extracted topic to the atom IDs that mention it. This enables queries like "show me everything about particle filters" across all sources in the project.

For the UAV paper:
- `"particle filter"` appears in **27 atoms** (most prevalent concept)
- `"Kalman filter"` appears in **13 atoms**
- `"sensor fusion"` appears in **8 atoms**
- 88 unique topics total across 153 atoms

### Entity Index

Similarly, entities (algorithms, systems, acronyms, proper names) are indexed:
- Acronyms: `PF`, `IKF-PF`, `IMU`, `IKF`, `KF`, `GPS`, `UWB`, `UKF`
- Proper names: `Xihang University`, `Kalman Filter`, `Particle Filter`
- 42 unique entities total

### Key Themes

Key themes are the most significant topics after aggressive noise filtering:

1. Filter stopwords (87 generic academic terms: "machine", "learning", "analysis", etc.)
2. Apply `is_theme_candidate()` to reject institutional/venue names
3. For multi-source projects: require topics to appear in 2+ sources
4. Enforce multi-word phrases or 6+ characters for single words
5. Take top 10 surviving topics

Result for the UAV paper:
```
✓ "particle filter"
✓ "Kalman filter"
✓ "particle weight calculation"
✓ "state estimation"
✓ "sensor fusion"
✓ "NLOS environments"
✓ "UAV positioning"
✓ "LOS environments"
✓ "runtime analysis"
✓ "resampling"
```

---

## Cross-Source Linking

When a project contains multiple papers, the system automatically discovers connections between them.

### How Links Are Created

During knowledge graph rebuild, for each entity that appears in atoms from **2+ different sources**, the system creates a `CrossSourceLink`:

```json
{
  "link_id": "link_abc123",
  "source_atom_id": "doc_aaa_atom_042",
  "target_atom_id": "doc_bbb_atom_017",
  "source_source_id": "src_aaa",
  "target_source_id": "src_bbb",
  "relationship": "same_topic",
  "confidence": 0.6,
  "created_by": "auto"
}
```

### Link Types

| Relationship | Description |
|-------------|-------------|
| `same_topic` | Both atoms discuss the same entity (auto-detected) |
| `supports` | One atom provides evidence for the other |
| `contradicts` | Atoms present conflicting findings |
| `extends` | One atom builds on the other's work |

Currently, only `same_topic` links are auto-generated. Other types are available for future user annotation.

### Shared Topics/Entities

The graph provides methods to find overlap between sources:
```python
shared_topics = kg.get_shared_topics()    # Topics in 2+ sources
shared_entities = kg.get_shared_entities() # Entities in 2+ sources
```

---

## Quality Metrics

The `kb inspect` command computes four quality scores entirely from the stored graph data (no LLM calls needed).

### Topic Quality Score (0-100)

**Formula**: `(good_topics / total_topics) * 100`

A topic is classified as **noise** if it matches any of:
- Structural terms (49 hardcoded): "figure", "abstract", "methodology", "introduction", "results", etc.
- Institutional/venue names: detected via `is_theme_candidate()`
- Length-based: less than 3 characters, pure digits, or single words under 6 characters

A score of **100/100** means zero noise topics were detected — every extracted topic is a genuine semantic concept.

### Entity Quality Score (0-100)

**Formula**: `(acronyms + proper_names) / total_entities * 100`

Entities are categorized by pattern:
- **Acronyms**: All caps, 2-6 chars (e.g., "PF", "GPS", "IMU")
- **Proper names**: Capitalized multi-word (e.g., "Kalman Filter", "Xihang University")
- **Other**: Everything else (potentially noisy)

A score of **92/100** means 92% of entities are well-formed acronyms or proper names.

### Atom Type Distribution

Shows how the document was decomposed:
```
paragraph          ███████░░░░░░░░░   54 (35.3%)
equation           █████░░░░░░░░░░░   45 (29.4%)
section_header     ██░░░░░░░░░░░░░░   19 (12.4%)
author             █░░░░░░░░░░░░░░░   11 (7.2%)
figure             █░░░░░░░░░░░░░░░   11 (7.2%)
citation           █░░░░░░░░░░░░░░░    8 (5.2%)
```

This distribution tells you the nature of the source material. The UAV paper is equation-heavy (29.4%), which is typical for a signal processing paper.

### Concept Distribution

The top 12 topics ranked by atom count, normalized to the highest:
```
particle filter               ████████████████████  27
Kalman filter                 █████████░░░░░░░░░░░  13
particle weight calculation   ██████░░░░░░░░░░░░░░   9
state estimation              █████░░░░░░░░░░░░░░░   8
```

---

## From KB to Production

The knowledge graph feeds directly into the production pipeline:

### Script Generation (`kb script`)
- Reads the unified KG's atoms, summaries, and key themes
- Figures become explicit references in the script (e.g., "As shown in Figure 3...")
- Topic distribution guides content emphasis
- Cross-source links inform comparison segments

### Video Production (`kb produce` / `produce-video`)
- Scene importance scoring uses atom `importance_score` to allocate visual budget
- Figures from the KB are available as source material for image generation
- The ContentLibrarian tracks which KB figures are used where
- The DoP (Director of Photography) assigns visual treatments based on atom types

### Example Flow
```
KB (153 atoms, 11 figures, 88 topics)
  → Script (10 segments, references 6 figures)
    → Visual Plan (medium tier: 27% images)
      → 3 DALL-E images + Ken Burns animation
        → Final video with per-scene audio
```

---

## File Reference

| Component | File |
|-----------|------|
| Atom & Document models | [`core/models/document.py`](../core/models/document.py) |
| Knowledge Graph models | [`core/models/knowledge.py`](../core/models/knowledge.py) |
| Document Ingestor agent | [`agents/document_ingestor.py`](../agents/document_ingestor.py) |
| Content Classifier | [`core/content_classifier.py`](../core/content_classifier.py) |
| KB CLI (inspect, add, rebuild) | [`cli/kb.py`](../cli/kb.py) |
| JSON Extractor | [`core/claude_client.py`](../core/claude_client.py) |
