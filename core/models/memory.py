"""Memory models for short-term and long-term memory tracking"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class RunStage(Enum):
    """Stages of a production run"""
    INITIALIZED = "initialized"
    ANALYZING_ASSETS = "analyzing_assets"
    PLANNING_PILOTS = "planning_pilots"
    GENERATING_SCRIPTS = "generating_scripts"
    GENERATING_VIDEO = "generating_video"
    GENERATING_AUDIO = "generating_audio"
    EVALUATING = "evaluating"
    EDITING = "editing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageEvent:
    """Event in the run timeline"""
    stage: RunStage
    timestamp: datetime
    duration_ms: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PilotMemory:
    """Memory of a pilot's performance"""
    pilot_id: str
    tier: str
    allocated_budget: float
    spent_budget: float
    scenes_generated: int
    quality_score: Optional[float] = None
    status: str = "running"  # running, approved, rejected
    rejection_reason: Optional[str] = None


@dataclass
class AssetMemory:
    """Memory of generated assets"""
    asset_id: str
    asset_type: str  # video, audio, image
    path: str
    scene_id: Optional[str] = None
    duration: Optional[float] = None
    cost: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ShortTermMemory:
    """State within a single production run"""
    run_id: str
    concept: str
    budget_total: float
    budget_spent: float = 0
    audio_tier: str = "SIMPLE_OVERLAY"

    # Current state
    current_stage: RunStage = RunStage.INITIALIZED
    progress_percent: float = 0

    # Pilot tracking
    pilots: List[PilotMemory] = field(default_factory=list)
    winning_pilot_id: Optional[str] = None

    # Scene tracking
    total_scenes: int = 0
    scenes_completed: int = 0

    # Asset tracking
    assets: List[AssetMemory] = field(default_factory=list)

    # Timeline
    timeline: List[StageEvent] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Seed assets used
    seed_asset_ids: List[str] = field(default_factory=list)
    extracted_themes: List[str] = field(default_factory=list)
    extracted_colors: List[str] = field(default_factory=list)

    # Final output paths
    final_video_path: Optional[str] = None


@dataclass
class UserPreferences:
    """User preferences learned over time"""
    preferred_style: str = "balanced"  # safe, dynamic, cinematic
    preferred_tier: Optional[str] = None
    default_voice: str = "nova"
    default_voice_speed: float = 1.0
    default_music_mood: str = "ambient"
    default_audio_tier: str = "SIMPLE_OVERLAY"
    brand_colors: List[str] = field(default_factory=list)
    quality_threshold: int = 75  # Minimum acceptable score
    max_budget_per_run: Optional[float] = None


@dataclass
class ProductionRecord:
    """Record of a completed production"""
    run_id: str
    concept: str
    timestamp: datetime

    # Results
    status: str  # completed, failed, cancelled
    winning_tier: Optional[str] = None
    final_score: Optional[float] = None
    total_cost: float = 0
    duration_seconds: float = 0

    # What worked
    scenes_count: int = 0
    edit_style_used: str = "safe"

    # User feedback
    user_rating: Optional[int] = None  # 1-5
    user_notes: Optional[str] = None

    # Paths to outputs
    final_video_path: Optional[str] = None
    edl_path: Optional[str] = None


@dataclass
class LearnedPattern:
    """Pattern learned from successful productions"""
    pattern_name: str  # e.g., "podcast_intro", "product_demo"

    # Recommendations based on history
    recommended_tier: str
    recommended_scenes: int
    recommended_duration: int
    recommended_edit_style: str

    # Stats
    times_used: int = 0
    avg_score: float = 0
    avg_cost: float = 0

    # Keywords that trigger this pattern
    keywords: List[str] = field(default_factory=list)


@dataclass
class ProviderLearning:
    """What we learned about a provider from a single run"""
    provider: str  # "luma", "runway", etc.
    run_id: str
    timestamp: datetime

    # Overall assessment
    overall_success: bool = True
    adherence_score: float = 0  # 0-100: Did output match prompts?
    quality_score: float = 0  # 0-100: Technical quality

    # What worked
    effective_patterns: List[str] = field(default_factory=list)  # Prompt patterns that worked
    strengths_observed: List[str] = field(default_factory=list)  # What provider did well

    # What didn't work
    ineffective_patterns: List[str] = field(default_factory=list)  # Prompt patterns that failed
    weaknesses_observed: List[str] = field(default_factory=list)  # What provider struggled with

    # Actionable tips
    prompt_tips: List[str] = field(default_factory=list)  # Specific advice for prompts
    avoid_list: List[str] = field(default_factory=list)  # Things to avoid

    # Context
    concept_type: str = ""  # "intro", "demo", etc.
    prompt_samples: List[Dict[str, Any]] = field(default_factory=list)  # {"prompt": "...", "result": "good/bad", "notes": "..."}


@dataclass
class ProviderKnowledge:
    """Accumulated knowledge about a provider from all runs"""
    provider: str
    total_runs: int = 0
    avg_adherence: float = 0
    avg_quality: float = 0

    # Aggregated learnings
    known_strengths: List[str] = field(default_factory=list)
    known_weaknesses: List[str] = field(default_factory=list)
    prompt_guidelines: List[str] = field(default_factory=list)
    avoid_list: List[str] = field(default_factory=list)

    # Best practices discovered
    best_prompt_patterns: List[str] = field(default_factory=list)
    optimal_settings: Dict[str, Any] = field(default_factory=dict)  # duration, resolution, etc.

    # Recent learnings (for context)
    recent_learnings: List[ProviderLearning] = field(default_factory=list)


@dataclass
class LongTermMemory:
    """Persistent memory across all runs"""
    # User preferences
    preferences: UserPreferences = field(default_factory=UserPreferences)

    # Production history
    total_runs: int = 0
    total_spent: float = 0
    production_history: List[ProductionRecord] = field(default_factory=list)

    # Learned patterns
    patterns: Dict[str, LearnedPattern] = field(default_factory=dict)

    # Provider knowledge (learned from runs)
    provider_knowledge: Dict[str, ProviderKnowledge] = field(default_factory=dict)

    # Favorite/saved assets
    saved_assets: List[AssetMemory] = field(default_factory=list)

    # Brand assets (logos, colors, etc.)
    brand_assets: List[Dict[str, Any]] = field(default_factory=list)

    # Last updated
    updated_at: Optional[datetime] = None
