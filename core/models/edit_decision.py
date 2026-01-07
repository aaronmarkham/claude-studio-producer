"""
Edit Decision List (EDL) models for video assembly

These models represent the final editing decisions that combine
generated video scenes into cohesive final cuts.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class ExportFormat(Enum):
    """Supported EDL export formats"""
    JSON = "json"
    FCPXML = "fcpxml"  # Final Cut Pro XML
    EDL_CMX3600 = "cmx3600"  # Industry standard EDL format
    DAVINCI = "davinci"  # DaVinci Resolve
    PREMIERE = "premiere"  # Adobe Premiere Pro XML


@dataclass
class EditDecision:
    """
    A single edit decision for one scene in the final cut.

    Specifies which video variation to use, trim points, and transitions.
    """
    scene_id: str
    selected_variation: int  # Which variation (0, 1, 2, etc.)
    video_url: str  # Path or URL to the selected video file
    audio_url: Optional[str] = None  # Optional separate audio track

    # Trim points (seconds)
    in_point: float = 0.0  # Start trim
    out_point: Optional[float] = None  # End trim (None = use full duration)

    # Transition into this scene
    transition_in: str = "cut"  # "cut", "dissolve", "fade_in", "wipe"
    transition_in_duration: float = 0.0  # Duration in seconds

    # Transition out of this scene
    transition_out: str = "cut"  # "cut", "dissolve", "fade_out", "wipe"
    transition_out_duration: float = 0.0  # Duration in seconds

    # Timing
    start_time: float = 0.0  # Position in final timeline (seconds)
    duration: Optional[float] = None  # Calculated duration after trims

    # Metadata
    notes: str = ""  # Editorial notes


@dataclass
class EditCandidate:
    """
    One complete edit candidate with a specific editorial approach.

    Contains all edit decisions needed to assemble a final cut.
    """
    candidate_id: str
    name: str  # Human-readable name (e.g., "Safe Cut", "Dynamic Edit")
    style: str  # Editorial approach: "safe", "creative", "balanced"

    decisions: List[EditDecision] = field(default_factory=list)

    # Metrics
    total_duration: float = 0.0  # Total runtime in seconds
    estimated_quality: float = 0.0  # 0-100 score

    # Editorial notes
    description: str = ""  # What makes this edit unique
    reasoning: str = ""  # Why these decisions were made

    # Continuity analysis
    continuity_issues: List[str] = field(default_factory=list)
    continuity_score: float = 100.0  # 0-100, higher is better


@dataclass
class EditDecisionList:
    """
    Collection of edit candidates for a project.

    Typically includes 2-3 candidates with different editorial approaches
    for the user to choose from.
    """
    edl_id: str
    project_name: str = ""

    candidates: List[EditCandidate] = field(default_factory=list)
    recommended_candidate_id: Optional[str] = None  # Which one to use by default

    # Export options
    export_formats: List[ExportFormat] = field(default_factory=list)

    # Metadata
    created_timestamp: Optional[str] = None
    total_scenes: int = 0
    original_request: str = ""  # User's original video concept


@dataclass
class HumanFeedback:
    """
    Human review feedback for an edit candidate.

    Allows human-in-the-loop refinement of edit decisions.
    """
    candidate_id: str
    approved: bool
    notes: str = ""
    requested_changes: List[str] = field(default_factory=list)

    # Specific feedback
    scenes_to_recut: List[str] = field(default_factory=list)
    transition_adjustments: List[str] = field(default_factory=list)
    pacing_notes: str = ""
