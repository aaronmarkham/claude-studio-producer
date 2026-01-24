"""Data models for Claude Studio Producer"""

from .seed_assets import (
    SeedAssetType,
    AssetRole,
    SeedAsset,
    SeedAssetRef,
    SeedAssetCollection,
)
from .production_request import ProductionRequest
from .audio import (
    AudioTier,
    VoiceStyle,
    MusicMood,
    SyncPoint,
    VoiceoverSpec,
    MusicSpec,
    SoundEffectSpec,
    SceneAudio,
    ProjectAudio,
    WordTiming,
    GeneratedAudio,
    VoiceoverResult,
    SyncPointResult,
    TimeStretch,
    SyncedAudioResult,
    MixSettings,
    MixedAudio,
    AudioQAResult,
)
from .edit_decision import (
    ExportFormat,
    EditDecision,
    EditCandidate,
    EditDecisionList,
    HumanFeedback,
)
from .render import (
    TrackType,
    TransitionType,
    AudioTrack,
    Transition,
    RenderConfig,
    RenderResult,
    RenderJob,
)
from .qa import (
    FrameAnalysis,
    QAVisualAnalysis,
)

__all__ = [
    # Seed assets
    "SeedAssetType",
    "AssetRole",
    "SeedAsset",
    "SeedAssetRef",
    "SeedAssetCollection",
    # Production request
    "ProductionRequest",
    # Audio models
    "AudioTier",
    "VoiceStyle",
    "MusicMood",
    "SyncPoint",
    "VoiceoverSpec",
    "MusicSpec",
    "SoundEffectSpec",
    "SceneAudio",
    "ProjectAudio",
    "WordTiming",
    "GeneratedAudio",
    "VoiceoverResult",
    "SyncPointResult",
    "TimeStretch",
    "SyncedAudioResult",
    "MixSettings",
    "MixedAudio",
    "AudioQAResult",
    # Edit decision models
    "ExportFormat",
    "EditDecision",
    "EditCandidate",
    "EditDecisionList",
    "HumanFeedback",
    # Render models
    "TrackType",
    "TransitionType",
    "AudioTrack",
    "Transition",
    "RenderConfig",
    "RenderResult",
    "RenderJob",
    # QA visual analysis models
    "FrameAnalysis",
    "QAVisualAnalysis",
]
