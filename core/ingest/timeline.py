"""Google location-history ingestion.

Google Takeout / on-device Timeline exports have shipped at least four different
JSON shapes over the years (`Records.json`, `Semantic Location History/*.json`,
`Timeline.json`, and a bare top-level array). `parse_timeline()` auto-detects
which one it is looking at, normalizes every coordinate/timestamp encoding at
the edge, and returns a single `Timeline` (see `core/ingest/models.py`) so
nothing downstream ever has to know which export vintage produced it.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md, "Component 1: Timeline Ingestion".
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.ingest.geo import haversine_m, speed_kmh
from core.ingest.models import FilterStats, Place, Timeline, TimelineSegment, TrackPoint

# A jump implying more speed than this is a teleport (bad fix), unless the
# enclosing activity is "flying" — see Component 1 / Filtering in the spec.
_MAX_TELEPORT_KMH = 1200.0
# Points closer together than this are the same stationary moment.
_COLLAPSE_RADIUS_M = 25.0

# Filenames Google has used for the raw-track / on-device exports. Matched
# case-insensitively when walking a Takeout directory. Semantic Location
# History files are matched by parent-directory name instead, since their
# filenames vary by year/month (e.g. "2023_MAY.json").
_KNOWN_FILENAMES = {"records.json", "timeline.json", "location-history.json"}

_RFC3339_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<frac>\.\d+)?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)


# ---------------------------------------------------------------------------
# Normalization primitives — the crux of this module. Every coordinate and
# timestamp shape Google has ever shipped funnels through these two
# functions, so nothing downstream ever sees a raw Google encoding.
# ---------------------------------------------------------------------------


def parse_coord(value: Any) -> Optional[Tuple[float, float]]:
    """Normalize any of Google's coordinate shapes to (lat, lon) floats.

    Handles E7 integers (`{"latitudeE7": ..., "longitudeE7": ...}`), `"geo:"`
    URIs, `"38.682°, -9.1393°"` degree strings, `{"latLng": <degree string>}`,
    and `{"latitude": ..., "longitude": ...}`. Returns None for anything else
    rather than raising — callers count this in `FilterStats.unparseable`.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return _parse_coord_string(value)
    if isinstance(value, dict):
        if "latLng" in value:
            return _parse_coord_string(value["latLng"])
        if "latitudeE7" in value and "longitudeE7" in value:
            try:
                lat_e7 = value["latitudeE7"]
                lon_e7 = value["longitudeE7"]
                if lat_e7 is None or lon_e7 is None:
                    return None
                return (float(lat_e7) / 1e7, float(lon_e7) / 1e7)
            except (TypeError, ValueError):
                return None
        if "latitude" in value and "longitude" in value:
            try:
                lat = value["latitude"]
                lon = value["longitude"]
                if lat is None or lon is None:
                    return None
                return (float(lat), float(lon))
            except (TypeError, ValueError):
                return None
    return None


def _parse_coord_string(text: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.lower().startswith("geo:"):
        s = s[4:].split(";")[0]
    s = s.replace("°", "")  # strip degree signs
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 2:
        return None
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError:
        return None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an RFC3339 timestamp or legacy epoch-millis value.

    Handles `Z`, numeric offsets (with or without a colon), and fractional
    seconds of any length, plus the legacy `timestampMs` string-of-millis
    encoding. Always returns a tz-aware UTC datetime, or None if the value
    can't be parsed — never a naive datetime, since downstream comparisons
    (speed filtering, gap detection) would raise on a naive/aware mismatch.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit():
            return _from_epoch(int(s))
        return _parse_rfc3339(s)
    return None


def _from_epoch(value: float) -> Optional[datetime]:
    # Millisecond epochs (Google's timestampMs) are ~13 digits; second
    # epochs are ~10. 1e12 comfortably separates them until the year 2286.
    seconds = value / 1000.0 if value > 1e12 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_rfc3339(s: str) -> Optional[datetime]:
    m = _RFC3339_RE.match(s)
    if not m:
        return None
    frac = m.group("frac") or ""
    if frac:
        digits = frac[1:][:6].ljust(6, "0")
        frac = "." + digits
    tz = m.group("tz") or "Z"
    if tz == "Z":
        tz = "+00:00"
    elif ":" not in tz:
        tz = f"{tz[:3]}:{tz[3:]}"
    iso = f"{m.group('date')}T{m.group('time')}{frac}{tz}"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


def _seg_id(kind: str, start: datetime, end: datetime) -> str:
    key = f"{kind}:{start.isoformat()}:{end.isoformat()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _place_id(lat: float, lon: float, name: Optional[str]) -> str:
    key = f"{round(lat, 5)}:{round(lon, 5)}:{name or ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Segment builders — shared by all four formats once each format's per-item
# fields have been extracted to a common shape.
# ---------------------------------------------------------------------------

# (point, activity_type) — activity is carried alongside the point only
# long enough for the teleport filter to consult it, then dropped.
_Entry = Tuple[TrackPoint, Optional[str]]


def _build_visit(
    start: Optional[datetime],
    end: Optional[datetime],
    loc_value: Any,
    name: Optional[str],
    address: Optional[str],
    stats: FilterStats,
) -> Tuple[Optional[TimelineSegment], List[_Entry]]:
    stats.points_in += 1
    coord = parse_coord(loc_value)
    if coord is None or start is None:
        stats.unparseable += 1
        return None, []
    lat, lon = coord
    end = end or start
    place = Place(place_id=_place_id(lat, lon, name), name=name, lat=lat, lon=lon, address=address)
    point = TrackPoint(ts=start, lat=lat, lon=lon, source="visit")
    seg = TimelineSegment(
        seg_id=_seg_id("visit", start, end), kind="visit", start=start, end=end, place=place, path=[point]
    )
    return seg, [(point, None)]


def _build_move(
    start: Optional[datetime],
    end: Optional[datetime],
    start_loc: Any,
    end_loc: Any,
    activity_type: Optional[str],
    distance: Any,
    stats: FilterStats,
) -> Tuple[Optional[TimelineSegment], List[_Entry]]:
    stats.points_in += 2
    if start is None:
        stats.unparseable += 2
        return None, []
    end = end or start
    activity = activity_type.lower() if isinstance(activity_type, str) and activity_type else None

    points: List[_Entry] = []
    from_place: Optional[Place] = None
    to_place: Optional[Place] = None

    start_coord = parse_coord(start_loc)
    if start_coord is not None:
        lat, lon = start_coord
        from_place = Place(place_id=_place_id(lat, lon, None), lat=lat, lon=lon)
        points.append((TrackPoint(ts=start, lat=lat, lon=lon, source="activity"), activity))
    else:
        stats.unparseable += 1

    end_coord = parse_coord(end_loc)
    if end_coord is not None:
        lat, lon = end_coord
        to_place = Place(place_id=_place_id(lat, lon, None), lat=lat, lon=lon)
        points.append((TrackPoint(ts=end, lat=lat, lon=lon, source="activity"), activity))
    else:
        stats.unparseable += 1

    seg = TimelineSegment(
        seg_id=_seg_id("move", start, end),
        kind="move",
        start=start,
        end=end,
        from_place=from_place,
        to_place=to_place,
        activity=activity,
        distance_m=float(distance) if isinstance(distance, (int, float)) else None,
        path=[point for point, _ in points],
    )
    return seg, points


# ---------------------------------------------------------------------------
# Per-format parsers. Each returns (segments, entries); entries are merged,
# sorted, and filtered together regardless of which format(s) produced them.
# ---------------------------------------------------------------------------


def _parse_records(data: Dict[str, Any], stats: FilterStats) -> Tuple[List[TimelineSegment], List[_Entry]]:
    entries: List[_Entry] = []
    for loc in data.get("locations", []) or []:
        stats.points_in += 1
        coord = parse_coord(loc)
        raw_ts = loc.get("timestamp")
        if raw_ts is None:
            raw_ts = loc.get("timestampMs")
        ts = parse_timestamp(raw_ts)
        if coord is None or ts is None:
            stats.unparseable += 1
            continue
        lat, lon = coord
        accuracy = loc.get("accuracy")
        point = TrackPoint(ts=ts, lat=lat, lon=lon, accuracy_m=accuracy, source="record")
        entries.append((point, None))
    return [], entries


def _parse_semantic(data: Dict[str, Any], stats: FilterStats) -> Tuple[List[TimelineSegment], List[_Entry]]:
    segments: List[TimelineSegment] = []
    entries: List[_Entry] = []
    for obj in data.get("timelineObjects", []) or []:
        if "placeVisit" in obj:
            pv = obj["placeVisit"] or {}
            location = pv.get("location", {}) or {}
            duration = pv.get("duration", {}) or {}
            start = parse_timestamp(duration.get("startTimestamp") or duration.get("startTimestampMs"))
            end = parse_timestamp(duration.get("endTimestamp") or duration.get("endTimestampMs"))
            seg, pts = _build_visit(start, end, location, location.get("name"), location.get("address"), stats)
        elif "activitySegment" in obj:
            asg = obj["activitySegment"] or {}
            duration = asg.get("duration", {}) or {}
            start = parse_timestamp(duration.get("startTimestamp") or duration.get("startTimestampMs"))
            end = parse_timestamp(duration.get("endTimestamp") or duration.get("endTimestampMs"))
            seg, pts = _build_move(
                start,
                end,
                asg.get("startLocation", {}),
                asg.get("endLocation", {}),
                asg.get("activityType"),
                asg.get("distance"),
                stats,
            )
        else:
            continue
        if seg is not None:
            segments.append(seg)
        entries.extend(pts)
    return segments, entries


def _parse_segment_list(items: List[Dict[str, Any]], stats: FilterStats) -> Tuple[List[TimelineSegment], List[_Entry]]:
    """Shared parser for `semanticSegments` (wrapped) and bare top-level arrays.

    Both use the same per-item shape: `{"startTime", "endTime", "visit" | "activity"}`.
    """
    segments: List[TimelineSegment] = []
    entries: List[_Entry] = []
    for item in items or []:
        start = parse_timestamp(item.get("startTime"))
        end = parse_timestamp(item.get("endTime"))
        if "visit" in item:
            visit = item.get("visit") or {}
            top = visit.get("topCandidate") or {}
            loc = top.get("placeLocation")
            if loc is None:
                loc = visit.get("location")
            name = top.get("semanticType") or visit.get("name")
            address = visit.get("address")
            seg, pts = _build_visit(start, end, loc, name, address, stats)
        elif "activity" in item:
            activity = item.get("activity") or {}
            top = activity.get("topCandidate") or {}
            start_loc = activity.get("start")
            if start_loc is None:
                start_loc = activity.get("startLocation")
            end_loc = activity.get("end")
            if end_loc is None:
                end_loc = activity.get("endLocation")
            activity_type = top.get("type") or activity.get("activityType")
            distance = activity.get("distanceMeters")
            if distance is None:
                distance = activity.get("distance")
            seg, pts = _build_move(start, end, start_loc, end_loc, activity_type, distance, stats)
        else:
            continue
        if seg is not None:
            segments.append(seg)
        entries.extend(pts)
    return segments, entries


def _detect_and_parse(data: Any, stats: FilterStats) -> Tuple[str, List[TimelineSegment], List[_Entry]]:
    if isinstance(data, list):
        segments, entries = _parse_segment_list(data, stats)
        return "bare", segments, entries
    if isinstance(data, dict):
        if "locations" in data:
            segments, entries = _parse_records(data, stats)
            return "records", segments, entries
        if "timelineObjects" in data:
            segments, entries = _parse_semantic(data, stats)
            return "semantic", segments, entries
        if "semanticSegments" in data:
            segments, entries = _parse_segment_list(data.get("semanticSegments") or [], stats)
            return "wrapped", segments, entries
    return "unknown", [], []


# ---------------------------------------------------------------------------
# Filtering — accuracy, teleports, and stationary-run collapsing.
# ---------------------------------------------------------------------------


def _filter_and_collapse(entries: List[_Entry], stats: FilterStats, max_accuracy_m: int) -> List[TrackPoint]:
    stage1: List[_Entry] = []
    for point, activity in entries:
        if point.accuracy_m is not None and point.accuracy_m > max_accuracy_m:
            stats.dropped_accuracy += 1
            continue
        stage1.append((point, activity))

    stage2: List[_Entry] = []
    prev: Optional[_Entry] = None
    for point, activity in stage1:
        if prev is not None:
            prev_point, prev_activity = prev
            seconds = (point.ts - prev_point.ts).total_seconds()
            if seconds > 0:
                velocity = speed_kmh(prev_point.lat, prev_point.lon, point.lat, point.lon, seconds)
                flying = (activity == "flying") or (prev_activity == "flying")
                if velocity > _MAX_TELEPORT_KMH and not flying:
                    stats.dropped_speed += 1
                    continue
        stage2.append((point, activity))
        prev = (point, activity)

    collapsed: List[TrackPoint] = []
    run: List[TrackPoint] = []

    def flush() -> None:
        if not run:
            return
        if len(run) == 1:
            collapsed.append(run[0])
            return
        stats.collapsed_stationary += len(run) - 1
        lat = statistics.median(p.lat for p in run)
        lon = statistics.median(p.lon for p in run)
        timestamps = sorted(p.ts for p in run)
        mid = len(timestamps) // 2
        if len(timestamps) % 2 == 1:
            median_ts = timestamps[mid]
        else:
            median_ts = timestamps[mid - 1] + (timestamps[mid] - timestamps[mid - 1]) / 2
        accuracies = [p.accuracy_m for p in run if p.accuracy_m is not None]
        collapsed.append(
            TrackPoint(
                ts=median_ts,
                lat=lat,
                lon=lon,
                accuracy_m=min(accuracies) if accuracies else None,
                source=run[0].source,
            )
        )

    for point, _activity in stage2:
        if run and haversine_m(run[-1].lat, run[-1].lon, point.lat, point.lon) <= _COLLAPSE_RADIUS_M:
            run.append(point)
        else:
            flush()
            run = [point]
    flush()

    stats.points_out = len(collapsed)
    return collapsed


def _tz_hint(track: List[TrackPoint]) -> Optional[str]:
    """A cheap, dependency-free timezone guess from the dominant longitude.

    Not a real IANA zone lookup (that would need a shapefile/tzdb dependency
    we don't have) — just a plausible fixed-offset zone, good enough to seed
    a UI default. `Etc/GMT` zones use POSIX's inverted sign convention.
    """
    if not track:
        return None
    lon = statistics.median(p.lon for p in track)
    offset = max(-12, min(14, round(lon / 15.0)))
    if offset == 0:
        return "Etc/UTC"
    sign = "-" if offset > 0 else "+"
    return f"Etc/GMT{sign}{abs(offset)}"


# ---------------------------------------------------------------------------
# File / directory resolution
# ---------------------------------------------------------------------------


def _resolve_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    found: List[Path] = []
    for candidate in sorted(path.rglob("*.json")):
        if candidate.name.lower() in _KNOWN_FILENAMES:
            found.append(candidate)
        elif "semantic location history" in str(candidate.parent).lower():
            found.append(candidate)
    return found


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_timeline(path: Path, *, max_accuracy_m: int = 2000) -> Timeline:
    """Parse a Google location-history export into a normalized `Timeline`.

    `path` may be a single export file (any of the four formats) or a
    Takeout directory, which is walked for `Records.json`, files under
    `Semantic Location History/`, `Timeline.json`, and `location-history.json`.

    Filtering (accuracy threshold, teleport rejection, stationary-run
    collapsing) is applied once, across the merged track from every file
    found, so multi-file Takeout exports produce one continuous track.
    """
    path = Path(path)
    stats = FilterStats()
    source_format = "unknown"
    all_segments: List[TimelineSegment] = []
    all_entries: List[_Entry] = []

    for file_path in _resolve_files(path):
        data = _load_json(file_path)
        if data is None:
            continue
        fmt, segments, entries = _detect_and_parse(data, stats)
        if fmt != "unknown":
            source_format = fmt
        all_segments.extend(segments)
        all_entries.extend(entries)

    all_entries.sort(key=lambda entry: entry[0].ts)
    track = _filter_and_collapse(all_entries, stats, max_accuracy_m)
    all_segments.sort(key=lambda seg: seg.start)

    return Timeline(
        segments=all_segments,
        track=track,
        tz_hint=_tz_hint(track),
        source_format=source_format,
        stats=stats,
    )
