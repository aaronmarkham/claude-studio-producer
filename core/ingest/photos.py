"""Photo ingestion from folders assembled from Google Takeout, AirDrop, and shared drives.

Builds one `Photo` per image file found under a directory, filling in timestamp and
GPS from whichever of two sources is available, in priority order:

1. A Google Takeout JSON sidecar (`photoTakenTime.timestamp`, `geoData`) — unambiguous
   UTC, no timezone guessing, survives EXIF stripping. Sidecar *naming* is a genuine
   minefield (see `resolve_sidecar`), so it needs a real resolver rather than
   `f"{name}.json"`.
2. EXIF, via Pillow. `DateTimeOriginal` is local wall-clock with **no** zone unless
   `OffsetTimeOriginal` is present — it is never assumed to be UTC. Resolving the rest
   (inferring or assuming a zone) is Component 3's job (`trip_join.py`), not this
   module's.

Also handles camera-based attribution: since Google Photos will not tell us who took a
shot in a shared/collaborative album, we fingerprint the device from EXIF `Make` /
`Model` / `BodySerialNumber` (`camera_key`) and let the user name each cluster once via
a `credits` mapping. A camera absent from that mapping stays uncredited — never guess a
name.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md, "Component 2: Photo Ingestion".
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from PIL.ExifTags import Base

from core.ingest.models import LocationSource, Photo, TzSource

# EXIF sub-IFD tag numbers (Pillow exposes these via Exif.get_ifd()).
_EXIF_SUB_IFD = 0x8769   # holds DateTimeOriginal / OffsetTimeOriginal
_GPS_IFD = 0x8825
_TAG_DATE_TIME_ORIGINAL = 36867
_TAG_OFFSET_TIME_ORIGINAL = 36881
_TAG_GPS_LAT_REF = 1
_TAG_GPS_LAT = 2
_TAG_GPS_LON_REF = 3
_TAG_GPS_LON = 4

_IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tif", ".tiff", ".webp", ".bmp", ".gif",
}

# Short-side/long-side ratios of common phone and desktop displays. A screenshot has
# no camera EXIF *and* one of these proportions. 1:1 is deliberately excluded — plenty
# of ordinary photos (and most of our tiny test fixtures) are square, and a false
# positive there would silently drop real photos.
_SCREENSHOT_ASPECTS = (9 / 16, 9 / 18, 9 / 18.5, 9 / 19.5, 9 / 20, 3 / 4)
_ASPECT_TOLERANCE = 0.02


# --------------------------------------------------------------------------- #
# Sidecar resolution
# --------------------------------------------------------------------------- #

def resolve_sidecar(photo_path: Path) -> Optional[Path]:
    """Locate a Takeout JSON sidecar for a photo, handling Google's naming quirks.

    Tried in order:

    1. Exact `<name>.json` (older exports).
    2. `<name>.supplemental-metadata.json` (newer exports).
    3. A case-insensitive match of either — Takeout occasionally emits the sidecar
       with different extension casing than the photo on disk (`IMG_4471.HEIC.json`
       next to `img_4471.heic`).
    4. A truncated match: Takeout shortens the combined `<name>.json` when it would
       exceed the filesystem's name-length limit, so the sidecar's basename (minus
       `.json`) becomes a *prefix* of the photo's filename that still contains the
       full stem (e.g. `IMG_4471.jp.json` for `IMG_4471.jpg`).

    Returns `None` when nothing matches — a folder with a genuinely missing sidecar
    (or none at all) falls through to EXIF.
    """
    directory = photo_path.parent
    if not directory.is_dir():
        return None

    name = photo_path.name
    stem = photo_path.stem
    name_lower = name.lower()
    stem_lower = stem.lower()

    exact = directory / f"{name}.json"
    if exact.exists():
        return exact

    supplemental = directory / f"{name}.supplemental-metadata.json"
    if supplemental.exists():
        return supplemental

    try:
        json_siblings = [p for p in directory.iterdir() if p.suffix.lower() == ".json"]
    except OSError:
        return None

    # Case-insensitive exact / supplemental match.
    for candidate in json_siblings:
        cand_lower = candidate.name.lower()
        if cand_lower == f"{name_lower}.json":
            return candidate
        if cand_lower == f"{name_lower}.supplemental-metadata.json":
            return candidate

    # Truncated match: the sidecar's basename is a prefix of the photo's name that
    # still contains the whole stem (only the extension/`.json` tail was chopped).
    best: Optional[Path] = None
    best_len = -1
    for candidate in json_siblings:
        base = candidate.name[:-len(".json")]
        base_lower = base.lower()
        if not base_lower.startswith(stem_lower):
            continue
        if not name_lower.startswith(base_lower):
            continue
        if len(base) >= len(name):
            continue  # not actually truncated — would have matched exactly above
        if len(base) > best_len:
            best, best_len = candidate, len(base)

    return best


def _parse_sidecar(sidecar_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _sidecar_utc(data: Dict[str, Any]) -> Optional[datetime]:
    ts = (data.get("photoTakenTime") or {}).get("timestamp")
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _sidecar_geo(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """geoData is present even when Google never had a fix, in which case it's
    exactly 0.0/0.0 — a real position in the Atlantic, and one we must not report."""
    geo = data.get("geoData") or {}
    lat, lon = geo.get("latitude"), geo.get("longitude")
    if lat is None or lon is None:
        return None, None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None
    if not _valid_position(lat, lon):
        return None, None
    return lat, lon


# --------------------------------------------------------------------------- #
# EXIF extraction
# --------------------------------------------------------------------------- #

def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().strip("\x00").strip()
    return text or None


def _parse_local_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _parse_offset_minutes(value: Optional[str]) -> Optional[int]:
    """OffsetTimeOriginal, e.g. '+02:00' or '-05:00', to signed minutes east of UTC."""
    if not value:
        return None
    text = value.strip()
    sign = 1
    if text and text[0] in "+-":
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return sign * (hours * 60 + minutes)


def _dms_to_decimal(dms: Any, ref: Optional[str]) -> Optional[float]:
    if not dms or len(dms) != 3:
        return None
    try:
        degrees, minutes, seconds = (float(x) for x in dms)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    value = degrees + minutes / 60.0 + seconds / 3600.0
    if not math.isfinite(value):
        return None
    if ref in ("S", "W"):
        value = -value
    return value


def _valid_position(lat: Optional[float], lon: Optional[float]) -> bool:
    """Whether a coordinate pair is a real measurement rather than a placeholder.

    Photos that have passed through a sharing or upload pipeline routinely keep a
    GPS block whose values have been blanked rather than removed: NaN rationals
    (a 0/0 numerator, which is how EXIF spells "no value"), empty hemisphere refs,
    or an exact 0/0 that would put the shot in the Gulf of Guinea. All three must
    read as "this photo does not know where it was" — otherwise the join sees a
    position already present, declines to supply one, and the photo ends up with
    a location of NaN and no way to recover.
    """
    if lat is None or lon is None:
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _gps_from_ifd(gps_ifd: Dict[int, Any]) -> Tuple[Optional[float], Optional[float]]:
    lat = _dms_to_decimal(gps_ifd.get(_TAG_GPS_LAT), gps_ifd.get(_TAG_GPS_LAT_REF))
    lon = _dms_to_decimal(gps_ifd.get(_TAG_GPS_LON), gps_ifd.get(_TAG_GPS_LON_REF))
    if not _valid_position(lat, lon):
        return None, None
    return lat, lon


def _read_image_metadata(path: Path) -> Dict[str, Any]:
    """Pull the handful of EXIF fields we need, plus pixel dimensions.

    Never raises: an undecodable file (e.g. HEIC without a plugin, or a corrupt
    image) just yields an empty metadata dict, so the photo still gets built from
    whatever the sidecar knows.
    """
    meta: Dict[str, Any] = {
        "width": 0, "height": 0,
        "make": None, "model": None, "serial": None,
        "date_time_original": None, "offset_time_original": None,
        "gps_lat": None, "gps_lon": None,
    }
    try:
        with Image.open(path) as img:
            meta["width"], meta["height"] = img.size
            exif = img.getexif()
            if exif:
                meta["make"] = _clean_str(exif.get(Base.Make))
                meta["model"] = _clean_str(exif.get(Base.Model))
                meta["serial"] = _clean_str(exif.get(Base.BodySerialNumber))
                sub_ifd = exif.get_ifd(_EXIF_SUB_IFD) or {}
                meta["date_time_original"] = sub_ifd.get(_TAG_DATE_TIME_ORIGINAL)
                meta["offset_time_original"] = sub_ifd.get(_TAG_OFFSET_TIME_ORIGINAL)
                gps_ifd = exif.get_ifd(_GPS_IFD) or {}
                if gps_ifd:
                    meta["gps_lat"], meta["gps_lon"] = _gps_from_ifd(gps_ifd)
    except Exception:
        pass
    return meta


# --------------------------------------------------------------------------- #
# Attribution
# --------------------------------------------------------------------------- #

def camera_key(exif: Dict[str, Optional[str]]) -> str:
    """Stable per-device fingerprint. Falls back gracefully as tags go missing.

    `exif` is a plain dict with (a subset of) "Make", "Model", "BodySerialNumber" —
    the shape produced by `_read_image_metadata`, adapted for the public signature
    the spec calls for.
    """
    parts = [exif.get("Make"), exif.get("Model"), exif.get("BodySerialNumber")]
    cleaned = [p.strip() for p in parts if p and p.strip()]
    return "/".join(cleaned) if cleaned else "unknown"


def cluster_by_camera(photos: List[Photo]) -> Dict[str, List[Photo]]:
    """Partition a mixed folder into the cameras that shot it, keyed by `camera_key`."""
    clusters: Dict[str, List[Photo]] = {}
    for photo in photos:
        clusters.setdefault(photo.camera_key, []).append(photo)
    return clusters


# --------------------------------------------------------------------------- #
# Screenshot heuristic
# --------------------------------------------------------------------------- #

def _is_screenshot(make: Optional[str], model: Optional[str], width: int, height: int) -> bool:
    if make or model:
        return False  # a real camera shot this
    if width <= 0 or height <= 0:
        return False
    short_side, long_side = sorted((width, height))
    ratio = short_side / long_side
    return any(abs(ratio - target) <= _ASPECT_TOLERANCE for target in _SCREENSHOT_ASPECTS)


# --------------------------------------------------------------------------- #
# Content hash
# --------------------------------------------------------------------------- #

def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Top-level ingestion
# --------------------------------------------------------------------------- #

def _build_photo(path: Path, credits: Dict[str, str]) -> Optional[Photo]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    meta = _read_image_metadata(path)
    make, model, serial = meta["make"], meta["model"], meta["serial"]
    width, height = meta["width"], meta["height"]

    camera = " ".join(p for p in (make, model) if p) or None
    key = camera_key({"Make": make, "Model": model, "BodySerialNumber": serial})

    exif_lat, exif_lon = meta["gps_lat"], meta["gps_lon"]
    taken_local_naive = _parse_local_datetime(meta["date_time_original"])

    taken_utc: Optional[datetime] = None
    tz_offset_source = TzSource.UNKNOWN
    tz_offset_minutes: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_source = LocationSource.NONE

    sidecar_path = resolve_sidecar(path)
    if sidecar_path is not None:
        data = _parse_sidecar(sidecar_path)
        if data is not None:
            sidecar_utc = _sidecar_utc(data)
            if sidecar_utc is not None:
                taken_utc = sidecar_utc
                tz_offset_source = TzSource.SIDECAR
            sidecar_lat, sidecar_lon = _sidecar_geo(data)
            if sidecar_lat is not None and sidecar_lon is not None:
                lat, lon = sidecar_lat, sidecar_lon
                location_source = LocationSource.SIDECAR

    # EXIF offset only fills in what the sidecar didn't already resolve — the
    # sidecar's UTC timestamp is unambiguous and always wins.
    if taken_utc is None and taken_local_naive is not None:
        offset_minutes = _parse_offset_minutes(meta["offset_time_original"])
        if offset_minutes is not None:
            utc_naive = taken_local_naive - timedelta(minutes=offset_minutes)
            taken_utc = utc_naive.replace(tzinfo=timezone.utc)
            tz_offset_source = TzSource.EXIF_OFFSET
            tz_offset_minutes = offset_minutes

    if lat is None and exif_lat is not None and exif_lon is not None:
        lat, lon = exif_lat, exif_lon
        location_source = LocationSource.EXIF

    is_screenshot = _is_screenshot(make, model, width, height)
    credit = credits.get(key)

    return Photo(
        photo_id=_content_hash(raw),
        path=path,
        taken_utc=taken_utc,
        taken_local_naive=taken_local_naive,
        tz_offset_source=tz_offset_source,
        tz_offset_minutes=tz_offset_minutes,
        lat=lat,
        lon=lon,
        location_source=location_source,
        camera=camera,
        camera_key=key,
        credit=credit,
        exif_lat=exif_lat,
        exif_lon=exif_lon,
        width=width,
        height=height,
        is_screenshot=is_screenshot,
        sidecar_path=sidecar_path,
    )


def _apply_manifest(photo: Photo, entry) -> Photo:
    """Overlay manifest values onto a photo. Highest precedence of all sources.

    The manifest was captured from the intact original, so where it and the file
    disagree the file is the degraded copy and loses. Fields absent from the
    manifest leave whatever the file knew — a manifest is allowed to be partial,
    and a redacted one deliberately is.
    """
    if entry.taken_utc:
        photo.taken_utc = datetime.fromisoformat(entry.taken_utc)
        photo.tz_offset_source = TzSource(entry.tz_source) if entry.tz_source else photo.tz_offset_source
        photo.tz_offset_minutes = entry.tz_offset_minutes
    if entry.taken_local_naive and photo.taken_local_naive is None:
        photo.taken_local_naive = datetime.fromisoformat(entry.taken_local_naive)
    if entry.lat is not None and entry.lon is not None:
        photo.lat, photo.lon = entry.lat, entry.lon
        source = entry.location_source or "exif"
        photo.location_source = (
            LocationSource.SIDECAR if source == "sidecar" else LocationSource.EXIF
        )
        # exif_lat/lon means "the photo measured this itself", which the join
        # uses to validate the timeline and to infer clock offsets. Only a real
        # EXIF fix earns that standing; a sidecar coordinate is a position but
        # not the photo's own measurement.
        if photo.location_source == LocationSource.EXIF:
            photo.exif_lat, photo.exif_lon = entry.lat, entry.lon
    if entry.camera:
        photo.camera = entry.camera
    if entry.camera_key and entry.camera_key != "unknown":
        photo.camera_key = entry.camera_key
    if entry.width and entry.height:
        photo.width, photo.height = entry.width, entry.height
    photo.is_screenshot = entry.is_screenshot or photo.is_screenshot
    return photo


def load_photos(
    directory: Path,
    *,
    include_screenshots: bool = False,
    credits: Optional[Dict[str, str]] = None,
    manifest=None,
) -> List[Photo]:
    """Walk `directory` and build one `Photo` per image file found.

    Metadata comes from a Takeout sidecar when `resolve_sidecar` finds one, else
    from EXIF (see module docstring for the priority rules). Screenshots — no
    camera EXIF and a common display aspect ratio — are excluded unless
    `include_screenshots` is set, since they carry real timestamps and would
    otherwise happily join to a location and appear in the video.

    `credits` maps `camera_key` -> photographer name; a camera absent from the
    mapping is left uncredited.

    `manifest` is an optional `TripManifest` captured from the originals before
    anything could strip them. Where it has a value it wins over both the sidecar
    and EXIF, which is the whole point: it was read while the metadata was still
    there. Credits are resolved after the overlay, so a camera identified only by
    the manifest is still creditable.
    """
    credits = credits or {}
    directory = Path(directory)
    photos: List[Photo] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        photo = _build_photo(path, credits)
        if photo is None:
            continue
        if manifest is not None:
            entry = manifest.match(path)
            if entry is not None:
                photo = _apply_manifest(photo, entry)
                photo.credit = credits.get(photo.camera_key)
        if photo.is_screenshot and not include_screenshots:
            continue
        photos.append(photo)
    return photos
