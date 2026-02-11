"""
Content Library model - persistent registry of all approved assets.

Enables asset reuse across runs, approval tracking, and generation planning.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class AssetType(str, Enum):
    """Types of assets in the library."""
    AUDIO = "audio"
    IMAGE = "image"
    FIGURE = "figure"           # KB-extracted, not generated
    VIDEO = "video"


class AssetStatus(str, Enum):
    """Approval status of an asset."""
    DRAFT = "draft"             # Just generated, not reviewed
    REVIEW = "review"           # Flagged for human review
    APPROVED = "approved"       # Good to use
    REJECTED = "rejected"       # Not usable (with reason)
    REVISED = "revised"         # Regenerated after rejection


class AssetSource(str, Enum):
    """How the asset was created."""
    DALLE = "dalle"
    ELEVENLABS = "elevenlabs"
    OPENAI_TTS = "openai_tts"
    GOOGLE_TTS = "google_tts"
    LUMA = "luma"
    RUNWAY = "runway"
    KB_EXTRACTION = "kb_extraction"
    WEB = "web"                 # Sourced from web (Wikimedia Commons, etc.)
    FFMPEG = "ffmpeg"           # Processed/composited
    MANUAL = "manual"           # User-provided


@dataclass
class AssetRecord:
    """A registered asset in the content library."""
    asset_id: str                               # e.g., "aud_001", "img_fig6_v2"
    asset_type: AssetType
    source: AssetSource
    status: AssetStatus = AssetStatus.DRAFT

    # File info
    path: str = ""                              # Relative to content_library/
    file_size_bytes: int = 0
    format: str = ""                            # "mp3", "png", "mp4"

    # Content description
    describes: str = ""                         # What this asset shows/says
    tags: List[str] = field(default_factory=list)

    # For audio
    text_content: Optional[str] = None          # The narration text
    voice: Optional[str] = None                 # Voice name/ID
    duration_sec: Optional[float] = None

    # For images/figures
    prompt: Optional[str] = None                # DALL-E prompt used
    figure_number: Optional[int] = None         # If KB figure
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    # Segment associations
    segment_idx: Optional[int] = None           # Primary segment this is for
    used_in_segments: List[int] = field(default_factory=list)
    script_id: Optional[str] = None

    # Provenance
    origin_run_id: Optional[str] = None
    generated_at: Optional[str] = None
    generated_by: Optional[str] = None          # Agent that created it
    generation_cost: float = 0.0

    # Review
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    rejected_reason: Optional[str] = None
    revision_of: Optional[str] = None           # asset_id this revises
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "source": self.source.value,
            "status": self.status.value,
            "path": self.path,
            "file_size_bytes": self.file_size_bytes,
            "format": self.format,
            "describes": self.describes,
            "tags": self.tags,
            "text_content": self.text_content,
            "voice": self.voice,
            "duration_sec": self.duration_sec,
            "prompt": self.prompt,
            "figure_number": self.figure_number,
            "caption": self.caption,
            "width": self.width,
            "height": self.height,
            "segment_idx": self.segment_idx,
            "used_in_segments": self.used_in_segments,
            "script_id": self.script_id,
            "origin_run_id": self.origin_run_id,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "generation_cost": self.generation_cost,
            "approved_at": self.approved_at,
            "approved_by": self.approved_by,
            "rejected_reason": self.rejected_reason,
            "revision_of": self.revision_of,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AssetRecord":
        """Deserialize from dictionary."""
        return cls(
            asset_id=data["asset_id"],
            asset_type=AssetType(data["asset_type"]),
            source=AssetSource(data["source"]),
            status=AssetStatus(data.get("status", "draft")),
            path=data.get("path", ""),
            file_size_bytes=data.get("file_size_bytes", 0),
            format=data.get("format", ""),
            describes=data.get("describes", ""),
            tags=data.get("tags", []),
            text_content=data.get("text_content"),
            voice=data.get("voice"),
            duration_sec=data.get("duration_sec"),
            prompt=data.get("prompt"),
            figure_number=data.get("figure_number"),
            caption=data.get("caption"),
            width=data.get("width"),
            height=data.get("height"),
            segment_idx=data.get("segment_idx"),
            used_in_segments=data.get("used_in_segments", []),
            script_id=data.get("script_id"),
            origin_run_id=data.get("origin_run_id"),
            generated_at=data.get("generated_at"),
            generated_by=data.get("generated_by"),
            generation_cost=data.get("generation_cost", 0.0),
            approved_at=data.get("approved_at"),
            approved_by=data.get("approved_by"),
            rejected_reason=data.get("rejected_reason"),
            revision_of=data.get("revision_of"),
            notes=data.get("notes", ""),
        )


@dataclass
class ContentLibrary:
    """The master content library for a project."""
    project_id: str
    assets: Dict[str, AssetRecord] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    # Counters for ID generation
    _audio_counter: int = 0
    _image_counter: int = 0
    _figure_counter: int = 0
    _video_counter: int = 0

    def _next_id(self, asset_type: AssetType) -> str:
        """Generate next asset ID for a given type."""
        if asset_type == AssetType.AUDIO:
            self._audio_counter += 1
            return f"aud_{self._audio_counter:04d}"
        elif asset_type == AssetType.IMAGE:
            self._image_counter += 1
            return f"img_{self._image_counter:04d}"
        elif asset_type == AssetType.FIGURE:
            self._figure_counter += 1
            return f"fig_{self._figure_counter:04d}"
        elif asset_type == AssetType.VIDEO:
            self._video_counter += 1
            return f"vid_{self._video_counter:04d}"
        else:
            return f"asset_{len(self.assets):04d}"

    def register(self, record: AssetRecord) -> str:
        """
        Register a new asset.

        If asset_id is empty, generates one.
        Returns the asset_id.
        """
        if not record.asset_id:
            record.asset_id = self._next_id(record.asset_type)

        if not record.generated_at:
            record.generated_at = datetime.now().isoformat()

        self.assets[record.asset_id] = record
        self.updated_at = datetime.now().isoformat()
        return record.asset_id

    def get(self, asset_id: str) -> Optional[AssetRecord]:
        """Get asset by ID."""
        return self.assets.get(asset_id)

    def query(
        self,
        asset_type: Optional[AssetType] = None,
        status: Optional[AssetStatus] = None,
        segment_idx: Optional[int] = None,
        figure_number: Optional[int] = None,
        tags: Optional[List[str]] = None,
        source: Optional[AssetSource] = None,
    ) -> List[AssetRecord]:
        """Query assets by criteria."""
        results = list(self.assets.values())

        if asset_type is not None:
            results = [a for a in results if a.asset_type == asset_type]

        if status is not None:
            results = [a for a in results if a.status == status]

        if segment_idx is not None:
            results = [a for a in results
                       if a.segment_idx == segment_idx
                       or segment_idx in a.used_in_segments]

        if figure_number is not None:
            results = [a for a in results if a.figure_number == figure_number]

        if tags:
            results = [a for a in results
                       if any(t in a.tags for t in tags)]

        if source is not None:
            results = [a for a in results if a.source == source]

        return results

    def approve(self, asset_id: str, approved_by: str = "user") -> bool:
        """
        Mark an asset as approved.

        Returns True if found and updated.
        """
        asset = self.get(asset_id)
        if asset:
            asset.status = AssetStatus.APPROVED
            asset.approved_at = datetime.now().isoformat()
            asset.approved_by = approved_by
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def reject(self, asset_id: str, reason: str) -> bool:
        """
        Mark an asset as rejected with a reason.

        Returns True if found and updated.
        """
        asset = self.get(asset_id)
        if asset:
            asset.status = AssetStatus.REJECTED
            asset.rejected_reason = reason
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def flag_for_review(self, asset_id: str) -> bool:
        """
        Flag an asset for human review.

        Returns True if found and updated.
        """
        asset = self.get(asset_id)
        if asset:
            asset.status = AssetStatus.REVIEW
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def has_approved_asset_for(
        self,
        segment_idx: int,
        asset_type: AssetType,
    ) -> bool:
        """Check if we already have an approved asset for a segment."""
        matching = self.query(
            asset_type=asset_type,
            status=AssetStatus.APPROVED,
            segment_idx=segment_idx,
        )
        return len(matching) > 0

    def get_approved_for_segment(
        self,
        segment_idx: int,
        asset_type: AssetType,
    ) -> Optional[AssetRecord]:
        """Get the approved asset for a segment, if one exists."""
        matching = self.query(
            asset_type=asset_type,
            status=AssetStatus.APPROVED,
            segment_idx=segment_idx,
        )
        return matching[0] if matching else None

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "project_id": self.project_id,
            "assets": {k: v.to_dict() for k, v in self.assets.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "_audio_counter": self._audio_counter,
            "_image_counter": self._image_counter,
            "_figure_counter": self._figure_counter,
            "_video_counter": self._video_counter,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def get_summary(self) -> dict:
        """Get a summary of assets by type and status."""
        by_type = {}
        by_status = {}

        for asset in self.assets.values():
            type_name = asset.asset_type.value
            status_name = asset.status.value

            by_type[type_name] = by_type.get(type_name, 0) + 1
            by_status[status_name] = by_status.get(status_name, 0) + 1

        return {
            "total": len(self.assets),
            "by_type": by_type,
            "by_status": by_status,
            "project_id": self.project_id,
        }

    def save(self, path: Optional[Path] = None) -> Path:
        """
        Save to JSON file.

        Default path: artifacts/content_library/library.json
        """
        if path is None:
            path = Path("artifacts/content_library/library.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())
        return path

    @classmethod
    def from_dict(cls, data: dict) -> "ContentLibrary":
        """Deserialize from dictionary."""
        lib = cls(
            project_id=data["project_id"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        lib._audio_counter = data.get("_audio_counter", 0)
        lib._image_counter = data.get("_image_counter", 0)
        lib._figure_counter = data.get("_figure_counter", 0)
        lib._video_counter = data.get("_video_counter", 0)

        for asset_id, asset_data in data.get("assets", {}).items():
            lib.assets[asset_id] = AssetRecord.from_dict(asset_data)

        return lib

    @classmethod
    def from_json(cls, json_str: str) -> "ContentLibrary":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ContentLibrary":
        """
        Load from JSON file.

        Default path: artifacts/content_library/library.json
        If file doesn't exist, returns empty library.
        """
        if path is None:
            path = Path("artifacts/content_library/library.json")

        if not path.exists():
            return cls(
                project_id="default",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

        return cls.from_json(path.read_text())

    @classmethod
    def from_asset_manifest_v1(
        cls,
        manifest_path: str,
        project_id: Optional[str] = None,
    ) -> "ContentLibrary":
        """
        Migrate from existing asset_manifest.json (v1 format).

        This is the backwards-compatible upgrade path for existing runs.

        V1 format:
        {
            "run_id": "...",
            "mode": "live",
            "total_scenes": N,
            "assets": [
                {
                    "scene_id": "scene_000",
                    "image_path": "...",
                    "video_path": null,
                    "audio_path": null,
                    "display_start": 0.0,
                    "display_end": 0.0
                },
                ...
            ]
        }
        """
        manifest_file = Path(manifest_path)
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        data = json.loads(manifest_file.read_text())
        run_id = data.get("run_id", manifest_file.parent.name)

        lib = cls(
            project_id=project_id or run_id,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        for asset in data.get("assets", []):
            scene_id = asset.get("scene_id", "unknown")

            # Extract scene index from scene_id (e.g., "scene_000" -> 0)
            segment_idx = None
            if scene_id.startswith("scene_"):
                try:
                    segment_idx = int(scene_id.split("_")[1])
                except (ValueError, IndexError):
                    pass

            # Register image if present
            image_path = asset.get("image_path")
            if image_path and Path(image_path).exists():
                lib.register(AssetRecord(
                    asset_id="",  # Will be generated
                    asset_type=AssetType.IMAGE,
                    source=AssetSource.DALLE,  # Assume DALL-E for v1
                    status=AssetStatus.DRAFT,
                    path=image_path,
                    format="png",
                    segment_idx=segment_idx,
                    origin_run_id=run_id,
                    notes=f"Migrated from v1 manifest: {scene_id}",
                ))

            # Register video if present
            video_path = asset.get("video_path")
            if video_path and Path(video_path).exists():
                lib.register(AssetRecord(
                    asset_id="",
                    asset_type=AssetType.VIDEO,
                    source=AssetSource.LUMA,  # Assume Luma for v1
                    status=AssetStatus.DRAFT,
                    path=video_path,
                    format="mp4",
                    segment_idx=segment_idx,
                    origin_run_id=run_id,
                    notes=f"Migrated from v1 manifest: {scene_id}",
                ))

            # Register audio if present
            audio_path = asset.get("audio_path")
            if audio_path and Path(audio_path).exists():
                lib.register(AssetRecord(
                    asset_id="",
                    asset_type=AssetType.AUDIO,
                    source=AssetSource.ELEVENLABS,  # Assume ElevenLabs for v1
                    status=AssetStatus.DRAFT,
                    path=audio_path,
                    format="mp3",
                    segment_idx=segment_idx,
                    origin_run_id=run_id,
                    notes=f"Migrated from v1 manifest: {scene_id}",
                ))

        return lib

    def summary(self) -> dict:
        """Get a summary of library contents."""
        by_type = {}
        by_status = {}

        for asset in self.assets.values():
            # Count by type
            type_key = asset.asset_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

            # Count by status
            status_key = asset.status.value
            by_status[status_key] = by_status.get(status_key, 0) + 1

        return {
            "project_id": self.project_id,
            "total_assets": len(self.assets),
            "by_type": by_type,
            "by_status": by_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
