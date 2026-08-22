"""Portable metadata manifest — capture once, locally, then travel light.

The problem this solves is that photo metadata does not survive the journey from
a phone to wherever the production runs. Sanitizers strip EXIF in transit, and
they are not going away: removing location before sharing is the correct default
for almost every other use of a photo. Three real frames measured for this
feature arrived with a full GPS block emptied to NaN, from two different phones
and three separate uploads.

The fix is to stop asking the photo. A `cs timeline extract` run on the machine
that holds the originals reads everything while it is still intact and writes a
`TripManifest` — a small JSON file next to the photos. From then on the manifest
is the source of truth, and the images can be copied, shared, re-uploaded and
stripped without losing anything the pipeline needs.

This mirrors what CSP already does for generated work: `ContentLibrary` is a
registry of assets that outlives any single run, and `RunManifest` records the
state of a production. `TripManifest` is the same idea pointed at material the
system did not create and therefore cannot regenerate.

It is also the privacy-preferable arrangement, which is a happy accident rather
than a compromise. The manifest can be redacted at capture time — coarse
coordinates, or none — and the photos themselves never have to leave the machine
for their metadata to be usable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.ingest.content_key import content_key, file_key
from core.ingest.models import LocationSource

MANIFEST_VERSION = 1
DEFAULT_FILENAME = "trip-manifest.json"


@dataclass
class PhotoEntry:
    """Everything worth knowing about one photo, keyed so it can be found again."""

    # Identity — in match-preference order.
    content_hash: str = ""              # survives metadata stripping
    content_method: str = "scan"        # scan | pixel | file
    file_hash: str = ""                 # exact-bytes match, cheapest when it works
    filename: str = ""                  # last-resort match
    width: int = 0
    height: int = 0
    file_size: int = 0

    # Time
    taken_utc: Optional[str] = None     # ISO 8601
    taken_local_naive: Optional[str] = None
    tz_offset_minutes: Optional[int] = None
    tz_source: str = "unknown"

    # Place — omitted entirely when captured with --no-location
    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude_m: Optional[float] = None
    location_precision: Optional[int] = None   # decimal places retained, if reduced
    location_source: Optional[str] = None      # exif | sidecar — where it came from

    # Provenance
    camera: Optional[str] = None
    camera_key: str = "unknown"
    is_screenshot: bool = False


@dataclass
class TripManifest:
    """A registry of photo metadata captured before anything could strip it."""

    version: int = MANIFEST_VERSION
    created_at: str = ""
    source_dir: str = ""
    tool: str = "claude-studio-producer"
    location_policy: str = "full"       # full | coarse:<places> | none
    entries: List[PhotoEntry] = field(default_factory=list)

    # ---------------------------------------------------------------- lookup

    def index(self) -> Dict[str, List[PhotoEntry]]:
        """content_hash -> every entry sharing it.

        A list rather than a single entry because the key is not unique: two
        copies of the same image have identical scan data and therefore an
        identical content key. Collapsing that to one entry would silently give
        both photos the same metadata, which is worse than not matching at all.
        """
        buckets: Dict[str, List[PhotoEntry]] = {}
        for e in self.entries:
            if e.content_hash:
                buckets.setdefault(e.content_hash, []).append(e)
        return buckets

    def match(self, path: Path) -> Optional[PhotoEntry]:
        """Find this photo's entry, tolerating a stripped or renamed copy.

        Tried in order of how much each key proves: exact bytes, then the
        metadata-invariant content key, then filename plus dimensions. The last
        is weak on its own — two frames from a burst can share a size — so it
        requires the pixel dimensions to agree as well.

        Where a key is ambiguous the answer is None, not a guess. Attaching one
        photo's time and place to another is the failure this whole mechanism
        exists to prevent, and an unmatched photo is visible in the report while
        a mismatched one is not.
        """
        by_file = {e.file_hash: e for e in self.entries if e.file_hash}
        exact = by_file.get(file_key(path))
        if exact:
            return exact

        digest, _ = content_key(path)
        bucket = self.index().get(digest, [])
        if len(bucket) == 1:
            return bucket[0]
        if bucket:
            # Duplicate images — the filename is the only thing separating them.
            named = [e for e in bucket if e.filename == path.name]
            return named[0] if len(named) == 1 else None

        candidates = [e for e in self.entries if e.filename == path.name]
        if not candidates:
            return None
        # A basename is not evidence on its own — point a manifest at an
        # unrelated folder holding an IMG_0001.jpg and it would inherit a
        # stranger's time, place and camera. Dimensions must agree too, even
        # when only one entry carries the name.
        try:
            from PIL import Image

            with Image.open(path) as img:
                w, h = img.size
        except Exception:
            return None
        sized = [e for e in candidates if e.width == w and e.height == h]
        return sized[0] if len(sized) == 1 else None

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "source_dir": self.source_dir,
            "tool": self.tool,
            "location_policy": self.location_policy,
            "entries": [asdict(e) for e in self.entries],
        }

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: Path) -> "TripManifest":
        data = json.loads(Path(path).read_text())
        version = data.get("version", 0)
        if version > MANIFEST_VERSION:
            raise ValueError(
                f"{path} was written by a newer version ({version} > "
                f"{MANIFEST_VERSION}). Upgrade rather than guess at its shape."
            )
        return cls(
            version=version,
            created_at=data.get("created_at", ""),
            source_dir=data.get("source_dir", ""),
            tool=data.get("tool", ""),
            location_policy=data.get("location_policy", "full"),
            entries=[PhotoEntry(**e) for e in data.get("entries", [])],
        )


def _round_or_none(value: Optional[float], places: Optional[int]) -> Optional[float]:
    if value is None or places is None:
        return value
    return round(value, places)


def build_manifest(
    photos,
    *,
    source_dir: Path,
    location: str = "full",
    coarse_places: int = 2,
) -> TripManifest:
    """Capture `photos` (already loaded from intact originals) into a manifest.

    `location` is "full", "coarse" (rounded to `coarse_places` decimals — about
    1 km at 2 places), or "none". Redaction happens here, at capture, so a
    redacted manifest never contains the precise value at all rather than
    carrying it and hoping every reader honors a flag.
    """
    policy = location if location != "coarse" else f"coarse:{coarse_places}"
    places = coarse_places if location == "coarse" else None

    entries: List[PhotoEntry] = []
    for p in photos:
        digest, method = content_key(p.path)
        keep_location = location != "none"
        # Take whatever position the photo actually resolved to, not just EXIF.
        # A Takeout photo's coordinates arrive via the sidecar's geoData and
        # never touch the EXIF fields, and that is the most common input of all
        # — capturing only EXIF would write a manifest with no location for it
        # while claiming to be the portable source of truth.
        if p.exif_lat is not None and p.exif_lon is not None:
            src_lat, src_lon, src_name = p.exif_lat, p.exif_lon, "exif"
        elif p.location_source in (LocationSource.SIDECAR, LocationSource.EXIF):
            src_lat, src_lon, src_name = p.lat, p.lon, p.location_source.value
        else:
            src_lat, src_lon, src_name = None, None, None
        entries.append(
            PhotoEntry(
                content_hash=digest,
                content_method=method,
                file_hash=file_key(p.path),
                filename=p.path.name,
                width=p.width,
                height=p.height,
                file_size=p.path.stat().st_size,
                taken_utc=p.taken_utc.isoformat() if p.taken_utc else None,
                taken_local_naive=(
                    p.taken_local_naive.isoformat() if p.taken_local_naive else None
                ),
                tz_offset_minutes=p.tz_offset_minutes,
                tz_source=p.tz_offset_source.value,
                lat=_round_or_none(src_lat, places) if keep_location else None,
                lon=_round_or_none(src_lon, places) if keep_location else None,
                location_precision=places if keep_location and src_lat is not None else None,
                location_source=src_name if keep_location else None,
                camera=p.camera,
                camera_key=p.camera_key,
                is_screenshot=p.is_screenshot,
            )
        )
    return TripManifest(
        created_at=datetime.now(timezone.utc).isoformat(),
        source_dir=str(source_dir),
        location_policy=policy,
        entries=entries,
    )
