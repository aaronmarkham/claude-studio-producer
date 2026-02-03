"""Data models for training pipeline"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from core.models.knowledge import KnowledgeGraph as DocumentGraph


class SegmentType(str, Enum):
    """Types of podcast segments"""
    INTRO = "intro"
    BACKGROUND = "background"
    PROBLEM_STATEMENT = "problem"
    METHODOLOGY = "methodology"
    KEY_FINDING = "key_finding"
    FIGURE_DISCUSSION = "figure"
    IMPLICATION = "implication"
    LIMITATION = "limitation"
    CONCLUSION = "conclusion"
    TANGENT = "tangent"
    TRANSITION = "transition"


class PodcastDepth(str, Enum):
    """Podcast depth levels"""
    OVERVIEW = "overview"           # 3-5 min
    STANDARD = "standard"           # 10-15 min (target)
    DEEP_DIVE = "deep_dive"         # 20-30 min
    COMPREHENSIVE = "comprehensive" # 45+ min


@dataclass
class WordTimestamp:
    """Individual word with timing"""
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0


@dataclass
class TranscriptSegment:
    """A segment of the transcript (sentence or paragraph level)"""
    segment_id: str
    text: str
    start_time: float
    end_time: float
    duration: float

    # Detected type (filled in by analysis phase)
    segment_type: Optional[SegmentType] = None

    # Linked to PDF atoms (filled in by alignment phase)
    linked_atoms: List[str] = field(default_factory=list)


@dataclass
class TranscriptionResult:
    """Result of transcribing a podcast MP3"""
    source_path: str
    transcript_text: str

    # Word-level timing (for alignment)
    word_timestamps: List[WordTimestamp]

    # Detected segments with timing
    segments: List[TranscriptSegment]

    # Audio metadata
    total_duration: float
    speaker_id: Optional[str] = None

    # Quality metrics
    confidence: float = 0.0
    language: str = "en"


@dataclass
class AlignedSegment:
    """A transcript segment aligned to PDF content"""
    segment_id: str
    transcript_segment: TranscriptSegment

    # What PDF content this segment discusses
    primary_atoms: List[str] = field(default_factory=list)
    referenced_figures: List[str] = field(default_factory=list)

    # Segment classification
    segment_type: SegmentType = SegmentType.INTRO

    # Content analysis
    key_concepts: List[str] = field(default_factory=list)
    technical_terms: List[str] = field(default_factory=list)
    analogies_used: List[str] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)

    # Timing
    words_per_minute: float = 0.0
    density_score: float = 0.0


@dataclass
class StructureProfile:
    """Extracted structure patterns from a podcast"""

    # Segment sequence
    segment_sequence: List[SegmentType]
    segment_counts: Dict[str, int]

    # Timing patterns
    total_duration: float
    segment_durations: Dict[str, List[float]]
    avg_segment_duration: float

    # Content density
    words_per_minute: float
    concepts_per_minute: float
    figures_discussed: int
    figure_discussion_duration: float

    # Structure patterns
    intro_percentage: float
    methodology_percentage: float
    findings_percentage: float
    conclusion_percentage: float

    # Transition patterns
    transition_phrases: List[str] = field(default_factory=list)


@dataclass
class StyleProfile:
    """Extracted style patterns from a podcast"""

    # Voice characteristics
    speaker_id: str
    speaker_gender: str

    # Language patterns
    avg_sentence_length: float
    vocabulary_complexity: float
    jargon_density: float

    # Engagement markers
    questions_per_minute: float
    analogies_per_segment: float
    enthusiasm_markers: List[str] = field(default_factory=list)

    # Explanation patterns
    definition_style: str = "inline"
    example_frequency: float = 0.0

    # Phrasing templates
    intro_phrases: List[str] = field(default_factory=list)
    transition_phrases: List[str] = field(default_factory=list)
    emphasis_phrases: List[str] = field(default_factory=list)
    conclusion_phrases: List[str] = field(default_factory=list)

    # Figure discussion style
    figure_intro_pattern: str = ""
    figure_explanation_depth: str = "moderate"


@dataclass
class DepthTarget:
    """Targets for a specific depth level"""
    depth: PodcastDepth

    duration_range: Tuple[float, float]
    segment_count_range: Tuple[int, int]
    concepts_per_segment: Tuple[int, int]
    figure_coverage: float

    # Derived from training data analysis
    example_pair_ids: List[str] = field(default_factory=list)


@dataclass
class AggregatedProfile:
    """Combined profile from all training pairs"""

    # Structure template
    canonical_segment_sequence: List[SegmentType]
    segment_duration_targets: Dict[str, Tuple[float, float]]

    # Timing targets by depth level
    depth_targets: Dict[str, DepthTarget]

    # Style variations (by speaker/gender)
    style_variants: Dict[str, StyleProfile]

    # Common patterns
    universal_intro_patterns: List[str]
    universal_transition_patterns: List[str]
    universal_figure_patterns: List[str]

    # Quality thresholds learned from data
    min_coverage: float
    target_words_per_minute: Tuple[float, float]
    target_concepts_per_minute: Tuple[float, float]

    # Version tracking
    version: str
    training_pairs_used: List[str]
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "canonical_segment_sequence": [s.value for s in self.canonical_segment_sequence],
            "segment_duration_targets": self.segment_duration_targets,
            "depth_targets": {k: vars(v) for k, v in self.depth_targets.items()},
            "style_variants": {k: vars(v) for k, v in self.style_variants.items()},
            "universal_intro_patterns": self.universal_intro_patterns,
            "universal_transition_patterns": self.universal_transition_patterns,
            "universal_figure_patterns": self.universal_figure_patterns,
            "min_coverage": self.min_coverage,
            "target_words_per_minute": self.target_words_per_minute,
            "target_concepts_per_minute": self.target_concepts_per_minute,
            "version": self.version,
            "training_pairs_used": self.training_pairs_used,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }


@dataclass
class TrainingPair:
    """A paired PDF + podcast for training"""
    pair_id: str

    # Source files
    pdf_path: str
    audio_path: str

    # Extracted content
    document_graph: Optional[DocumentGraph] = None
    transcription: Optional[TranscriptionResult] = None

    # Analysis results (filled in Phase 2)
    aligned_segments: Optional[List[AlignedSegment]] = None
    structure_profile: Optional[StructureProfile] = None
    style_profile: Optional[StyleProfile] = None

    # Metadata
    speaker_gender: str = "unknown"
    source: str = "journalclub"
    duration_minutes: float = 0.0


@dataclass
class LossMetrics:
    """Metrics for evaluating generated podcast quality"""

    # Duration loss (lower is better)
    duration_loss: float
    duration_generated: float
    duration_reference: float

    # Coverage loss (lower is better)
    coverage_loss: float
    concepts_mentioned: int
    concepts_total: int
    concepts_missed: List[str]

    # Structure loss (lower is better)
    structure_loss: float
    segment_type_accuracy: float
    sequence_similarity: float

    # Quality scores (higher is better, inverted for loss)
    engagement_score: float
    clarity_score: float
    accuracy_score: float
    quality_loss: float

    # ROUGE scores (higher is better)
    rouge_1: float
    rouge_2: float
    rouge_l: float
    rouge_loss: float

    # Combined loss
    total_loss: float

    # Metadata
    trial_id: str
    pair_id: str
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class TrainingConfig:
    """Configuration for training run"""
    max_trials: int = 5
    convergence_threshold: float = 0.05
    convergence_window: int = 2

    # Loss weights (structure disabled - requires expensive segment classification of generated content)
    loss_weights: Dict[str, float] = field(default_factory=lambda: {
        "duration": 0.30,
        "coverage": 0.30,
        "structure": 0.00,  # Disabled - would need to classify generated segments
        "quality": 0.25,
        "rouge": 0.15,
    })

    # Target depth for training
    target_depth: PodcastDepth = PodcastDepth.STANDARD


@dataclass
class TrialResult:
    """Result of a single training trial"""
    trial_id: str
    trial_number: int

    # Per-pair results
    pair_results: Dict[str, LossMetrics]

    # Aggregated metrics
    avg_total_loss: float
    avg_duration_loss: float
    avg_coverage_loss: float
    avg_structure_loss: float
    avg_quality_loss: float
    avg_rouge_loss: float

    # Generated artifacts (for review)
    generated_scripts: Dict[str, str]
    generated_audio: Dict[str, str]

    # Prompt version used
    prompt_version: str
    profile_version: str

    timestamp: datetime = field(default_factory=datetime.now)
