"""Seed assets and multi-modal inputs for video production"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class SeedAssetType(Enum):
    """Types of seed assets"""

    # Images
    IMAGE = "image"                      # General reference image
    SKETCH = "sketch"                    # Hand-drawn sketch/doodle
    STORYBOARD = "storyboard"            # Storyboard frame(s)
    MOOD_BOARD = "mood_board"            # Collection of style references
    SCREENSHOT = "screenshot"            # UI/app screenshots
    PHOTO = "photo"                      # Real photographs
    LOGO = "logo"                        # Brand logo

    # Documents
    BRAND_GUIDELINES = "brand_guidelines"  # Brand guide PDF
    SCRIPT = "script"                    # Existing script/screenplay
    NOTES = "notes"                      # Handwritten or typed notes
    OUTLINE = "outline"                  # Story outline

    # Video
    REFERENCE_VIDEO = "reference_video"  # Style reference
    RAW_FOOTAGE = "raw_footage"          # Real footage to incorporate
    EXISTING_AD = "existing_ad"          # Previous ad/video to match

    # Audio
    MUSIC_REFERENCE = "music_reference"  # "Make it sound like this"
    VOICEOVER_SAMPLE = "voiceover_sample"  # Voice to match/clone

    # Other
    COLOR_PALETTE = "color_palette"      # Specific colors to use
    FONT_SAMPLE = "font_sample"          # Typography reference
    CHARACTER_DESIGN = "character_design"  # Character reference sheets


class AssetRole(Enum):
    """How the asset should be used"""

    STYLE_REFERENCE = "style_reference"   # "Make it look like this"
    CONTENT_SOURCE = "content_source"     # "Include this in the video"
    BRAND_GUIDE = "brand_guide"           # "Follow these guidelines"
    STORYBOARD = "storyboard"             # "Follow this sequence"
    TEXTURE = "texture"                   # "Use this texture/pattern"
    CHARACTER = "character"               # "This is what X looks like"
    SETTING = "setting"                   # "This is the environment"
    MOOD = "mood"                         # "This is the feeling/vibe"


@dataclass
class SeedAsset:
    """A single seed asset with metadata"""

    asset_id: str
    asset_type: SeedAssetType
    role: AssetRole
    file_path: str                        # Local path or URL

    # User's description of what this is
    description: str

    # How to use it (user instructions)
    usage_instructions: str

    # Optional metadata
    tags: List[str] = field(default_factory=list)

    # For storyboards/sequences - which part?
    sequence_index: Optional[int] = None

    # For images - extracted description (from vision model)
    extracted_description: Optional[str] = None

    # For brand assets
    brand_info: Optional[Dict[str, Any]] = None


@dataclass
class SeedAssetRef:
    """Reference to a seed asset within a scene"""

    asset_id: str
    usage: str  # "source_frame", "style_reference", "texture", "include_directly"
    timestamp: Optional[float] = None  # When to use it in the scene
    transform: Optional[str] = None    # "animate", "zoom", "pan", "static"


@dataclass
class SeedAssetCollection:
    """Collection of seed assets for a production"""

    assets: List[SeedAsset] = field(default_factory=list)

    # Global instructions for how to use these
    global_instructions: str = ""

    # Extracted themes/patterns (populated by analysis)
    extracted_themes: List[str] = field(default_factory=list)
    extracted_color_palette: List[str] = field(default_factory=list)
    extracted_style_keywords: List[str] = field(default_factory=list)

    def get_by_type(self, asset_type: SeedAssetType) -> List[SeedAsset]:
        """Get all assets of a specific type"""
        return [a for a in self.assets if a.asset_type == asset_type]

    def get_by_role(self, role: AssetRole) -> List[SeedAsset]:
        """Get all assets with a specific role"""
        return [a for a in self.assets if a.role == role]

    def get_storyboard_sequence(self) -> List[SeedAsset]:
        """Get storyboard assets sorted by sequence index"""
        storyboard = self.get_by_type(SeedAssetType.STORYBOARD)
        return sorted(storyboard, key=lambda a: a.sequence_index or 0)

    def get_asset_by_id(self, asset_id: str) -> Optional[SeedAsset]:
        """Get a specific asset by ID"""
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    def add_asset(self, asset: SeedAsset) -> None:
        """Add an asset to the collection"""
        self.assets.append(asset)

    def remove_asset(self, asset_id: str) -> bool:
        """Remove an asset from the collection"""
        for i, asset in enumerate(self.assets):
            if asset.asset_id == asset_id:
                self.assets.pop(i)
                return True
        return False

    @property
    def asset_count(self) -> int:
        """Total number of assets"""
        return len(self.assets)

    @property
    def has_storyboard(self) -> bool:
        """Check if collection includes storyboard assets"""
        return len(self.get_by_type(SeedAssetType.STORYBOARD)) > 0

    @property
    def has_brand_assets(self) -> bool:
        """Check if collection includes brand guidelines"""
        return len(self.get_by_type(SeedAssetType.BRAND_GUIDELINES)) > 0 or \
               len(self.get_by_role(AssetRole.BRAND_GUIDE)) > 0
