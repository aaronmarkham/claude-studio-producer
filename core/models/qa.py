"""QA visual analysis models for enriched quality assessment"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class FrameAnalysis:
    """What was observed in a single extracted frame"""
    frame_index: int
    timestamp: float
    description: str
    detected_elements: List[str]
    detected_camera: str
    lighting: str
    color_palette: List[str]
    artifacts_detected: List[str]


@dataclass
class QAVisualAnalysis:
    """Complete visual analysis of a generated video - what was actually observed"""
    frames_analyzed: int
    frame_analyses: List[FrameAnalysis]

    # Aggregated across frames
    consistent_elements: List[str]       # Present in ALL frames
    inconsistent_elements: List[str]     # Appear/disappear between frames
    overall_description: str
    primary_subject: str
    setting: str
    action: str

    # Expected vs observed comparison
    expected_elements: List[str]         # From scene description
    matched_elements: List[str]          # Expected AND observed
    missing_elements: List[str]          # Expected but NOT observed
    unexpected_elements: List[str]       # Observed but NOT expected

    # Provider learning
    provider_observations: Optional[Dict[str, Any]] = None
    # Contains: prompt_interpretation, strengths, weaknesses

    # For chained videos
    continuity_score: Optional[float] = None
    transition_timestamp: Optional[float] = None
