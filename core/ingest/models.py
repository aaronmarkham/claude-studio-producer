"""Shared data model for personal-media ingestion.

This is the contract between the three ingestion modules: `timeline.py` produces
`Timeline`, `photos.py` produces `Photo`, and `trip_join.py` consumes both to
produce `TripKnowledge`. Nothing here parses, joins, or renders — keeping the
shapes in one module is what lets those three be written independently.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class TrackConfidence(str, Enum):
    """How much to trust a position at a given instant."""
    VISIT = "visit"                 # inside a placeVisit — highest
    INTERPOLATED = "interpolated"   # between track points, gap under threshold
    INFERRED = "inferred"           # gap exceeds threshold, extrapolated
    UNKNOWN = "unknown"             # outside the track entirely


class TzSource(str, Enum):
    """Where a photo's UTC timestamp came from. Drives the join's trust model."""
    SIDECAR = "sidecar"             # Takeout epoch seconds — unambiguous
    EXIF_OFFSET = "exif_offset"     # OffsetTimeOriginal was present
    INFERRED = "inferred"           # recovered by cross-correlating GPS photos
    ASSUMED = "assumed"             # fell back to the trip's dominant zone
    UNKNOWN = "unknown"


class LocationSource(str, Enum):
    """Where a photo's coordinates came from."""
    EXIF = "exif"                   # the photo measured it itself
    SIDECAR = "sidecar"             # Google's geoData block
    TIMELINE = "timeline"           # supplied by the join
    NONE = "none"


@dataclass
class TrackPoint:
    """A single normalized position fix. Always tz-aware UTC."""
    ts: datetime
    lat: float
    lon: float
    accuracy_m: Optional[int] = None
    source: str = "record"          # record | visit | activity


@dataclass
class Place:
    """A named location the timeline says the user stopped at."""
    place_id: str                   # stable hash of rounded coords + name
    name: Optional[str] = None      # Google's placeVisit name when present
    lat: float = 0.0
    lon: float = 0.0
    address: Optional[str] = None


@dataclass
class TimelineSegment:
    """A visit or a movement, in chronological order."""
    seg_id: str
    kind: str                       # "visit" | "move"
    start: datetime
    end: datetime
    place: Optional[Place] = None           # set when kind == "visit"
    from_place: Optional[Place] = None      # set when kind == "move"
    to_place: Optional[Place] = None
    activity: Optional[str] = None          # "flying", "in_passenger_vehicle", "walking"
    distance_m: Optional[float] = None
    path: List[TrackPoint] = field(default_factory=list)


@dataclass
class FilterStats:
    """What parsing threw away. A track that loses most of its points is a bug
    report, not a clean track, so these counts are surfaced to the user."""
    points_in: int = 0
    points_out: int = 0
    dropped_accuracy: int = 0
    dropped_speed: int = 0
    collapsed_stationary: int = 0
    unparseable: int = 0


@dataclass
class Timeline:
    """A parsed, normalized, chronologically sorted location history."""
    segments: List[TimelineSegment] = field(default_factory=list)
    track: List[TrackPoint] = field(default_factory=list)   # sorted — the join index
    tz_hint: Optional[str] = None   # IANA zone inferred from the dominant location
    source_format: str = "unknown"  # records | semantic | wrapped | bare | photos_only
    stats: FilterStats = field(default_factory=FilterStats)

    @property
    def start(self) -> Optional[datetime]:
        return self.track[0].ts if self.track else None

    @property
    def end(self) -> Optional[datetime]:
        return self.track[-1].ts if self.track else None


@dataclass
class Photo:
    """One photograph with everything known about when and where it was taken."""
    photo_id: str                   # content hash, stable across re-imports
    path: Path
    # Time
    taken_utc: Optional[datetime] = None
    taken_local_naive: Optional[datetime] = None   # raw EXIF wall-clock, for debugging
    tz_offset_source: TzSource = TzSource.UNKNOWN
    tz_offset_minutes: Optional[int] = None
    # Space — may be filled by the join rather than by the file
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_source: LocationSource = LocationSource.NONE
    confidence: TrackConfidence = TrackConfidence.UNKNOWN
    place_name: Optional[str] = None
    # Provenance
    camera: Optional[str] = None            # "Apple iPhone 14 Pro"
    camera_key: str = "unknown"             # Make/Model/Serial fingerprint
    credit: Optional[str] = None            # photographer, resolved from camera_key
    exif_lat: Optional[float] = None        # the photo's own measurement, kept
    exif_lon: Optional[float] = None        # separately so the join can validate
    width: int = 0
    height: int = 0
    is_screenshot: bool = False
    sidecar_path: Optional[Path] = None

    @property
    def has_own_position(self) -> bool:
        """True when the photo measured its own location — the join's validator."""
        return self.exif_lat is not None and self.exif_lon is not None


@dataclass
class JoinReport:
    """The primary debugging artifact. `cs timeline inspect` renders this."""
    photos_total: int = 0
    photos_dated: int = 0
    photos_located: int = 0
    by_confidence: Dict[str, int] = field(default_factory=dict)
    by_location_source: Dict[str, int] = field(default_factory=dict)
    by_tz_source: Dict[str, int] = field(default_factory=dict)
    cameras: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tz_offsets_applied: Dict[str, str] = field(default_factory=dict)
    gps_disagreements: List[Tuple[str, float]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TripBeat:
    """A story unit: a place worth talking about, or a movement worth showing."""
    beat_id: str
    kind: str                       # "stay" | "move"
    start: datetime
    end: datetime
    place: Optional[Place] = None
    from_place: Optional[Place] = None
    to_place: Optional[Place] = None
    photos: List[Photo] = field(default_factory=list)
    distance_m: Optional[float] = None
    activity: Optional[str] = None
    day_index: int = 1              # 1-based day of trip
    salience: float = 0.0           # 0..1 — drives importance_score downstream

    @property
    def duration_sec(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass
class TripKnowledge:
    """The ingestion output. Analogue of a KB, for personal media."""
    trip_id: str
    title: str = ""                 # "Portugal, May 2023" — derived, user-overridable
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    beats: List[TripBeat] = field(default_factory=list)
    places: List[Place] = field(default_factory=list)
    photos: List[Photo] = field(default_factory=list)
    total_distance_m: float = 0.0
    credits: Dict[str, str] = field(default_factory=dict)   # camera_key -> name
    report: JoinReport = field(default_factory=JoinReport)

    @property
    def day_count(self) -> int:
        if not self.start or not self.end:
            return 0
        return (self.end.date() - self.start.date()).days + 1
