"""Production request with concept and seed assets"""

from dataclasses import dataclass, field
from typing import Dict, Any
from .seed_assets import SeedAssetCollection


@dataclass
class ProductionRequest:
    """Complete production request with concept and seed assets"""

    # The main concept/prompt
    concept: str

    # Budget
    total_budget: float

    # Target duration
    target_duration: int = 60

    # Seed assets
    seed_assets: SeedAssetCollection = field(default_factory=SeedAssetCollection)

    # Style preferences (can be derived from seeds)
    style_preferences: Dict[str, Any] = field(default_factory=dict)

    # Audio preferences
    audio_tier: str = "time_synced"
    voice_style: str = "professional"
    music_mood: str = "corporate"

    # Output preferences
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"

    # Optional metadata
    project_name: str = ""
    client_name: str = ""
    deadline: str = ""
    notes: str = ""

    @property
    def has_seed_assets(self) -> bool:
        """Check if request includes seed assets"""
        return self.seed_assets.asset_count > 0

    @property
    def budget_per_second(self) -> float:
        """Calculate budget per second of video"""
        return self.total_budget / self.target_duration if self.target_duration > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "concept": self.concept,
            "total_budget": self.total_budget,
            "target_duration": self.target_duration,
            "seed_assets": {
                "assets": [
                    {
                        "asset_id": asset.asset_id,
                        "asset_type": asset.asset_type.value,
                        "role": asset.role.value,
                        "file_path": asset.file_path,
                        "description": asset.description,
                        "usage_instructions": asset.usage_instructions,
                        "tags": asset.tags,
                        "sequence_index": asset.sequence_index,
                        "extracted_description": asset.extracted_description,
                        "brand_info": asset.brand_info,
                    }
                    for asset in self.seed_assets.assets
                ],
                "global_instructions": self.seed_assets.global_instructions,
                "extracted_themes": self.seed_assets.extracted_themes,
                "extracted_color_palette": self.seed_assets.extracted_color_palette,
                "extracted_style_keywords": self.seed_assets.extracted_style_keywords,
            },
            "style_preferences": self.style_preferences,
            "audio_tier": self.audio_tier,
            "voice_style": self.voice_style,
            "music_mood": self.music_mood,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "project_name": self.project_name,
            "client_name": self.client_name,
            "deadline": self.deadline,
            "notes": self.notes,
        }
