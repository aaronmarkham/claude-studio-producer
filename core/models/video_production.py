"""
Video production models for transcript-led video generation.

These models bridge the podcast training pipeline (AlignedSegment)
with visual production (DALL-E + Luma + FFmpeg composition).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from core.training.models import AlignedSegment, SegmentType


@dataclass
class VideoScene:
    """
    A scene for video production, derived from podcast segment.

    Wraps an AlignedSegment with visual metadata for production planning.
    Each scene will generate one visual asset (DALL-E image with optional Luma animation).
    """
    scene_id: str
    title: str                          # From segment key_concepts[0]
    concept: str                        # One-sentence summary
    transcript_segment: str             # Verbatim cleaned transcript
    start_time: float
    end_time: float

    # From training pipeline
    segment_type: SegmentType
    key_concepts: List[str] = field(default_factory=list)
    technical_terms: List[str] = field(default_factory=list)
    referenced_figures: List[str] = field(default_factory=list)

    # Computed for visuals (from SEGMENT_VISUAL_MAPPING)
    visual_complexity: str = "medium"   # "low", "medium", "high", "none"
    animation_candidate: bool = False   # Should this be animated with Luma?
    ken_burns_enabled: bool = False     # Use Ken Burns effect for static images?

    # Data quality flags
    title_is_fallback: bool = False     # True if title came from transcript, not key_concepts

    @property
    def duration(self) -> float:
        """Scene duration in seconds"""
        return self.end_time - self.start_time


@dataclass
class VisualPlan:
    """
    Complete visual plan for a scene.

    Specifies how to generate and display the visual for this scene,
    including DALL-E prompt, Luma animation config, and display settings.
    """
    scene_id: str

    # DALL-E configuration
    dalle_prompt: str
    dalle_style: str                    # From SEGMENT_VISUAL_MAPPING
    dalle_settings: Dict[str, Any] = field(default_factory=dict)

    # Luma animation (if applicable)
    animate_with_luma: bool = False
    luma_prompt: Optional[str] = None
    luma_settings: Optional[Dict[str, Any]] = None

    # On-screen elements
    on_screen_text: Optional[str] = None        # Key concept to display
    text_position: str = "bottom-left"          # "bottom-left", "bottom-center", etc.

    # Transitions
    transition_in: str = "fade"                 # "fade", "cut", "slide_left", "zoom_in"
    transition_out: str = "fade"

    # Ken Burns for static images
    ken_burns: Optional[Dict[str, Any]] = None  # {"enabled": bool, "direction": str, "duration_match": str}


@dataclass
class SceneAssets:
    """
    Generated assets for a single scene.

    Tracks the paths to generated images/videos and their display timing.
    """
    scene_id: str
    image_path: str                     # DALL-E output
    video_path: Optional[str] = None    # Luma output if animated
    display_start: float = 0.0          # When to display in final timeline
    display_end: float = 0.0            # When to stop displaying
    visual_plan: Optional[VisualPlan] = None


@dataclass
class AudioPatch:
    """
    A small audio patch for surgical edits (e.g., transition phrases).

    Used when cleanup requires adding a short bridging phrase via TTS.
    """
    patch_id: str
    text: str                           # Text to synthesize
    insert_time: float                  # Where to insert in timeline
    duration: float                     # Expected duration
    audio_path: Optional[str] = None    # Path to generated audio file
    volume_db: float = 0.0              # Volume adjustment


@dataclass
class AssetManifest:
    """
    Complete manifest of all generated assets for a video project.

    Contains all scene assets, audio patches, and render settings
    needed to compose the final video.
    """
    scenes: List[SceneAssets] = field(default_factory=list)
    audio_patches: List[AudioPatch] = field(default_factory=list)
    total_duration: float = 0.0
    render_settings: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    project_id: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class CleanupDecision:
    """
    A single transcript cleanup decision for transparency.

    Tracks what was changed, why, and optionally how to patch with TTS.
    """
    location: str                       # Timestamp or segment ID
    original_text: str
    action: str                         # "remove_filler", "remove_restatement", "bridge_needed"
    result_text: str
    rationale: str
    elevenlabs_patch: Optional[AudioPatch] = None
