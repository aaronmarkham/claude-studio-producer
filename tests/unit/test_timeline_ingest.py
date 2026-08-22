"""Unit tests for core.ingest.timeline (Component 1: Timeline Ingestion).

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.ingest.timeline import parse_coord, parse_timeline, parse_timestamp

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "timeline"

# The three positions encoded (in each format's native shape) across the
# four fixtures. Used to assert format-equivalence.
LISBON = (38.7223, -9.1393)
PORTO = (41.1579, -8.6291)
SINTRA = (38.8029, -9.3817)
EXPECTED_POSITIONS = [LISBON, PORTO, SINTRA]
EXPECTED_TIMESTAMPS = [
    datetime(2023, 5, 4, 9, 12, 33, tzinfo=timezone.utc),
    datetime(2023, 5, 5, 10, 0, 0, tzinfo=timezone.utc),
    datetime(2023, 5, 6, 11, 30, 0, tzinfo=timezone.utc),
]


def _write(tmp_path: Path, name: str, data) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestFormatDetection:
    def test_records_format(self):
        tl = parse_timeline(FIXTURES / "records.json")
        assert tl.source_format == "records"
        assert len(tl.track) == 3

    def test_semantic_format(self):
        tl = parse_timeline(FIXTURES / "semantic.json")
        assert tl.source_format == "semantic"
        assert len(tl.track) == 3
        assert len(tl.segments) == 3

    def test_wrapped_format(self):
        tl = parse_timeline(FIXTURES / "wrapped.json")
        assert tl.source_format == "wrapped"
        assert len(tl.track) == 3
        assert len(tl.segments) == 3

    def test_bare_format(self):
        tl = parse_timeline(FIXTURES / "bare.json")
        assert tl.source_format == "bare"
        assert len(tl.track) == 3
        assert len(tl.segments) == 3


class TestFormatEquivalence:
    """All four formats encode the same three positions/timestamps and must
    normalize to identical track output."""

    @pytest.mark.parametrize("fixture", ["records.json", "semantic.json", "wrapped.json", "bare.json"])
    def test_track_matches_expected_positions(self, fixture):
        tl = parse_timeline(FIXTURES / fixture)
        assert len(tl.track) == 3
        for point, (exp_lat, exp_lon), exp_ts in zip(tl.track, EXPECTED_POSITIONS, EXPECTED_TIMESTAMPS):
            assert round(point.lat, 6) == round(exp_lat, 6)
            assert round(point.lon, 6) == round(exp_lon, 6)
            assert point.ts == exp_ts

    def test_all_formats_agree_with_each_other(self):
        tracks = [
            parse_timeline(FIXTURES / fixture).track
            for fixture in ("records.json", "semantic.json", "wrapped.json", "bare.json")
        ]
        reference = tracks[0]
        for other in tracks[1:]:
            assert len(other) == len(reference)
            for p_ref, p_other in zip(reference, other):
                assert round(p_ref.lat, 6) == round(p_other.lat, 6)
                assert round(p_ref.lon, 6) == round(p_other.lon, 6)
                assert p_ref.ts == p_other.ts


class TestCoordinateEncodings:
    """Every coordinate shape Google has shipped must normalize to the same float."""

    def test_all_encodings_produce_identical_floats(self):
        e7 = parse_coord({"latitudeE7": 386820000, "longitudeE7": -91393000})
        geo_uri = parse_coord("geo:38.682,-9.1393")
        degree_string = parse_coord("38.682°, -9.1393°")
        lat_lng_wrapped = parse_coord({"latLng": "38.682°, -9.1393°"})
        lat_lon_object = parse_coord({"latitude": 38.682, "longitude": -9.1393})

        results = [e7, geo_uri, degree_string, lat_lng_wrapped, lat_lon_object]
        assert all(r is not None for r in results)
        for lat, lon in results:
            assert round(lat, 6) == round(38.682, 6)
            assert round(lon, 6) == round(-9.1393, 6)

    def test_unparseable_coordinate_returns_none(self):
        assert parse_coord("not a coordinate") is None
        assert parse_coord({"foo": "bar"}) is None
        assert parse_coord(None) is None
        assert parse_coord(12345) is None


class TestTimestampParsing:
    def test_returns_tz_aware_utc(self):
        dt = parse_timestamp("2023-05-04T09:12:33Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)

    def test_handles_fractional_seconds(self):
        dt = parse_timestamp("2023-05-04T09:12:33.123456Z")
        assert dt == datetime(2023, 5, 4, 9, 12, 33, 123456, tzinfo=timezone.utc)

    def test_handles_offset_without_colon(self):
        dt = parse_timestamp("2023-05-04T09:12:33+0100")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime(2023, 5, 4, 8, 12, 33, tzinfo=timezone.utc)

    def test_handles_legacy_timestamp_ms_string(self):
        dt = parse_timestamp("1683191553000")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime.fromtimestamp(1683191553, tz=timezone.utc)

    def test_unparseable_timestamp_returns_none(self):
        assert parse_timestamp("not a date") is None
        assert parse_timestamp(None) is None

    def test_no_track_point_is_naive(self):
        for fixture in ("records.json", "semantic.json", "wrapped.json", "bare.json"):
            tl = parse_timeline(FIXTURES / fixture)
            for point in tl.track:
                assert point.ts.tzinfo is not None
                assert point.ts.utcoffset() == timedelta(0)


class TestAccuracyFilter:
    def test_low_accuracy_point_is_dropped(self, tmp_path):
        data = {
            "locations": [
                {"latitudeE7": 387223000, "longitudeE7": -91393000, "timestamp": "2023-05-04T09:00:00Z", "accuracy": 10},
                {"latitudeE7": 387224000, "longitudeE7": -91394000, "timestamp": "2023-05-04T09:01:00Z", "accuracy": 3000},
            ]
        }
        path = _write(tmp_path, "records.json", data)
        tl = parse_timeline(path, max_accuracy_m=2000)
        assert tl.stats.dropped_accuracy == 1
        assert len(tl.track) == 1
        assert tl.track[0].accuracy_m == 10


class TestTeleportFilter:
    def test_teleport_without_activity_is_dropped(self, tmp_path):
        # Lisbon -> Tokyo in 60 seconds, as plain (non-activity) records.
        data = {
            "locations": [
                {"latitudeE7": 387223000, "longitudeE7": -91393000, "timestamp": "2023-05-04T09:00:00Z", "accuracy": 10},
                {"latitudeE7": 356762000, "longitudeE7": 1396503000, "timestamp": "2023-05-04T09:01:00Z", "accuracy": 10},
            ]
        }
        path = _write(tmp_path, "records.json", data)
        tl = parse_timeline(path)
        assert tl.stats.dropped_speed == 1
        assert len(tl.track) == 1
        assert round(tl.track[0].lat, 4) == round(38.7223, 4)

    def test_teleport_inside_flying_activity_is_kept(self, tmp_path):
        # Same jump, but as an activitySegment with activityType "FLYING".
        data = {
            "timelineObjects": [
                {
                    "activitySegment": {
                        "startLocation": {"latitudeE7": 387223000, "longitudeE7": -91393000},
                        "endLocation": {"latitudeE7": 356762000, "longitudeE7": 1396503000},
                        "activityType": "FLYING",
                        "distance": 11000000,
                        "duration": {
                            "startTimestamp": "2023-05-04T09:00:00Z",
                            "endTimestamp": "2023-05-04T09:01:00Z",
                        },
                    }
                }
            ]
        }
        path = _write(tmp_path, "semantic.json", data)
        tl = parse_timeline(path)
        assert tl.stats.dropped_speed == 0
        assert len(tl.track) == 2
        assert tl.segments[0].activity == "flying"


class TestStationaryCollapse:
    def test_fifty_stationary_points_collapse_to_one(self, tmp_path):
        base = datetime(2023, 5, 4, 9, 0, 0, tzinfo=timezone.utc)
        locations = [
            {
                "latitudeE7": 387223000,
                "longitudeE7": -91393000,
                "timestamp": (base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "accuracy": 10,
            }
            for i in range(50)
        ]
        path = _write(tmp_path, "records.json", {"locations": locations})
        tl = parse_timeline(path)
        assert len(tl.track) == 1
        assert tl.stats.collapsed_stationary == 49
        assert tl.stats.points_out == 1


class TestUnparseableCoordinates:
    def test_bad_location_increments_unparseable_without_raising(self, tmp_path):
        data = {
            "locations": [
                {"latitudeE7": 387223000, "longitudeE7": -91393000, "timestamp": "2023-05-04T09:00:00Z", "accuracy": 10},
                {"latitude": "garbage", "timestamp": "2023-05-04T09:01:00Z", "accuracy": 10},
            ]
        }
        path = _write(tmp_path, "records.json", data)
        tl = parse_timeline(path)
        assert tl.stats.unparseable == 1
        assert len(tl.track) == 1


class TestDirectoryWalk:
    def test_walks_takeout_directory_for_records_file(self, tmp_path):
        loc_dir = tmp_path / "Takeout" / "Location History"
        loc_dir.mkdir(parents=True)
        data = json.loads((FIXTURES / "records.json").read_text(encoding="utf-8"))
        (loc_dir / "Records.json").write_text(json.dumps(data), encoding="utf-8")
        tl = parse_timeline(tmp_path)
        assert tl.source_format == "records"
        assert len(tl.track) == 3

    def test_walks_semantic_location_history_subdirectory(self, tmp_path):
        sem_dir = tmp_path / "Takeout" / "Location History" / "Semantic Location History" / "2023"
        sem_dir.mkdir(parents=True)
        data = json.loads((FIXTURES / "semantic.json").read_text(encoding="utf-8"))
        (sem_dir / "2023_MAY.json").write_text(json.dumps(data), encoding="utf-8")
        tl = parse_timeline(tmp_path)
        assert tl.source_format == "semantic"
        assert len(tl.track) == 3
