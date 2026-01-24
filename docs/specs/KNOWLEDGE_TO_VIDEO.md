# Knowledge-to-Video Pipeline Specification

## Overview

A multi-stage pipeline that transforms knowledge sources (papers, articles, datasets, notes) into video content through iterative refinement and adversarial synthesis. The knowledge base is the product; videos are views into it.

```
CORE PHILOSOPHY: "Knowledge Base → Multiple Productions"

┌─────────────────────────────────────────────────────────────────┐
│                      KNOWLEDGE BASE                             │
│  Papers, articles, datasets, notes, connections, insights       │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   Production 1          Production 2          Production 3
   "Intro to X"          "Deep dive Y"         "X + Y synthesis"
   (static tier)         (broll tier)          (full tier)
```

## Production Tiers

```
v1 STATIC:      Audio + single image           $0.50   2 min
v2 TEXT:        + text overlays (quotes)       $1.00   5 min
v3 ANIMATED:    + Ken Burns, motion graphics   $2.00   10 min
v4 BROLL:       + AI video (Luma)              $5.00   15 min
v5 AVATAR:      + virtual presenter            $15.00  20 min
v6 FULL:        All of the above               $30.00  30 min
```

---

# Part 1: Knowledge Base Model

## Core Data Structures

### KnowledgeProject

```python
@dataclass
class KnowledgeProject:
    """A growing knowledge base that can spawn multiple videos"""
    project_id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    
    # Sources (multiple documents, notes, links)
    sources: Dict[str, KnowledgeSource]
    
    # Unified knowledge graph across all sources
    knowledge_graph: KnowledgeGraph
    
    # User additions
    notes: Dict[str, Note]
    artifacts: Dict[str, Artifact]       # Design docs, one-pagers created
    connections: Dict[str, Connection]   # Explicit links between concepts
    
    # Generated outputs
    productions: Dict[str, Production]
    series: Dict[str, ProductionSeries]  # Adversarial series
    
    # Asset library (reusable across productions)
    asset_library: Dict[str, GeneratedAsset]
    
    # Memory namespace
    memory_namespace: str
    
    def get_source(self, source_id: str) -> KnowledgeSource: ...
    def get_atoms(self, source_ids: List[str] = None) -> List[DocumentAtom]: ...
    def get_figures(self, source_ids: List[str] = None) -> List[DocumentAtom]: ...
    def search(self, query: str, limit: int = 10) -> List[DocumentAtom]: ...
```

### KnowledgeSource

```python
class SourceType(Enum):
    PAPER = "paper"             # Academic paper (PDF)
    ARTICLE = "article"         # News article (URL or text)
    DATASET = "dataset"         # CSV, JSON data
    NOTE = "note"               # Your observations
    CODE_EXPERIMENT = "code"    # Results from trying code
    DESIGN_DOC = "design"       # One-pagers, specs you created
    TRANSCRIPT = "transcript"   # Interview, podcast transcript
    URL = "url"                 # Generic web content


@dataclass
class KnowledgeSource:
    """A single source of knowledge"""
    source_id: str
    source_type: SourceType
    
    # Original content
    title: str
    raw_content: Optional[str]
    file_path: Optional[str]
    url: Optional[str]
    
    # Extracted structure
    document_graph: Optional[DocumentGraph]  # For documents
    data_summary: Optional[DataSummary]      # For datasets
    
    # Metadata
    authors: List[str]
    date: Optional[datetime]
    tags: List[str]
    
    # Processing state
    added_at: datetime
    processed_at: Optional[datetime]
    extraction_method: str              # "pandoc", "marker", "manual"
    
    def get_atoms(self) -> List[DocumentAtom]: ...
    def get_figures(self) -> List[DocumentAtom]: ...
    def get_key_quotes(self) -> List[DocumentAtom]: ...
```

### DocumentGraph (from Stage 0)

```python
@dataclass
class DocumentAtom:
    """Smallest unit of extracted knowledge"""
    atom_id: str
    source_id: str                      # Which source this came from
    atom_type: AtomType
    
    # Content
    content: str                        # Text content or description
    raw_data: Optional[bytes]           # For figures/tables: the actual image
    
    # Location in source
    source_page: Optional[int]
    source_location: Optional[Rect]
    
    # Semantic metadata
    topics: List[str]
    entities: List[str]
    claims: List[str]                   # Factual claims made
    
    # Importance
    importance_score: float
    
    # For figures/tables
    caption: Optional[str]
    figure_number: Optional[str]
    data_summary: Optional[str]         # LLM description of what it shows


class AtomType(Enum):
    # Text atoms
    TITLE = "title"
    ABSTRACT = "abstract"
    SECTION_HEADER = "section_header"
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    CITATION = "citation"
    CLAIM = "claim"                     # A specific factual claim
    
    # Visual atoms
    FIGURE = "figure"
    CHART = "chart"
    TABLE = "table"
    EQUATION = "equation"
    DIAGRAM = "diagram"
    
    # Data atoms (from datasets)
    DATA_COLUMN = "data_column"
    DATA_ROW = "data_row"
    DATA_INSIGHT = "data_insight"       # LLM-generated insight from data
    
    # Meta atoms
    AUTHOR = "author"
    DATE = "date"
    KEYWORD = "keyword"


@dataclass
class KnowledgeGraph:
    """Unified graph across all sources"""
    atoms: Dict[str, DocumentAtom]
    
    # Relationships
    hierarchy: Dict[str, List[str]]         # Parent -> children
    references: Dict[str, List[str]]        # Atom -> atoms it references
    contradicts: Dict[str, List[str]]       # Atoms that contradict each other
    supports: Dict[str, List[str]]          # Atoms that support each other
    same_topic: Dict[str, List[str]]        # Atoms about same topic
    
    # Cross-source connections
    cross_source_links: List[CrossSourceLink]
    
    # Summaries
    topics: List[str]                       # All topics across sources
    entities: List[str]                     # All entities
    key_claims: List[str]                   # Most important claims
    
    def get_atoms_by_topic(self, topic: str) -> List[DocumentAtom]: ...
    def get_related_atoms(self, atom_id: str) -> List[DocumentAtom]: ...
    def get_contradicting_atoms(self, atom_id: str) -> List[DocumentAtom]: ...
    def search(self, query: str) -> List[DocumentAtom]: ...


@dataclass
class CrossSourceLink:
    """A relationship between atoms from different sources"""
    link_id: str
    source_atom_id: str
    target_atom_id: str
    relationship: str       # "supports", "contradicts", "extends", "applies"
    confidence: float
    auto_detected: bool     # True if LLM found it, False if user created
```

### User Additions

```python
@dataclass
class Note:
    """User's observation or insight"""
    note_id: str
    title: str
    content: str
    
    # What this note is about
    related_sources: List[str]
    related_atoms: List[str]
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    tags: List[str]


@dataclass
class Artifact:
    """Something the user created (design doc, one-pager, etc.)"""
    artifact_id: str
    artifact_type: str          # "design_doc", "one_pager", "code", "diagram"
    title: str
    
    # Content
    content: str
    file_path: Optional[str]
    
    # What it's based on
    source_ids: List[str]
    atom_ids: List[str]
    
    # Can be treated as a source itself
    as_source: Optional[KnowledgeSource]
    
    created_at: datetime


@dataclass
class Connection:
    """An explicit relationship the user has identified"""
    connection_id: str
    
    # What's connected
    source_atoms: List[str]     # Atom IDs (can be from different sources)
    
    # The insight
    relationship_type: str      # "builds_on", "contradicts", "applies_to", "combines_with", "explains"
    title: str
    description: str
    
    # Supporting reasoning
    reasoning: str
    evidence: List[str]         # Atom IDs that support this connection
    
    # Metadata
    created_at: datetime
    confidence: float           # User's confidence in this connection
    
    # Can become an atom itself for use in scripts
    as_atom: Optional[DocumentAtom]
```

### Dataset Support

```python
@dataclass
class DataSummary:
    """Summary of a dataset source"""
    source_id: str
    
    # Structure
    columns: List[ColumnInfo]
    row_count: int
    
    # Extracted insights
    insights: List[DataInsight]
    
    # Key statistics
    statistics: Dict[str, Any]
    
    # Queryable
    def query(self, sql: str) -> pd.DataFrame: ...
    def get_column(self, name: str) -> List[Any]: ...


@dataclass
class ColumnInfo:
    name: str
    dtype: str
    description: str            # LLM-generated
    sample_values: List[Any]
    statistics: Dict[str, Any]  # min, max, mean, etc.


@dataclass
class DataInsight:
    """An insight extracted from data"""
    insight_id: str
    insight_type: str           # "trend", "outlier", "correlation", "comparison"
    description: str
    
    # Evidence
    columns_involved: List[str]
    rows_involved: List[int]
    statistical_support: Dict[str, Any]
    
    # As an atom
    as_atom: DocumentAtom
```

---

# Part 2: Production Model

### Production

```python
@dataclass
class Production:
    """A video/podcast generated from the knowledge base"""
    production_id: str
    project_id: str
    
    # What this production draws from
    source_ids: List[str]
    atom_ids: List[str]             # Specific atoms to include
    connection_ids: List[str]       # Connections to highlight
    note_ids: List[str]             # User notes to incorporate
    
    # The creative direction
    production_prompt: str          # "Explain how A and B connect"
    target_audience: str            # "general", "technical", "academic"
    tone: str                       # "educational", "persuasive", "balanced"
    
    # Target specs
    target_duration: float
    target_tier: ProductionTier
    
    # Generated content
    script: Optional[VideoScript]
    assets: Dict[str, GeneratedAsset]
    timeline: Optional[Timeline]
    
    # Output
    output_path: Optional[str]
    
    # Versioning
    version: int
    previous_version_id: Optional[str]
    
    # Cost tracking
    generation_cost: float
    generation_time: float
    
    # State
    status: str                     # "draft", "generating", "complete", "failed"
    created_at: datetime
    completed_at: Optional[datetime]


class ProductionTier(Enum):
    STATIC = "static"
    TEXT_OVERLAY = "text"
    ANIMATED = "animated"
    BROLL = "broll"
    AVATAR = "avatar"
    FULL = "full"
```

### VideoScript

```python
@dataclass
class VideoScript:
    """Complete script for video production"""
    script_id: str
    production_id: str
    version: int
    
    # Content
    segments: List[ScriptSegment]
    
    # Asset manifest
    required_assets: List[AssetRequirement]
    
    # Metadata
    total_duration_estimate: float
    figures_used: List[str]
    sources_referenced: List[str]
    
    # For iterative refinement
    locked_segments: List[str]      # Segment IDs that shouldn't change


@dataclass
class ScriptSegment:
    """A segment of the script"""
    segment_id: str
    segment_type: SegmentType
    
    # Timing
    start_time: Optional[float]
    duration_estimate: float
    
    # Dialogue/Narration
    dialogue: str
    speaker: str                    # "narrator", "host", "expert"
    
    # Visual specification (tier-dependent)
    visual: VisualSpec
    
    # Source attribution
    source_atoms: List[str]         # Which atoms this draws from
    source_quotes: List[str]        # Direct quotes used
    
    # For refinement
    locked: bool = False
    notes: Optional[str] = None
    
    # Generated assets
    tts_asset_id: Optional[str]
    visual_asset_id: Optional[str]


class SegmentType(Enum):
    INTRO = "intro"
    SECTION_HEADER = "section_header"
    EXPLANATION = "explanation"
    FIGURE_CALLOUT = "figure_callout"
    DATA_HIGHLIGHT = "data_highlight"
    QUOTE = "quote"
    COMPARISON = "comparison"           # Comparing two sources/claims
    CONNECTION = "connection"           # Highlighting a user connection
    TRANSITION = "transition"
    RECAP = "recap"
    OUTRO = "outro"


@dataclass
class VisualSpec:
    """What should be shown - tier-aware"""
    
    # Tier 1: Static
    static_image: Optional[str] = None
    
    # Tier 2: Text overlay
    text_overlay: Optional[TextOverlay] = None
    
    # Tier 3: Animation
    animation: Optional[AnimationSpec] = None
    
    # Tier 4: B-roll
    broll: Optional[BrollSpec] = None
    
    # Tier 5: Avatar
    avatar: Optional[AvatarSpec] = None
    
    # Compositing
    layout: str = "full"
    
    def get_for_tier(self, tier: ProductionTier) -> 'VisualSpec':
        """Downgrade visual spec to match production tier"""
        ...


@dataclass
class TextOverlay:
    text: str
    style: str              # "quote", "title", "bullet", "statistic"
    position: str           # "center", "lower_third", "full"
    animation: str          # "fade", "typewriter", "slide"
    source_citation: Optional[str]


@dataclass
class AnimationSpec:
    animation_type: str     # "ken_burns", "parallax", "morph", "chart_build"
    source_image: str       # Atom ID
    motion_params: Dict


@dataclass
class BrollSpec:
    prompt: str
    seed_image: Optional[str]
    style: str
    continuity_group: Optional[str]
    duration: float


@dataclass
class AvatarSpec:
    avatar_id: str
    emotion: str
    gesture: Optional[str]
    position: str
```

---

# Part 3: Adversarial Series Model

## Overview

An adversarial series generates multiple productions from the same sources, 
exploring different perspectives, then uses LLM-as-judge to evaluate and 
synthesize a stronger final production.

```
Sources ──┬── Perspective A ("Pro") ────┐
          │                             │
          ├── Perspective B ("Con") ────┼── Judge ── Synthesis
          │                             │
          └── Perspective C ("Skeptic")─┘
```

## Data Structures

```python
@dataclass
class ProductionSeries:
    """A set of related productions exploring a topic from multiple angles"""
    series_id: str
    project_id: str
    name: str
    
    # The shared foundation
    source_ids: List[str]
    base_prompt: str                    # The topic/question being explored
    
    # Configuration
    target_tier: ProductionTier
    target_duration: float
    
    # Perspectives to explore
    perspectives: Dict[str, Perspective]
    
    # Judgment rounds
    judgments: List[Judgment]
    
    # Synthesis
    synthesis_production_id: Optional[str]
    
    # State
    current_round: int
    status: str                         # "defining", "generating", "judging", "synthesizing", "complete"
    
    created_at: datetime
    completed_at: Optional[datetime]


@dataclass
class Perspective:
    """A specific angle/stance to argue"""
    perspective_id: str
    series_id: str
    
    name: str                           # "Pro", "Con", "Skeptic", "Optimist", "Technical"
    
    # Instructions for this perspective
    stance: str                         # "Argue in favor of X"
    framing: str                        # "From an economic perspective..."
    
    # Guidance on source usage
    atoms_to_emphasize: List[str]       # Atoms to highlight
    atoms_to_minimize: List[str]        # Atoms to downplay (for adversarial)
    required_atoms: List[str]           # Must include these
    
    # Constraints
    tone: str                           # "confident", "cautious", "provocative"
    target_audience: str
    
    # Generated production
    production_id: Optional[str]
    production: Optional[Production]
    
    # Evaluation
    judgment_scores: Dict[str, float]   # From judge rounds
    
    created_at: datetime


@dataclass
class Judgment:
    """LLM evaluation of productions in a series"""
    judgment_id: str
    series_id: str
    round: int
    
    # What was evaluated
    perspective_ids: List[str]
    
    # Per-perspective evaluation
    evaluations: Dict[str, PerspectiveEvaluation]
    
    # Cross-perspective analysis
    gaps: List[Gap]                     # What all perspectives missed
    contradictions: List[Contradiction]  # Conflicting claims
    tensions: List[Tension]             # Valid disagreements
    
    # Synthesis recommendations
    synthesis_recommendations: List[SynthesisRecommendation]
    
    # Overall assessment
    strongest_perspective: str
    most_balanced_perspective: str
    recommended_approach: str
    
    judged_at: datetime
    judge_model: str                    # Which LLM did the judging


@dataclass
class PerspectiveEvaluation:
    """Evaluation of a single perspective"""
    perspective_id: str
    
    # Scores
    argument_strength: float            # 0-100
    evidence_usage: float               # 0-100
    logical_consistency: float          # 0-100
    source_fidelity: float              # 0-100 (does it accurately represent sources?)
    persuasiveness: float               # 0-100
    
    overall_score: float
    
    # Detailed feedback
    strengths: List[StrengthWeakness]
    weaknesses: List[StrengthWeakness]
    
    # Evidence analysis
    well_used_evidence: List[str]       # Atom IDs used effectively
    misrepresented_evidence: List[str]  # Atom IDs misrepresented
    ignored_evidence: List[str]         # Relevant atoms not used
    
    # Logical analysis
    sound_arguments: List[str]
    logical_fallacies: List[str]
    unsupported_claims: List[str]


@dataclass
class StrengthWeakness:
    description: str
    evidence: List[str]                 # Atom IDs supporting this assessment
    severity: str                       # "minor", "moderate", "major"
    segment_ids: List[str]              # Which segments this applies to


@dataclass
class Gap:
    """Something all perspectives missed"""
    description: str
    relevant_atoms: List[str]           # Evidence that should have been used
    importance: str                     # "critical", "important", "minor"
    suggested_incorporation: str        # How to include in synthesis


@dataclass
class Contradiction:
    """Conflicting claims between perspectives"""
    description: str
    perspective_a: str
    perspective_b: str
    claim_a: str
    claim_b: str
    relevant_evidence: List[str]        # Atoms that bear on this
    resolution: str                     # Which is better supported, or both valid


@dataclass
class Tension:
    """A valid disagreement (not resolvable by evidence)"""
    description: str
    perspectives_involved: List[str]
    nature: str                         # "values", "priorities", "interpretation"
    synthesis_approach: str             # How to handle in synthesis


@dataclass
class SynthesisRecommendation:
    """Recommendation for the synthesis production"""
    recommendation: str
    priority: str                       # "essential", "recommended", "optional"
    atoms_to_incorporate: List[str]
    perspectives_to_draw_from: List[str]
    segment_type_suggested: str
```

## Synthesis Production

```python
@dataclass
class SynthesisSpec:
    """Specification for generating a synthesis production"""
    series_id: str
    
    # What to incorporate
    from_judgments: List[str]           # Judgment IDs to incorporate
    
    # Structure guidance
    structure: str                      # "balanced", "thesis_antithesis", "comprehensive"
    
    # Content guidance
    must_address_gaps: List[str]        # Gap IDs that must be addressed
    must_acknowledge_tensions: List[str] # Tension IDs to acknowledge
    resolution_approach: str            # "adjudicate", "present_both", "meta_analysis"
    
    # Reuse from perspectives
    segments_to_reuse: Dict[str, List[str]]  # perspective_id -> segment_ids
    assets_to_reuse: List[str]
    
    # Target
    target_tier: ProductionTier
    target_duration: float
    target_audience: str
```

---

# Part 4: CLI Interface

## Project Management

```bash
# Create knowledge base
claude-studio kb create "Project Name" [--description "..."]

# Add sources
claude-studio kb add <project> --paper paper.pdf [--title "..."]
claude-studio kb add <project> --article article.pdf
claude-studio kb add <project> --url "https://..."
claude-studio kb add <project> --dataset data.csv [--description "..."]
claude-studio kb add <project> --note "My observation..." [--title "..."]
claude-studio kb add <project> --artifact design_doc.md --type design_doc

# Explore knowledge base
claude-studio kb show <project>
claude-studio kb sources <project>
claude-studio kb atoms <project> [--source <source_id>] [--type figures]
claude-studio kb search <project> "query"
claude-studio kb graph <project> [--output graph.png]

# Add connections
claude-studio kb connect <project> \
  --atoms "source_a:atom_1" "source_b:atom_2" \
  --relationship "builds_on" \
  --description "A's method could improve B's results" \
  [--reasoning "Because..."]

# View connections
claude-studio kb connections <project>
```

## Single Production

```bash
# Generate production from knowledge base
claude-studio kb produce <project> \
  [--sources source_1 source_2] \
  [--atoms atom_1 atom_2] \
  [--connections conn_1] \
  --prompt "Explain the key findings" \
  --tier static \
  [--duration 120] \
  [--audience general]

# Upgrade production tier
claude-studio kb upgrade <project> --production <prod_id> \
  --to-tier broll \
  [--keep-audio] \
  [--regenerate-segments 3,4,5]

# Refine specific segments
claude-studio kb regen <project> --production <prod_id> \
  --segment 4 \
  [--prompt "Make this more technical"] \
  [--provider runway]

# Lock good segments
claude-studio kb lock <project> --production <prod_id> --segments 1,2,6

# Preview
claude-studio kb preview <project> --production <prod_id> [--segment 3]
```

## Adversarial Series

```bash
# Create series
claude-studio kb series create <project> \
  --name "Series Name" \
  --prompt "What is the impact of X?" \
  --sources source_1 source_2 source_3 \
  [--tier static] \
  [--duration 120]

# Add perspectives
claude-studio kb series perspective <series> \
  --name "Pro" \
  --stance "Argue that X is beneficial" \
  [--emphasize atom_1 atom_2] \
  [--tone confident]

claude-studio kb series perspective <series> \
  --name "Con" \
  --stance "Argue that X has significant costs" \
  [--emphasize atom_3 atom_4] \
  [--tone cautious]

claude-studio kb series perspective <series> \
  --name "Skeptic" \
  --stance "Question the methodology and conclusions" \
  [--tone provocative]

# Generate perspective productions
claude-studio kb series generate <series> [--perspective Pro]

# Run judge
claude-studio kb series judge <series> [--round 1]

# View judgment
claude-studio kb series judgment <series> [--round 1]

# Generate synthesis
claude-studio kb series synthesize <series> \
  [--structure balanced] \
  [--tier broll]

# Iterate
claude-studio kb series perspective <series> \
  --name "Devil's Advocate" \
  --stance "Challenge the synthesis"

claude-studio kb series judge <series> --round 2
claude-studio kb series synthesize <series> --round 2

# Export series report
claude-studio kb series report <series> --output report.md
```

## Inspection & Analysis

```bash
# Show production details
claude-studio kb production show <project> <prod_id>

# Show script
claude-studio kb production script <project> <prod_id>

# Show assets
claude-studio kb production assets <project> <prod_id>

# Compare productions
claude-studio kb compare <project> <prod_id_1> <prod_id_2>

# Cost analysis
claude-studio kb cost <project> [--production <prod_id>] [--series <series_id>]

# Export knowledge base
claude-studio kb export <project> --output project_export.json

# Import/merge knowledge bases
claude-studio kb import <project> --from other_project_export.json
```

---

# Part 5: Execution Model

## Phase-Based Execution

```python
@dataclass
class ExecutionPlan:
    """Plan for generating a production"""
    production_id: str
    phases: List[ExecutionPhase]


@dataclass
class ExecutionPhase:
    phase_id: str
    phase_type: str             # "extraction", "script", "audio", "video", "assembly"
    
    groups: List[TaskGroup]
    
    depends_on: List[str]       # Phase IDs
    skip_if: Optional[Callable] # Condition to skip
    
    estimated_duration: float
    estimated_cost: float


@dataclass
class TaskGroup:
    group_id: str
    tasks: List[str]            # Task/scene IDs
    mode: ExecutionMode         # PARALLEL or SEQUENTIAL
    provider: str
    
    # For sequential (chaining)
    chain_type: Optional[str]   # "luma_extend", "keyframe"


# Example execution plan for BROLL tier production:

plan = ExecutionPlan(
    production_id="prod_123",
    phases=[
        # Phase 1: Script (if not cached)
        ExecutionPhase(
            phase_id="script",
            phase_type="script",
            groups=[
                TaskGroup(
                    tasks=["generate_script"],
                    mode=SEQUENTIAL,
                    provider="llm",
                ),
            ],
        ),
        
        # Phase 2: Audio generation
        ExecutionPhase(
            phase_id="audio",
            phase_type="audio",
            groups=[
                TaskGroup(
                    tasks=["tts_seg_1", "tts_seg_2", "tts_seg_3", ...],
                    mode=PARALLEL,
                    provider="elevenlabs",
                ),
            ],
            depends_on=["script"],
        ),
        
        # Phase 3: Video generation (parallel groups, sequential within chains)
        ExecutionPhase(
            phase_id="video",
            phase_type="video",
            groups=[
                # Ken Burns on figures
                TaskGroup(
                    group_id="figures",
                    tasks=["ken_burns_fig1", "ken_burns_fig2"],
                    mode=PARALLEL,
                    provider="ffmpeg",
                ),
                # Luma B-roll chain A
                TaskGroup(
                    group_id="broll_chain_a",
                    tasks=["broll_1", "broll_3"],
                    mode=SEQUENTIAL,
                    provider="luma",
                    chain_type="luma_extend",
                ),
                # Luma B-roll chain B
                TaskGroup(
                    group_id="broll_chain_b",
                    tasks=["broll_2"],
                    mode=PARALLEL,
                    provider="luma",
                ),
            ],
            depends_on=["script"],
        ),
        
        # Phase 4: Assembly
        ExecutionPhase(
            phase_id="assembly",
            phase_type="assembly",
            groups=[
                TaskGroup(
                    tasks=["build_timeline", "render"],
                    mode=SEQUENTIAL,
                    provider="ffmpeg",
                ),
            ],
            depends_on=["audio", "video"],
        ),
    ],
)
```

## Adversarial Series Execution

```python
# Series execution plan:

series_plan = SeriesExecutionPlan(
    series_id="series_456",
    stages=[
        # Stage 1: Generate all perspectives (parallel)
        SeriesStage(
            stage_type="generate_perspectives",
            perspective_ids=["pro", "con", "skeptic"],
            parallel=True,
        ),
        
        # Stage 2: Judge
        SeriesStage(
            stage_type="judge",
            round=1,
            depends_on=["generate_perspectives"],
        ),
        
        # Stage 3: Synthesize
        SeriesStage(
            stage_type="synthesize",
            round=1,
            depends_on=["judge"],
        ),
        
        # Optional: More rounds
        # Stage 4: New perspective based on synthesis
        # Stage 5: Judge round 2
        # Stage 6: Synthesize round 2
    ],
)
```

---

# Part 6: Memory Integration

## Namespace Structure

```
/org/{org}/kb/{project}/
├── config.json                     # Project configuration
├── sources/
│   ├── {source_id}/
│   │   ├── metadata.json
│   │   ├── raw_content.txt
│   │   ├── document_graph.json
│   │   └── figures/
│   │       ├── figure_1.png
│   │       └── ...
│   └── ...
├── knowledge_graph.json            # Unified graph
├── user/
│   ├── notes/
│   │   └── {note_id}.json
│   ├── artifacts/
│   │   └── {artifact_id}.json
│   └── connections/
│       └── {connection_id}.json
├── productions/
│   └── {production_id}/
│       ├── config.json
│       ├── script.json
│       ├── assets/
│       │   ├── tts_seg_1.mp3
│       │   └── ...
│       ├── timeline.json
│       └── output/
│           └── final.mp4
├── series/
│   └── {series_id}/
│       ├── config.json
│       ├── perspectives/
│       │   ├── pro.json
│       │   └── con.json
│       ├── judgments/
│       │   ├── round_1.json
│       │   └── round_2.json
│       └── synthesis/
│           └── round_1.json
└── learnings/
    ├── source_insights.json        # What we learned about sources
    ├── production_patterns.json    # What production approaches worked
    └── series_learnings.json       # Adversarial insights
```

## Cross-Project Learning

```
/org/{org}/learnings/
├── provider/{provider}/            # Provider-specific learnings
├── format/{format}/                # Format-specific (podcast, explainer)
├── topic/{topic}/                  # Topic-specific patterns
└── adversarial/                    # Adversarial synthesis patterns
    ├── effective_perspectives.json
    ├── judge_patterns.json
    └── synthesis_strategies.json
```

---

# Part 7: Example Workflows

## Workflow 1: Single Paper Explainer

```bash
# Create project
claude-studio kb create "CRISPR Cancer Treatment"

# Add paper
claude-studio kb add crispr --paper crispr_paper.pdf

# Quick static production
claude-studio kb produce crispr \
  --prompt "Explain this paper's key findings for a general audience" \
  --tier static \
  --duration 180

# Review, then upgrade
claude-studio kb upgrade crispr --production prod_001 \
  --to-tier broll \
  --keep-audio
```

## Workflow 2: Multi-Source Analysis

```bash
# Create project
claude-studio kb create "AI Regulation Analysis"

# Add diverse sources
claude-studio kb add ai_reg --paper eu_ai_act.pdf
claude-studio kb add ai_reg --article nyt_coverage.txt
claude-studio kb add ai_reg --url "https://techcrunch.com/..."
claude-studio kb add ai_reg --dataset enforcement_actions.csv

# Add your analysis
claude-studio kb add ai_reg --note "The EU approach differs from US in these ways..."

# Connect insights across sources
claude-studio kb connect ai_reg \
  --atoms "eu_ai_act:article_5" "enforcement:row_47" \
  --relationship "contradicts" \
  --description "The act requires X but enforcement data shows Y"

# Generate synthesis video
claude-studio kb produce ai_reg \
  --prompt "Analyze the gap between AI regulation intent and enforcement reality" \
  --tier animated
```

## Workflow 3: Adversarial Policy Analysis

```bash
# Create project with news + data
claude-studio kb create "Immigration Economics"
claude-studio kb add immig --url "https://nytimes.com/..."
claude-studio kb add immig --url "https://wsj.com/..."
claude-studio kb add immig --dataset census_data.csv
claude-studio kb add immig --dataset border_stats.csv

# Create adversarial series
claude-studio kb series create immig \
  --name "Immigration Economic Impact" \
  --prompt "What is the economic impact of immigration?"

# Define perspectives
claude-studio kb series perspective immig_series \
  --name "Pro-Immigration" \
  --stance "Argue immigration is economically beneficial"

claude-studio kb series perspective immig_series \
  --name "Immigration-Skeptic" \
  --stance "Argue immigration has significant economic costs"

# Generate and judge
claude-studio kb series generate immig_series
claude-studio kb series judge immig_series

# Review judgment, then synthesize
claude-studio kb series judgment immig_series
claude-studio kb series synthesize immig_series --tier broll
```

## Workflow 4: Iterative Research Project

```bash
# Start with one paper
claude-studio kb create "Transformer Architectures"
claude-studio kb add transformers --paper attention_is_all_you_need.pdf

# Initial video
claude-studio kb produce transformers \
  --prompt "Explain the transformer architecture" \
  --tier static

# Later: Add related paper
claude-studio kb add transformers --paper bert.pdf

# Connect them
claude-studio kb connect transformers \
  --atoms "attention:encoder" "bert:bidirectional" \
  --relationship "extends"

# New video about the connection
claude-studio kb produce transformers \
  --sources attention bert \
  --connections conn_001 \
  --prompt "How BERT built on and extended the original transformer"

# Even later: Add your implementation notes
claude-studio kb add transformers \
  --note "Implemented attention from scratch, key insight was..." \
  --artifact my_implementation.py --type code

# Video incorporating your experience
claude-studio kb produce transformers \
  --prompt "Practical lessons from implementing transformers" \
  --notes note_001
```

---

# Part 8: Future Extensions

## Multi-Language Support

```python
# Generate in multiple languages
production = kb.produce(
    prompt="...",
    languages=["en", "es", "zh"],  # Parallel TTS in each
)
```

## Collaborative Knowledge Bases

```python
# Share knowledge base
kb.share(users=["collaborator@example.com"], permission="edit")

# Merge another user's additions
kb.merge(from_user="collaborator", changes=["note_005", "conn_003"])
```

## Live Source Updates

```python
# Monitor sources for updates
kb.watch(source_id="news_feed", check_interval="1h")

# Auto-regenerate when sources change
production.auto_update = True
```

## Interactive Exploration

```bash
# Chat with knowledge base
claude-studio kb chat <project>

> What does paper A say about X?
> How does that compare to the dataset?
> Generate a video segment explaining this
```

---

# Summary

This spec enables:

1. **Knowledge-first approach** - Build understanding, videos follow
2. **Multi-source synthesis** - Papers, articles, data, notes
3. **User insights as first-class** - Your connections and notes matter
4. **Adversarial reasoning** - Explore multiple perspectives, stronger synthesis
5. **Iterative refinement** - Cheap drafts → polished productions
6. **Asset reuse** - TTS, B-roll cached across productions
7. **Learning over time** - Patterns improve future productions

The knowledge base is the product. Videos are just one way to view it.
