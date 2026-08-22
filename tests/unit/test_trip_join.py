"""Unit tests for core/ingest/trip_join.py — the timeline/photo join.

Fixtures build Timeline/Photo objects directly (no dependency on the
concurrently-written timeline.py / photos.py parsers).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.ingest.geo import interpolate_linear
from core.ingest.models import (
    JoinReport,
    LocationSource,
    Photo,
    Place,
    Timeline,
    TimelineSegment,
    TrackConfidence,
    TrackPoint,
    TzSource,
)
from core.ingest.trip_join import (
    build_beats,
    join_trip,
    locate,
    resolve_times,
    validate_positions,
)


def _dt(y, m, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=timezone.utc)


def _photo(photo_id: str, **kwargs) -> Photo:
    defaults = dict(
        photo_id=photo_id,
        path=Path(f"/photos/{photo_id}.jpg"),
        camera_key="unknown",
    )
    defaults.update(kwargs)
    return Photo(**defaults)


# ---------------------------------------------------------------------------
# Step 2: locate()
# ---------------------------------------------------------------------------


def test_photo_inside_visit_gets_visit_confidence_and_place_name():
    place = Place(place_id="p1", name="Castelo de Sao Jorge", lat=38.7139, lon=-9.1334)
    seg = TimelineSegment(
        seg_id="seg1",
        kind="visit",
        start=_dt(2024, 5, 1, 10, 0),
        end=_dt(2024, 5, 1, 12, 0),
        place=place,
    )
    timeline = Timeline(segments=[seg], track=[])
    photo = _photo("a", taken_utc=_dt(2024, 5, 1, 11, 0))

    result = locate(photo, timeline)

    assert result.confidence == TrackConfidence.VISIT
    assert result.place_name == "Castelo de Sao Jorge"
    assert result.lat == pytest.approx(38.7139)
    assert result.lon == pytest.approx(-9.1334)
    assert result.location_source == LocationSource.TIMELINE
    # pure function — the input photo must not be mutated
    assert photo.place_name is None


def test_photo_in_six_hour_gap_gets_inferred_not_interpolated():
    track = [
        TrackPoint(ts=_dt(2024, 5, 1, 6, 0), lat=38.0, lon=-9.0),
        TrackPoint(ts=_dt(2024, 5, 1, 12, 0), lat=39.0, lon=-9.0),  # 6h gap
    ]
    timeline = Timeline(segments=[], track=track)
    photo = _photo("b", taken_utc=_dt(2024, 5, 1, 9, 0))

    result = locate(photo, timeline)

    assert result.confidence == TrackConfidence.INFERRED
    assert result.location_source == LocationSource.TIMELINE
    assert result.lat is not None


def test_photo_in_short_gap_gets_interpolated():
    track = [
        TrackPoint(ts=_dt(2024, 5, 1, 6, 0), lat=38.0, lon=-9.0),
        TrackPoint(ts=_dt(2024, 5, 1, 6, 10), lat=38.1, lon=-9.0),
    ]
    timeline = Timeline(segments=[], track=track)
    photo = _photo("c", taken_utc=_dt(2024, 5, 1, 6, 5))

    result = locate(photo, timeline)

    assert result.confidence == TrackConfidence.INTERPOLATED
    expected_lat, expected_lon = interpolate_linear(38.0, -9.0, 38.1, -9.0, 0.5)
    assert result.lat == pytest.approx(expected_lat)
    assert result.lon == pytest.approx(expected_lon)


def test_photo_outside_track_range_is_unknown():
    track = [
        TrackPoint(ts=_dt(2024, 5, 1, 6, 0), lat=38.0, lon=-9.0),
        TrackPoint(ts=_dt(2024, 5, 1, 6, 10), lat=38.1, lon=-9.0),
    ]
    timeline = Timeline(segments=[], track=track)
    photo = _photo("d", taken_utc=_dt(2024, 5, 2, 6, 0))

    result = locate(photo, timeline)

    assert result.confidence == TrackConfidence.UNKNOWN
    assert result.lat is None


def test_great_circle_used_when_enclosing_activity_is_flying():
    track = [
        TrackPoint(ts=_dt(2024, 5, 1, 0, 0), lat=40.0, lon=-74.0),   # NYC
        TrackPoint(ts=_dt(2024, 5, 1, 8, 0), lat=38.7, lon=-9.1),    # Lisbon
    ]
    flight = TimelineSegment(
        seg_id="flight1",
        kind="move",
        start=_dt(2024, 5, 1, 0, 0),
        end=_dt(2024, 5, 1, 8, 0),
        activity="flying",
    )
    timeline = Timeline(segments=[flight], track=track)
    photo = _photo("e", taken_utc=_dt(2024, 5, 1, 4, 0))

    result = locate(photo, timeline)

    from core.ingest.geo import interpolate_great_circle

    expected_lat, expected_lon = interpolate_great_circle(40.0, -74.0, 38.7, -9.1, 0.5)
    assert result.lat == pytest.approx(expected_lat)
    assert result.lon == pytest.approx(expected_lon)


# ---------------------------------------------------------------------------
# Step 1: resolve_times() — clock-skew recovery + refusal rule
# ---------------------------------------------------------------------------


def _moving_track(start: datetime, hours: int, lat0: float, lat_per_hour: float, lon: float):
    return [
        TrackPoint(ts=start + timedelta(hours=h), lat=lat0 + lat_per_hour * h, lon=lon)
        for h in range(hours + 1)
    ]


def test_clock_skew_recovery_applies_to_same_camera_only():
    start = _dt(2024, 5, 1, 0, 0)
    # The person moves steadily north over 24 hours — enough spatial spread
    # that the offset search unambiguously prefers the true 8h correction.
    track = _moving_track(start, hours=24, lat0=38.0, lat_per_hour=0.125, lon=-8.5)
    timeline = Timeline(segments=[], track=track)

    skewed_camera = "Apple/iPhone14Pro/SN1"
    other_camera = "Canon/EOS/SN2"

    def true_position(true_ts: datetime):
        elapsed_h = (true_ts - start).total_seconds() / 3600.0
        return 38.0 + 0.125 * elapsed_h, -8.5

    photos = []
    # 4 GPS-bearing photos from the skewed camera, wall clock 8h ahead of true UTC.
    for i, hour in enumerate([2, 8, 14, 20]):
        true_ts = start + timedelta(hours=hour)
        lat, lon = true_position(true_ts)
        photos.append(
            _photo(
                f"skewed-{i}",
                taken_local_naive=(true_ts + timedelta(hours=8)).replace(tzinfo=None),
                exif_lat=lat,
                exif_lon=lon,
                camera_key=skewed_camera,
            )
        )
    # A GPS-less photo from the SAME camera should be corrected by the
    # inferred offset.
    gps_less_true_ts = start + timedelta(hours=11)
    gps_less = _photo(
        "skewed-gpsless",
        taken_local_naive=(gps_less_true_ts + timedelta(hours=8)).replace(tzinfo=None),
        camera_key=skewed_camera,
    )
    photos.append(gps_less)

    # A photo from a DIFFERENT camera, no GPS, no votes for it — must fall
    # back to the assumed-timezone case, not inherit the other camera's fix.
    unrelated_true_ts = start + timedelta(hours=5)
    unrelated = _photo(
        "other-camera",
        taken_local_naive=unrelated_true_ts.replace(tzinfo=None),
        camera_key=other_camera,
    )
    photos.append(unrelated)

    report = JoinReport()
    resolve_times(photos, timeline, report)

    for i in range(4):
        p = next(p for p in photos if p.photo_id == f"skewed-{i}")
        assert p.tz_offset_source == TzSource.INFERRED
        assert p.tz_offset_minutes == -8 * 60

    assert gps_less.tz_offset_source == TzSource.INFERRED
    assert gps_less.tz_offset_minutes == -8 * 60
    assert gps_less.taken_utc == gps_less_true_ts

    assert unrelated.tz_offset_source == TzSource.ASSUMED
    assert skewed_camera in report.tz_offsets_applied
    assert other_camera not in report.tz_offsets_applied


def test_weak_inference_refuses_and_warns():
    start = _dt(2024, 5, 1, 0, 0)
    track = _moving_track(start, hours=24, lat0=38.0, lat_per_hour=0.125, lon=-8.5)
    timeline = Timeline(segments=[], track=track)
    camera = "Apple/iPhoneX/SN9"

    def true_position(true_ts: datetime):
        elapsed_h = (true_ts - start).total_seconds() / 3600.0
        return 38.0 + 0.125 * elapsed_h, -8.5

    # Two photos that each best-match a *different* offset — no consensus.
    ts_a = start + timedelta(hours=3)
    lat_a, lon_a = true_position(ts_a)
    photo_a = _photo(
        "disagree-a",
        taken_local_naive=(ts_a + timedelta(hours=8)).replace(tzinfo=None),
        exif_lat=lat_a,
        exif_lon=lon_a,
        camera_key=camera,
    )
    ts_b = start + timedelta(hours=15)
    lat_b, lon_b = true_position(ts_b)
    photo_b = _photo(
        "disagree-b",
        taken_local_naive=(ts_b + timedelta(hours=3)).replace(tzinfo=None),
        exif_lat=lat_b,
        exif_lon=lon_b,
        camera_key=camera,
    )

    report = JoinReport()
    resolve_times([photo_a, photo_b], timeline, report)

    assert camera not in report.tz_offsets_applied
    assert photo_a.tz_offset_source == TzSource.ASSUMED
    assert photo_b.tz_offset_source == TzSource.ASSUMED
    assert any("refusing" in w for w in report.warnings)


def test_sidecar_time_is_left_alone():
    photo = _photo("sc", taken_utc=_dt(2024, 5, 1, 10, 0), tz_offset_source=TzSource.SIDECAR)
    timeline = Timeline(segments=[], track=[])
    report = JoinReport()

    resolve_times([photo], timeline, report)

    assert photo.taken_utc == _dt(2024, 5, 1, 10, 0)
    assert photo.tz_offset_source == TzSource.SIDECAR


# ---------------------------------------------------------------------------
# Step 3: validate_positions()
# ---------------------------------------------------------------------------


def test_single_disagreement_trusts_photo_gps():
    photo = _photo(
        "gps1",
        taken_utc=_dt(2024, 5, 1, 10, 0),
        exif_lat=38.0,
        exif_lon=-9.0,
        lat=39.0,  # timeline said something ~111km away
        lon=-9.0,
        location_source=LocationSource.TIMELINE,
        camera_key="cam1",
    )
    report = JoinReport()

    validate_positions([photo], report)

    assert photo.location_source == LocationSource.EXIF
    assert photo.lat == pytest.approx(38.0)
    assert len(report.gps_disagreements) == 1
    assert report.gps_disagreements[0][0] == "gps1"


def test_many_consistent_disagreements_warn_loudly():
    photos = []
    for i in range(3):
        photos.append(
            _photo(
                f"gps{i}",
                taken_utc=_dt(2024, 5, 1, 10, 0),
                exif_lat=38.0 + i * 0.001,
                exif_lon=-9.0,
                lat=39.0 + i * 0.001,
                lon=-9.0,
                location_source=LocationSource.TIMELINE,
                camera_key="cam-skewed",
            )
        )
    report = JoinReport()

    validate_positions(photos, report)

    assert len(report.gps_disagreements) == 3
    assert any("cam-skewed" in w and "clock offset" in w for w in report.warnings)


def test_no_disagreement_below_threshold():
    photo = _photo(
        "gps-close",
        taken_utc=_dt(2024, 5, 1, 10, 0),
        exif_lat=38.000,
        exif_lon=-9.000,
        lat=38.001,
        lon=-9.000,
        location_source=LocationSource.TIMELINE,
        camera_key="cam1",
    )
    report = JoinReport()

    validate_positions([photo], report)

    assert report.gps_disagreements == []
    assert photo.location_source == LocationSource.TIMELINE


# ---------------------------------------------------------------------------
# Step 4 / join_trip(): beats, salience, degenerate inputs
# ---------------------------------------------------------------------------


def test_photos_only_no_timeline_still_yields_beats():
    photos = [
        _photo(
            "p1",
            taken_local_naive=datetime(2024, 5, 1, 10, 0),
            exif_lat=38.7,
            exif_lon=-9.1,
            camera_key="cam1",
        ),
        _photo(
            "p2",
            taken_local_naive=datetime(2024, 5, 1, 11, 0),
            exif_lat=38.71,
            exif_lon=-9.11,
            camera_key="cam1",
        ),
    ]
    knowledge = join_trip(timeline=None, photos=photos)

    assert len(knowledge.beats) >= 1
    assert sum(len(b.photos) for b in knowledge.beats) == 2
    assert knowledge.report.photos_total == 2


def test_timeline_only_no_photos_still_yields_beats():
    place = Place(place_id="p1", name="Sintra", lat=38.7979, lon=-9.3904)
    seg = TimelineSegment(
        seg_id="seg1",
        kind="visit",
        start=_dt(2024, 5, 1, 9, 0),
        end=_dt(2024, 5, 1, 14, 0),
        place=place,
    )
    timeline = Timeline(segments=[seg], track=[])

    knowledge = join_trip(timeline=timeline, photos=[])

    assert len(knowledge.beats) == 1
    assert knowledge.beats[0].place.name == "Sintra"
    assert knowledge.beats[0].photos == []


def test_salience_in_range_and_photo_count_dominates():
    place_a = Place(place_id="a", name="A", lat=0.0, lon=0.0)
    place_b = Place(place_id="b", name="B", lat=0.0, lon=0.2)
    seg_a = TimelineSegment(
        seg_id="sa", kind="visit", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 10, 0),
        place=place_a,
    )
    seg_b = TimelineSegment(
        seg_id="sb", kind="visit", start=_dt(2024, 5, 2, 8, 0), end=_dt(2024, 5, 2, 10, 0),
        place=place_b,
    )
    timeline = Timeline(segments=[seg_a, seg_b], track=[])

    photos = [
        _photo(f"a{i}", taken_utc=_dt(2024, 5, 1, 9, 0)) for i in range(5)
    ] + [
        _photo("b0", taken_utc=_dt(2024, 5, 2, 9, 0)),
    ]

    knowledge = join_trip(timeline=timeline, photos=photos)

    beat_a = next(b for b in knowledge.beats if b.place and b.place.place_id == "a")
    beat_b = next(b for b in knowledge.beats if b.place and b.place.place_id == "b")

    for beat in knowledge.beats:
        assert 0.0 <= beat.salience <= 1.0

    assert beat_a.salience > beat_b.salience


def test_single_beat_trip_does_not_raise_and_salience_is_valid():
    place = Place(place_id="only", name="Only Place", lat=1.0, lon=1.0)
    seg = TimelineSegment(
        seg_id="s1", kind="visit", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 10, 0),
        place=place,
    )
    timeline = Timeline(segments=[seg], track=[])
    photos = [_photo("only1", taken_utc=_dt(2024, 5, 1, 9, 0))]

    knowledge = join_trip(timeline=timeline, photos=photos)

    assert len(knowledge.beats) == 1
    assert 0.0 <= knowledge.beats[0].salience <= 1.0


def test_short_move_between_same_place_visits_merges():
    place = Place(place_id="hotel", name="Hotel", lat=10.0, lon=10.0)
    other = Place(place_id="restaurant", name="Restaurant", lat=10.01, lon=10.0)
    seg1 = TimelineSegment(
        seg_id="s1", kind="visit", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 12, 0),
        place=place,
    )
    move = TimelineSegment(
        seg_id="m1", kind="move", start=_dt(2024, 5, 1, 12, 0), end=_dt(2024, 5, 1, 12, 30),
        from_place=place, to_place=other,
    )
    seg2 = TimelineSegment(
        seg_id="s2", kind="visit", start=_dt(2024, 5, 1, 13, 30), end=_dt(2024, 5, 1, 18, 0),
        place=place,
    )
    timeline = Timeline(segments=[seg1, move, seg2], track=[])
    photos = [_photo("p1", taken_utc=_dt(2024, 5, 1, 9, 0))]

    knowledge = join_trip(timeline=timeline, photos=photos)

    stays = [b for b in knowledge.beats if b.kind == "stay"]
    assert len(stays) == 1
    assert stays[0].start == _dt(2024, 5, 1, 8, 0)
    assert stays[0].end == _dt(2024, 5, 1, 18, 0)


def test_photoless_short_visit_is_dropped():
    place = Place(place_id="brief", name="Gas Station", lat=5.0, lon=5.0)
    seg = TimelineSegment(
        seg_id="s1", kind="visit", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 8, 5),
        place=place,
    )
    timeline = Timeline(segments=[seg], track=[])

    knowledge = join_trip(timeline=timeline, photos=[])

    assert knowledge.beats == []


def test_photoless_long_move_kept_short_move_dropped():
    long_move = TimelineSegment(
        seg_id="m1", kind="move", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 12, 0),
        distance_m=50_000.0, activity="in_passenger_vehicle",
    )
    short_move = TimelineSegment(
        seg_id="m2", kind="move", start=_dt(2024, 5, 2, 8, 0), end=_dt(2024, 5, 2, 8, 10),
        distance_m=500.0, activity="walking",
    )
    timeline = Timeline(segments=[long_move, short_move], track=[])

    knowledge = join_trip(timeline=timeline, photos=[])

    kinds_and_ids = [(b.kind, b.beat_id) for b in knowledge.beats]
    assert ("move", "beat-m1") in kinds_and_ids
    assert ("move", "beat-m2") not in kinds_and_ids


def test_report_populated_with_counts():
    place = Place(place_id="p1", name="Place", lat=1.0, lon=1.0)
    seg = TimelineSegment(
        seg_id="s1", kind="visit", start=_dt(2024, 5, 1, 8, 0), end=_dt(2024, 5, 1, 10, 0),
        place=place,
    )
    timeline = Timeline(segments=[seg], track=[])
    photos = [_photo("p1photo", taken_utc=_dt(2024, 5, 1, 9, 0), camera_key="cam1")]

    knowledge = join_trip(timeline=timeline, photos=photos)
    report = knowledge.report

    assert report.photos_total == 1
    assert report.photos_dated == 1
    assert report.photos_located == 1
    assert report.by_confidence.get("visit") == 1
    assert report.by_location_source.get("timeline") == 1
    assert "cam1" in report.cameras


def test_all_datetime_comparisons_are_tz_aware_no_crash():
    # A mix of assumed-timezone fallback and a track with tz-aware points —
    # exercising the full join must not raise on naive/aware comparisons.
    track = [
        TrackPoint(ts=_dt(2024, 5, 1, 6, 0), lat=38.0, lon=-9.0),
        TrackPoint(ts=_dt(2024, 5, 1, 6, 30), lat=38.1, lon=-9.0),
    ]
    timeline = Timeline(segments=[], track=track)
    photo_no_wall_clock = _photo("nowall", camera_key="cam1")
    photo_assumed = _photo(
        "assumed1", taken_local_naive=datetime(2024, 5, 1, 6, 15), camera_key="cam2"
    )

    knowledge = join_trip(timeline=timeline, photos=[photo_no_wall_clock, photo_assumed])

    assert knowledge is not None
    assert knowledge.report.photos_total == 2
