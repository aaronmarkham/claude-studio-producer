"""Training pipeline for podcast generation calibration"""

from .models import (
    TranscriptionResult,
    WordTimestamp,
    TranscriptSegment,
    TrainingPair,
    AlignedSegment,
    SegmentType,
    StructureProfile,
    StyleProfile,
    AggregatedProfile,
    DepthTarget,
    PodcastDepth,
    LossMetrics,
    TrainingConfig,
    TrialResult,
)

from .transcription import transcribe_podcast
from .analysis import classify_segments, extract_structure_profile, extract_style_profile
from .synthesis import synthesize_profiles, store_profile_in_memory
from .loss import (
    calculate_duration_loss,
    calculate_coverage_loss,
    calculate_structure_loss,
    calculate_quality_loss,
    calculate_rouge_loss,
    calculate_all_metrics,
)
from .trainer import run_training_loop

__all__ = [
    # Models
    "TranscriptionResult",
    "WordTimestamp",
    "TranscriptSegment",
    "TrainingPair",
    "AlignedSegment",
    "SegmentType",
    "StructureProfile",
    "StyleProfile",
    "AggregatedProfile",
    "DepthTarget",
    "PodcastDepth",
    "LossMetrics",
    "TrainingConfig",
    "TrialResult",
    # Functions
    "transcribe_podcast",
    "classify_segments",
    "extract_structure_profile",
    "extract_style_profile",
    "synthesize_profiles",
    "store_profile_in_memory",
    "calculate_duration_loss",
    "calculate_coverage_loss",
    "calculate_structure_loss",
    "calculate_quality_loss",
    "calculate_rouge_loss",
    "calculate_all_metrics",
    "run_training_loop",
]
