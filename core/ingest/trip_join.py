"""The join — cross-references a parsed `Timeline` against parsed `Photo`s to
produce `TripKnowledge`.

This is the heart of the personal-timeline feature. Four steps, run in order by
`join_trip`, the module's single public entry point:

  1. `resolve_times`   — give every photo a tz-aware UTC timestamp
  2. `locate`           — attach a position + confidence to a photo (pure)
  3. `validate_positions` — cross-check photos that know their own GPS
  4. `build_beats`      — collapse the joined photos + timeline into story units

Deterministic and offline: no LLM, no network, no randomness. Same input always
produces the same output.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md, "Component 3: The Join".
"""

from __future__ import annotations

import bisect
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.ingest.geo import (
    haversine_m,
    interpolate_great_circle,
    interpolate_linear,
)
from core.ingest.models import (
    JoinReport,
    LocationSource,
    Photo,
    Place,
    Timeline,
    TimelineSegment,
    TrackConfidence,
    TrackPoint,
    TripBeat,
    TripKnowledge,
    TzSource,
)

# --------------------------------------------------------------------------
# Tunables — named here so the reasoning behind a magic number lives with it.
# --------------------------------------------------------------------------

DEFAULT_MAX_GAP = timedelta(minutes=30)          # Step 2: interpolate vs. infer
DEFAULT_GPS_DISAGREEMENT_KM = 5.0                # Step 3: threshold for a "disagreement"
MIN_OFFSET_VOTES = 3                              # Step 1: refusal rule
MIN_OFFSET_MARGIN = 2.0                           # winner must beat runner-up by 2x
OFFSET_QUARTER_HOURS = range(-48, 57)             # -12h..+14h in 15-minute steps
SHORT_MOVE_FOR_MERGE = timedelta(hours=2)         # visits separated by a move this short merge
MIN_STAY_DURATION_FOR_EMPTY_VISIT = timedelta(minutes=20)  # drop photo-less short visits
MIN_MOVE_DISTANCE_M = 25_000.0                    # keep photo-less moves only past this


def _ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to tz-aware UTC. Naive datetimes are assumed UTC —
    every producer of these objects (timeline.py, photos.py) is contracted to
    hand us tz-aware values, but this keeps the join from throwing a confusing
    naive/aware TypeError if one slips through."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_offset(minutes: int) -> str:
    """Render a UTC offset the way a person reads it: +01:00, -08:30."""
    sign = "+" if minutes >= 0 else "-"
    m = abs(minutes)
    return f"{sign}{m // 60:02d}:{m % 60:02d}"


def _dominant_tz_offset(timeline: Timeline) -> timedelta:
    """Case 4's last resort: approximate the trip's civil offset from longitude.

    Mapping a coordinate to an IANA zone needs a boundary shapefile, which the
    stdlib has no answer for. But solar time does not: every 15 degrees of
    longitude is an hour, and civil zones sit within an hour or so of that
    almost everywhere. Assuming UTC instead would put a Tokyo trip nine hours
    out — far worse than the error this approximation can make.

    Deliberately coarse. It only ever applies to photos that had no sidecar, no
    EXIF offset, and no GPS to infer from, and every such photo is marked
    TzSource.ASSUMED so the report can say so.
    """
    if not timeline.track:
        return timedelta(0)
    lons = sorted(p.lon for p in timeline.track)
    median_lon = lons[len(lons) // 2]
    return timedelta(hours=round(median_lon / 15.0))


# --------------------------------------------------------------------------
# Step 1 — resolve every photo to UTC
# --------------------------------------------------------------------------


def _interpolated_position_at(timeline: Timeline, ts: datetime) -> Optional[Tuple[float, float]]:
    """Best-effort position for an arbitrary instant, used only during offset
    inference (never for the final `locate`, which has its own gap/activity
    rules). Falls back to linear interpolation between the nearest bracketing
    track points; returns None if `ts` is outside the track's range."""
    track = timeline.track
    if not track:
        return None
    ts = _ensure_utc(ts)
    idx = bisect.bisect_left([p.ts for p in track], ts)
    if idx == 0:
        return None if ts < track[0].ts else (track[0].lat, track[0].lon)
    if idx >= len(track):
        return (track[-1].lat, track[-1].lon) if ts == track[-1].ts else None
    before, after = track[idx - 1], track[idx]
    if before.ts == after.ts:
        return (before.lat, before.lon)
    span = (after.ts - before.ts).total_seconds()
    t = (ts - before.ts).total_seconds() / span if span > 0 else 0.0
    return interpolate_linear(before.lat, before.lon, after.lat, after.lon, t)


def _best_offset_for_photo(photo: Photo, timeline: Timeline) -> Optional[int]:
    """Quarter-hour offset (in units of 15 minutes) that best explains this
    photo's own GPS against the timeline. Returns None if the photo lacks the
    inputs needed, or if the timeline has no coverage for any candidate time."""
    if photo.taken_local_naive is None or not photo.has_own_position:
        return None
    best_k: Optional[int] = None
    best_dist = float("inf")
    for k in OFFSET_QUARTER_HOURS:
        candidate_utc = _ensure_utc(photo.taken_local_naive) - timedelta(minutes=15 * k)
        pos = _interpolated_position_at(timeline, candidate_utc)
        if pos is None:
            continue
        dist = haversine_m(photo.exif_lat, photo.exif_lon, pos[0], pos[1])
        if dist < best_dist:
            best_dist = dist
            best_k = k
    return best_k


def _infer_camera_offsets(
    photos: Sequence[Photo], timeline: Timeline, report: JoinReport
) -> Dict[str, int]:
    """Group GPS+wall-clock photos by camera, take the mode of the best offset
    per camera, and apply the refusal rule. Returns camera_key -> minutes."""
    votes_by_camera: Dict[str, List[int]] = defaultdict(list)
    for photo in photos:
        if photo.taken_utc is not None:
            continue  # already resolved by sidecar/exif_offset — not a vote
        if photo.tz_offset_source == TzSource.EXIF_OFFSET:
            continue
        k = _best_offset_for_photo(photo, timeline)
        if k is not None:
            votes_by_camera[photo.camera_key].append(k)

    accepted: Dict[str, int] = {}
    for camera_key, votes in votes_by_camera.items():
        counts = Counter(votes)
        ranked = counts.most_common()
        winner_k, winner_count = ranked[0]
        runner_up_count = ranked[1][1] if len(ranked) > 1 else 0
        if winner_count < MIN_OFFSET_VOTES:
            report.warnings.append(
                f"camera {camera_key}: offset inference had only {winner_count} "
                f"agreeing photo(s) (need {MIN_OFFSET_VOTES}) — refusing, falling back "
                "to assumed timezone"
            )
            continue
        if runner_up_count > 0 and winner_count < MIN_OFFSET_MARGIN * runner_up_count:
            report.warnings.append(
                f"camera {camera_key}: offset inference ambiguous "
                f"({winner_count} votes for {winner_k * 15}min vs {runner_up_count} "
                f"for runner-up) — refusing, falling back to assumed timezone"
            )
            continue
        offset_minutes = winner_k * 15
        accepted[camera_key] = offset_minutes
        report.tz_offsets_applied[camera_key] = (
            f"{_fmt_offset(offset_minutes)} (inferred, {winner_count} photos agreeing)"
        )
    return accepted


def resolve_times(photos: List[Photo], timeline: Timeline, report: Optional[JoinReport] = None) -> None:
    """Give every photo a tz-aware UTC `taken_utc`. Mutates `photos` in place.

    Four cases, checked in priority order per spec: sidecar, EXIF offset,
    inferred (cross-correlated against GPS-bearing photos of the same
    camera), and finally an assumed fallback."""
    if report is None:
        report = JoinReport()

    # Cases 1 & 2 are the responsibility of photos.py (sidecar parsing / EXIF
    # offset parsing) — a photo arrives here with taken_utc already set, or
    # with tz_offset_source == EXIF_OFFSET and taken_utc already computed.
    # Anything still missing taken_utc falls to case 3, then case 4.
    remaining = [p for p in photos if p.taken_utc is None]

    camera_offsets = _infer_camera_offsets(remaining, timeline, report)

    dominant_offset = _dominant_tz_offset(timeline)

    # Counted, not reported one-by-one: a warning repeated once per photo buries
    # the single-photo warnings that actually need a human to look at them.
    assumed = 0
    undateable = 0

    for photo in remaining:
        if photo.taken_local_naive is None:
            # No wall-clock at all — nothing to resolve against. Mark unknown.
            photo.tz_offset_source = TzSource.UNKNOWN
            undateable += 1
            continue

        offset_minutes = camera_offsets.get(photo.camera_key)
        if offset_minutes is not None:
            photo.taken_utc = _ensure_utc(photo.taken_local_naive) - timedelta(minutes=offset_minutes)
            photo.tz_offset_source = TzSource.INFERRED
            photo.tz_offset_minutes = -offset_minutes
            continue

        # Case 4: fall back to the timeline's dominant zone.
        photo.taken_utc = _ensure_utc(photo.taken_local_naive) - dominant_offset
        photo.tz_offset_source = TzSource.ASSUMED
        photo.tz_offset_minutes = -int(dominant_offset.total_seconds() // 60)
        assumed += 1

    if undateable:
        report.warnings.append(
            f"{undateable} photo(s) carry no timestamp at all — they cannot be placed"
        )
    if assumed:
        report.warnings.append(
            f"{assumed} photos had no timezone signal — assumed "
            f"UTC{_fmt_offset(int(dominant_offset.total_seconds() // 60))} from longitude"
        )


# --------------------------------------------------------------------------
# Step 2 — locate each photo
# --------------------------------------------------------------------------


def _find_visit_segment(ts: datetime, timeline: Timeline) -> Optional[TimelineSegment]:
    for seg in timeline.segments:
        if seg.kind == "visit" and seg.start <= ts <= seg.end:
            return seg
    return None


def _enclosing_activity(ts: datetime, timeline: Timeline) -> Optional[str]:
    for seg in timeline.segments:
        if seg.kind == "move" and seg.start <= ts <= seg.end:
            return seg.activity
    return None


def locate(photo: Photo, timeline: Timeline, max_gap: timedelta = DEFAULT_MAX_GAP) -> Photo:
    """Attach a position and a confidence to a photo. Pure function — returns
    a new Photo, the input and the timeline are never mutated."""
    import copy

    result = copy.copy(photo)

    if result.taken_utc is None:
        result.confidence = TrackConfidence.UNKNOWN
        return result

    ts = _ensure_utc(result.taken_utc)

    visit = _find_visit_segment(ts, timeline)
    if visit is not None and visit.place is not None:
        result.lat = visit.place.lat
        result.lon = visit.place.lon
        result.place_name = visit.place.name
        result.location_source = LocationSource.TIMELINE
        result.confidence = TrackConfidence.VISIT
        return result

    track = timeline.track
    if not track:
        result.confidence = TrackConfidence.UNKNOWN
        return result

    timestamps = [p.ts for p in track]
    idx = bisect.bisect_left(timestamps, ts)

    if idx == 0:
        if track[0].ts == ts:
            result.lat, result.lon = track[0].lat, track[0].lon
            result.location_source = LocationSource.TIMELINE
            result.confidence = TrackConfidence.INTERPOLATED
            return result
        result.confidence = TrackConfidence.UNKNOWN
        return result

    if idx >= len(track):
        if track[-1].ts == ts:
            result.lat, result.lon = track[-1].lat, track[-1].lon
            result.location_source = LocationSource.TIMELINE
            result.confidence = TrackConfidence.INTERPOLATED
            return result
        result.confidence = TrackConfidence.UNKNOWN
        return result

    before, after = track[idx - 1], track[idx]
    gap = after.ts - before.ts
    span = gap.total_seconds()
    t = (ts - before.ts).total_seconds() / span if span > 0 else 0.0
    t = max(0.0, min(1.0, t))

    activity = _enclosing_activity(ts, timeline)
    if activity == "flying":
        lat, lon = interpolate_great_circle(before.lat, before.lon, after.lat, after.lon, t)
    else:
        lat, lon = interpolate_linear(before.lat, before.lon, after.lat, after.lon, t)

    result.lat, result.lon = lat, lon
    result.location_source = LocationSource.TIMELINE
    result.confidence = TrackConfidence.INTERPOLATED if gap < max_gap else TrackConfidence.INFERRED
    return result


# --------------------------------------------------------------------------
# Step 3 — validate against EXIF GPS
# --------------------------------------------------------------------------


def validate_positions(
    photos: Sequence[Photo],
    report: JoinReport,
    threshold_km: float = DEFAULT_GPS_DISAGREEMENT_KM,
) -> None:
    """Compare timeline-supplied positions against photos that measured their
    own GPS. Records per-photo disagreements, and escalates to a loud warning
    when many photos disagree in a way consistent with a surviving clock
    offset (rather than one-off track noise)."""
    disagreeing: List[Tuple[Photo, float]] = []

    for photo in photos:
        if not photo.has_own_position:
            continue
        if photo.location_source != LocationSource.TIMELINE:
            continue
        if photo.lat is None or photo.lon is None:
            continue
        dist_km = haversine_m(photo.exif_lat, photo.exif_lon, photo.lat, photo.lon) / 1000.0
        if dist_km >= threshold_km:
            disagreeing.append((photo, dist_km))
            report.gps_disagreements.append((photo.photo_id, dist_km))

    if not disagreeing:
        return

    # "Consistent" disagreement: cluster by camera. If a single camera
    # accounts for most of the disagreements, a clock offset likely
    # survived Step 1 for that camera specifically.
    by_camera: Dict[str, int] = Counter(p.camera_key for p, _ in disagreeing)
    for camera_key, count in by_camera.items():
        if count >= MIN_OFFSET_VOTES:
            report.warnings.append(
                f"camera {camera_key}: {count} photos disagree with the timeline by "
                f">= {threshold_km}km — a clock offset likely survived inference; "
                "trusting each photo's own GPS for these"
            )
        # A single photo disagreeing is just noise/GPS drift — trust the
        # photo's own measurement rather than the timeline's interpolation.
        for photo, _dist_km in disagreeing:
            if photo.camera_key == camera_key:
                photo.lat, photo.lon = photo.exif_lat, photo.exif_lon
                photo.location_source = LocationSource.EXIF


# --------------------------------------------------------------------------
# Step 4 — build beats
# --------------------------------------------------------------------------


def _norm(values: Sequence[float]) -> List[float]:
    """Min-max normalize to 0..1. A constant series (including a single
    value) normalizes to all-1.0 rather than dividing by zero — a lone beat
    (or a tie) shouldn't be penalized for having nothing to compare against."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _centroid(points: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _pseudo_track_from_photos(photos: Sequence[Photo]) -> List[TrackPoint]:
    """Build a coarse track out of GPS-bearing, dated photos when there is no
    real Timeline — the "photos, no timeline" degenerate case."""
    pts = [
        TrackPoint(ts=p.taken_utc, lat=p.exif_lat, lon=p.exif_lon, source="photo")
        for p in photos
        if p.taken_utc is not None and p.has_own_position
    ]
    pts.sort(key=lambda p: p.ts)
    return pts


def build_beats(
    timeline: Timeline,
    photos: Sequence[Photo],
    report: JoinReport,
) -> List[TripBeat]:
    """Collapse joined photos + timeline segments into chronological story
    units, merging short visits and dropping beats with nothing to show."""
    photos_by_time = sorted(
        (p for p in photos if p.taken_utc is not None), key=lambda p: p.taken_utc
    )

    trip_start = timeline.start
    trip_end = timeline.end
    if photos_by_time:
        first_photo_ts = photos_by_time[0].taken_utc
        last_photo_ts = photos_by_time[-1].taken_utc
        trip_start = first_photo_ts if trip_start is None else min(trip_start, first_photo_ts)
        trip_end = last_photo_ts if trip_end is None else max(trip_end, last_photo_ts)

    raw_beats: List[TripBeat] = []

    if timeline.segments:
        for seg in timeline.segments:
            # Half-open: Google writes adjacent segments sharing an instant
            # (one ends exactly as the next begins), and an inclusive test on
            # both ends puts a photo taken at that instant into two beats,
            # inflating counts and salience. A photo past the last segment's
            # end is picked up by the orphan pass below, so nothing is lost.
            seg_photos = [p for p in photos_by_time if seg.start <= p.taken_utc < seg.end]
            if seg.kind == "visit":
                raw_beats.append(
                    TripBeat(
                        beat_id=f"beat-{seg.seg_id}",
                        kind="stay",
                        start=seg.start,
                        end=seg.end,
                        place=seg.place,
                        photos=seg_photos,
                        distance_m=seg.distance_m,
                        activity=seg.activity,
                    )
                )
            else:
                raw_beats.append(
                    TripBeat(
                        beat_id=f"beat-{seg.seg_id}",
                        kind="move",
                        start=seg.start,
                        end=seg.end,
                        from_place=seg.from_place,
                        to_place=seg.to_place,
                        photos=seg_photos,
                        distance_m=seg.distance_m,
                        activity=seg.activity,
                    )
                )
        # Photos that fall outside every segment's window still need a home —
        # attach them to the nearest preceding beat, or a leading beat if
        # there is none, so no photo silently disappears from the story.
        claimed_ids = {id(p) for b in raw_beats for p in b.photos}
        orphans = [p for p in photos_by_time if id(p) not in claimed_ids]
        if orphans and raw_beats:
            for orphan in orphans:
                # Find the last beat that starts at or before this photo.
                candidates = [b for b in raw_beats if b.start <= orphan.taken_utc]
                target = candidates[-1] if candidates else raw_beats[0]
                target.photos.append(orphan)
                target.photos.sort(key=lambda p: p.taken_utc)
        elif orphans and not raw_beats:
            raw_beats.append(
                TripBeat(
                    beat_id="beat-orphans",
                    kind="stay",
                    start=orphans[0].taken_utc,
                    end=orphans[-1].taken_utc,
                    photos=orphans,
                )
            )
    elif photos_by_time:
        # Degenerate case: photos, no timeline at all. Group photos into a
        # single "stay" beat per contiguous GPS cluster is overkill for a
        # pseudo-track; the spec asks only that beats fall out, coarsely.
        # We treat all dated photos as one beat spanning the trip, letting
        # `locate` (already run) have supplied whatever position it could
        # from the pseudo-track.
        raw_beats.append(
            TripBeat(
                beat_id="beat-photos-only",
                kind="stay",
                start=photos_by_time[0].taken_utc,
                end=photos_by_time[-1].taken_utc,
                photos=list(photos_by_time),
            )
        )
    else:
        # Timeline with no segments and no photos at all — nothing to build.
        return []

    # --- merge consecutive visits to the same place separated by a short move ---
    # Requires a lookahead: a short move should only be folded away when it is
    # actually sandwiched between two visits to the *same* place ("walk to
    # lunch and back"); a short move toward a genuinely different place must
    # survive as its own beat (or be dropped later by the photo-less/distance
    # rule below), not get silently absorbed into the wrong stay.
    merged: List[TripBeat] = []
    n = len(raw_beats)
    i = 0
    while i < n:
        beat = raw_beats[i]
        if (
            beat.kind == "move"
            and merged
            and merged[-1].kind == "stay"
            and merged[-1].place is not None
            and (beat.end - beat.start) <= SHORT_MOVE_FOR_MERGE
            and i + 1 < n
            and raw_beats[i + 1].kind == "stay"
            and raw_beats[i + 1].place is not None
            and raw_beats[i + 1].place.place_id == merged[-1].place.place_id
        ):
            prev = merged[-1]
            prev.end = beat.end
            if beat.photos:
                prev.photos = sorted(prev.photos + beat.photos, key=lambda p: p.taken_utc)
            i += 1
            continue
        if (
            beat.kind == "stay"
            and merged
            and merged[-1].kind == "stay"
            and beat.place is not None
            and merged[-1].place is not None
            and beat.place.place_id == merged[-1].place.place_id
        ):
            prev = merged[-1]
            prev.end = beat.end
            prev.photos = sorted(prev.photos + beat.photos, key=lambda p: p.taken_utc)
            i += 1
            continue
        merged.append(beat)
        i += 1

    # --- drop empty short visits, drop photo-less short moves ---
    kept: List[TripBeat] = []
    for beat in merged:
        if beat.kind == "stay":
            if not beat.photos and (beat.end - beat.start) < MIN_STAY_DURATION_FOR_EMPTY_VISIT:
                continue
        else:  # move
            if not beat.photos and (beat.distance_m or 0.0) <= MIN_MOVE_DISTANCE_M:
                continue
        kept.append(beat)

    if not kept:
        return []

    kept.sort(key=lambda b: b.start)

    # --- day_index: 1-based day of trip ---
    ref_date = (trip_start or kept[0].start).date()
    for beat in kept:
        beat.day_index = (beat.start.date() - ref_date).days + 1

    # --- salience ---
    photo_counts = [len(b.photos) for b in kept]
    durations = [b.duration_sec for b in kept]

    all_place_coords = [
        (b.place.lat, b.place.lon) for b in kept if b.kind == "stay" and b.place is not None
    ]
    centroid = _centroid(all_place_coords) if all_place_coords else (0.0, 0.0)

    def _dist_from_centroid(beat: TripBeat) -> float:
        if beat.kind == "stay" and beat.place is not None and all_place_coords:
            return haversine_m(beat.place.lat, beat.place.lon, centroid[0], centroid[1])
        return 0.0

    distances = [_dist_from_centroid(b) for b in kept]

    norm_photo = _norm(photo_counts)
    norm_duration = _norm(durations)
    norm_distance = _norm(distances)

    seen_places: set = set()
    first_visit_flags: List[float] = []
    for beat in kept:
        if beat.kind == "stay" and beat.place is not None:
            is_first = beat.place.place_id not in seen_places
            seen_places.add(beat.place.place_id)
            first_visit_flags.append(1.0 if is_first else 0.0)
        else:
            first_visit_flags.append(0.0)

    for i, beat in enumerate(kept):
        beat.salience = (
            0.4 * norm_photo[i]
            + 0.2 * norm_duration[i]
            + 0.2 * norm_distance[i]
            + 0.2 * first_visit_flags[i]
        )

    return kept


# --------------------------------------------------------------------------
# Top-level entry point
# --------------------------------------------------------------------------


def _name_move_endpoints(beats: List[TripBeat]) -> None:
    """Give move beats the names of the stays they sit between.

    An activitySegment carries coordinates but no place names, so a move renders
    as "? → ?" unless it borrows from its neighbors. The stay before it is where
    the traveler left; the stay after is where they arrived — which is exactly
    what the names should say.
    """
    for i, beat in enumerate(beats):
        if beat.kind != "move":
            continue
        prev_stay = next(
            (b for b in reversed(beats[:i]) if b.kind == "stay" and b.place), None
        )
        next_stay = next(
            (b for b in beats[i + 1:] if b.kind == "stay" and b.place), None
        )
        if prev_stay and (beat.from_place is None or not beat.from_place.name):
            beat.from_place = prev_stay.place
        if next_stay and (beat.to_place is None or not beat.to_place.name):
            beat.to_place = next_stay.place


def join_trip(
    timeline: Optional[Timeline],
    photos: Optional[List[Photo]],
    credits: Optional[Dict[str, str]] = None,
    max_gap: timedelta = DEFAULT_MAX_GAP,
    gps_disagreement_km: float = DEFAULT_GPS_DISAGREEMENT_KM,
    start_after: Optional[datetime] = None,
    end_before: Optional[datetime] = None,
) -> TripKnowledge:
    """Run all four join steps and produce the trip's `TripKnowledge`.

    Handles both degenerate inputs: photos with no timeline (a pseudo-track
    is built from GPS-bearing photos) and a timeline with no photos (beats
    are still produced, photo-less).

    `start_after`/`end_before` bound the trip. The filter belongs here rather
    than in the caller because a photo's UTC time is not known until step 1 has
    run: an EXIF-only photo arrives with `taken_utc` unset, which is the normal
    case for a plain folder, and filtering before resolution silently keeps
    everything."""
    timeline = timeline if timeline is not None else Timeline()
    photos = list(photos) if photos else []

    report = JoinReport(photos_total=len(photos))

    working_timeline = timeline
    if not timeline.track and not timeline.segments and photos:
        # Degenerate case: photos, no timeline — synthesize a pseudo-track
        # from whichever photos know their own GPS so `locate` has something
        # to interpolate against. This does NOT touch the caller's Timeline.
        pseudo_track = _pseudo_track_from_photos(
            [p for p in photos if p.taken_utc is not None or p.taken_local_naive is not None]
        )
        if pseudo_track:
            working_timeline = Timeline(
                segments=[],
                track=pseudo_track,
                tz_hint=timeline.tz_hint,
                source_format="photos_only",
                stats=timeline.stats,
            )

    resolve_times(photos, working_timeline, report)

    if start_after is not None or end_before is not None:
        # Only now is `taken_utc` populated for every photo that can have one.
        def _within(ts: Optional[datetime]) -> bool:
            if ts is None:
                return False
            if start_after is not None and ts < start_after:
                return False
            return end_before is None or ts <= end_before

        kept = [p for p in photos if _within(p.taken_utc)]
        dropped = len(photos) - len(kept)
        if dropped:
            report.warnings.append(
                f"{dropped} photos fell outside the requested date range"
            )
        photos = kept
        report.photos_total = len(photos)

    located: List[Photo] = []
    for photo in photos:
        loc = locate(photo, working_timeline, max_gap=max_gap)
        located.append(loc)

    validate_positions(located, report, threshold_km=gps_disagreement_km)

    beats = build_beats(working_timeline, located, report)
    _name_move_endpoints(beats)

    # --- report tallies ---
    report.photos_dated = sum(1 for p in located if p.taken_utc is not None)
    report.photos_located = sum(1 for p in located if p.lat is not None and p.lon is not None)
    report.by_confidence = dict(Counter(p.confidence.value for p in located))
    report.by_location_source = dict(Counter(p.location_source.value for p in located))
    report.by_tz_source = dict(Counter(p.tz_offset_source.value for p in located))

    # Per-camera rollup. Counted over every photo, not just the located ones —
    # a camera whose frames all failed to place is exactly what a reader needs
    # to see, and dropping it from this table would hide the failure.
    cameras: Dict[str, Dict[str, Any]] = {}
    for p in photos:
        entry = cameras.setdefault(
            p.camera_key,
            {"count": 0, "photo_count": 0, "credit": None, "first": None, "last": None},
        )
        entry["count"] += 1
        entry["photo_count"] += 1
        entry["credit"] = entry["credit"] or p.credit
        if p.taken_utc is not None:
            if entry["first"] is None or p.taken_utc < entry["first"]:
                entry["first"] = p.taken_utc
            if entry["last"] is None or p.taken_utc > entry["last"]:
                entry["last"] = p.taken_utc
    for entry in cameras.values():
        first, last = entry["first"], entry["last"]
        entry["span"] = (
            f"{first:%b %-d}–{last:%-d}" if first and last and first.month == last.month
            else f"{first:%b %-d}–{last:%b %-d}" if first and last
            else ""
        )
    report.cameras = dict(
        sorted(cameras.items(), key=lambda kv: -kv[1]["count"])
    )

    places: List[Place] = []
    seen_place_ids: set = set()
    for beat in beats:
        for place in (beat.place, beat.from_place, beat.to_place):
            if place is not None and place.place_id not in seen_place_ids:
                seen_place_ids.add(place.place_id)
                places.append(place)

    total_distance_m = sum(b.distance_m or 0.0 for b in beats if b.kind == "move")

    trip_start = working_timeline.start
    trip_end = working_timeline.end
    dated_photos = [p for p in located if p.taken_utc is not None]
    if dated_photos:
        first_photo_ts = min(p.taken_utc for p in dated_photos)
        last_photo_ts = max(p.taken_utc for p in dated_photos)
        trip_start = first_photo_ts if trip_start is None else min(trip_start, first_photo_ts)
        trip_end = last_photo_ts if trip_end is None else max(trip_end, last_photo_ts)
    if beats:
        beat_start = min(b.start for b in beats)
        beat_end = max(b.end for b in beats)
        trip_start = beat_start if trip_start is None else min(trip_start, beat_start)
        trip_end = beat_end if trip_end is None else max(trip_end, beat_end)

    title = _derive_title(trip_start, places)

    return TripKnowledge(
        trip_id=_derive_trip_id(trip_start, trip_end),
        title=title,
        start=trip_start,
        end=trip_end,
        beats=beats,
        places=places,
        photos=located,
        total_distance_m=total_distance_m,
        credits=dict(credits) if credits else {},
        report=report,
    )


def _derive_trip_id(start: Optional[datetime], end: Optional[datetime]) -> str:
    if start is None:
        return "trip-unknown"
    return f"trip-{start.date().isoformat()}"


def _derive_title(start: Optional[datetime], places: Sequence[Place]) -> str:
    """A user-overridable default: "<Region>, <Month Year>".

    Prefer the region shared by the trip's addresses over the first place name —
    a trip is "Portugal, May 2023", not "Alfama, May 2023" after the neighborhood
    that happened to be visited first. Google's addresses end in the country, so
    the last comma-separated token of the most common address serves as the
    region. Falls back to the first named place when there are no addresses.
    """
    regions = Counter(
        p.address.rsplit(",", 1)[-1].strip()
        for p in places
        if p.address and "," in p.address
    )
    label = regions.most_common(1)[0][0] if regions else None
    if not label:
        label = next((p.name for p in places if p.name), None)
    if start is None:
        return label or "Untitled Trip"
    when = start.strftime("%B %Y")
    return f"{label}, {when}" if label else f"Trip, {when}"
