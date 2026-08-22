"""Regression tests for the review findings on PR #27.

Each test here failed before its fix. Kept as a group because they share a
theme: every one is a case where the pipeline quietly produced a wrong answer
rather than no answer — a manifest missing the coordinates it advertised, a
photo matched to a stranger's metadata, a date filter that did not filter, a
photo counted in two beats at once.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

from core.ingest.manifest import TripManifest, build_manifest
from core.ingest.models import (
    LocationSource,
    Photo,
    Place,
    Timeline,
    TimelineSegment,
    TrackPoint,
    TzSource,
)
from core.ingest.photos import load_photos
from core.ingest.trip_join import join_trip

UTC = timezone.utc


def _jpeg(path: Path, size=(64, 64), seed=0) -> Path:
    img = Image.new("RGB", size, (30, 60, 90))
    for x in range(min(size)):
        img.putpixel((x, x), (255, (x * 7 + seed * 31) % 256, 0))
    img.save(path, "JPEG", quality=95)
    return path


def _takeout_photo(d: Path, name: str, *, epoch: int, lat: float, lon: float, seed=0):
    """A photo whose only location lives in a Takeout sidecar, not in EXIF."""
    _jpeg(d / name, seed=seed)
    (d / f"{name}.json").write_text(json.dumps({
        "title": name,
        "photoTakenTime": {"timestamp": str(epoch)},
        "geoData": {"latitude": lat, "longitude": lon, "altitude": 0.0},
    }))
    return d / name


class TestSidecarCoordinatesReachTheManifest:
    """P1: a Takeout photo's coordinates arrive via geoData, not EXIF. Writing
    only the EXIF fields produced a manifest with no location for the single
    most common Takeout input — while advertising itself as the portable source
    of truth."""

    def test_manifest_captures_sidecar_coordinates(self, tmp_path):
        d = tmp_path / "takeout"
        d.mkdir()
        _takeout_photo(d, "a.jpg", epoch=1683191553, lat=38.7223, lon=-9.1393)

        photo = load_photos(d)[0]
        assert photo.lat == pytest.approx(38.7223)
        assert photo.location_source == LocationSource.SIDECAR
        assert photo.exif_lat is None, "fixture must have no EXIF GPS"

        entry = build_manifest([photo], source_dir=d).entries[0]
        assert entry.lat == pytest.approx(38.7223), (
            "the manifest dropped the only coordinates this photo had"
        )
        assert entry.lon == pytest.approx(-9.1393)

    def test_sidecar_coordinates_restore_without_the_sidecar(self, tmp_path):
        """The scenario the manifest exists for: photo copied away, sidecar left."""
        src = tmp_path / "takeout"
        src.mkdir()
        _takeout_photo(src, "a.jpg", epoch=1683191553, lat=38.7223, lon=-9.1393)
        manifest = build_manifest(load_photos(src), source_dir=src)

        bare = tmp_path / "copied"
        bare.mkdir()
        (bare / "a.jpg").write_bytes((src / "a.jpg").read_bytes())
        assert load_photos(bare)[0].lat is None

        restored = load_photos(bare, manifest=manifest)[0]
        assert restored.lat == pytest.approx(38.7223)
        assert restored.lon == pytest.approx(-9.1393)

    def test_redaction_still_applies_to_sidecar_coordinates(self, tmp_path):
        d = tmp_path / "takeout"
        d.mkdir()
        _takeout_photo(d, "a.jpg", epoch=1683191553, lat=38.7223, lon=-9.1393)
        photos = load_photos(d)

        coarse = build_manifest(photos, source_dir=d, location="coarse", coarse_places=2)
        assert coarse.entries[0].lat == pytest.approx(38.72, abs=1e-9)

        none = build_manifest(photos, source_dir=d, location="none")
        assert none.entries[0].lat is None


class TestFilenameFallbackChecksDimensions:
    """P1: a lone entry with a matching basename was accepted outright. Point a
    manifest at an unrelated folder holding an `IMG_0001.jpg` and it would
    inherit a stranger's time, place and camera."""

    def test_same_name_different_photo_is_not_matched(self, tmp_path):
        src = tmp_path / "orig"
        src.mkdir()
        _jpeg(src / "IMG_0001.jpg", size=(64, 64), seed=1)
        manifest = build_manifest(load_photos(src), source_dir=src)

        other = tmp_path / "unrelated"
        other.mkdir()
        _jpeg(other / "IMG_0001.jpg", size=(48, 32), seed=99)   # same name, different image

        assert manifest.match(other / "IMG_0001.jpg") is None, (
            "a filename alone must not be enough to inherit another photo's metadata"
        )

    def test_same_name_same_dimensions_still_matches(self, tmp_path):
        """The fallback must keep working for a genuinely re-encoded copy."""
        src = tmp_path / "orig"
        src.mkdir()
        _jpeg(src / "IMG_0001.jpg", size=(64, 64), seed=1)
        manifest = build_manifest(load_photos(src), source_dir=src)

        copied = tmp_path / "copy"
        copied.mkdir()
        with Image.open(src / "IMG_0001.jpg") as im:
            im.save(copied / "IMG_0001.jpg", "JPEG", quality=40)   # breaks both hashes

        matched = manifest.match(copied / "IMG_0001.jpg")
        assert matched is not None and matched.filename == "IMG_0001.jpg"


class TestDateRangeFiltersUnresolvedPhotos:
    """P2: EXIF-only photos have taken_utc None until the join resolves them, so
    the range filter kept every one of them — the normal case for a plain photo
    folder."""

    def _timeline(self) -> Timeline:
        pts = [TrackPoint(datetime(2023, 5, d, 12, tzinfo=UTC), 38.72, -9.14)
               for d in (4, 10)]
        return Timeline(track=pts)

    def _photo(self, name: str, wall: datetime) -> Photo:
        return Photo(photo_id=name, path=Path(name), taken_local_naive=wall,
                     camera_key="Cam/A")

    def test_out_of_range_photos_are_excluded(self):
        photos = [self._photo("in.jpg", datetime(2023, 5, 4, 12)),
                  self._photo("out.jpg", datetime(2023, 5, 10, 12))]
        trip = join_trip(
            self._timeline(), photos,
            start_after=datetime(2023, 5, 3, tzinfo=UTC),
            end_before=datetime(2023, 5, 5, tzinfo=UTC),
        )
        assert trip.report.photos_total == 1
        assert [p.photo_id for p in trip.photos] == ["in.jpg"]

    def test_no_range_keeps_everything(self):
        photos = [self._photo("a.jpg", datetime(2023, 5, 4, 12)),
                  self._photo("b.jpg", datetime(2023, 5, 10, 12))]
        assert join_trip(self._timeline(), photos).report.photos_total == 2


class TestBoundaryPhotoBelongsToOneBeat:
    """P2: adjacent segments share an instant when one ends exactly as the next
    begins — which the fixtures do, because that is how Google writes them. An
    inclusive test on both ends put the same photo in two beats, inflating
    counts and salience."""

    def test_photo_on_a_shared_boundary_is_not_double_counted(self):
        a = Place(place_id="a", name="Belém", lat=38.71, lon=-9.15)
        b = Place(place_id="b", name="Sintra", lat=38.79, lon=-9.39)
        boundary = datetime(2023, 5, 6, 9, 10, tzinfo=UTC)
        timeline = Timeline(
            segments=[
                TimelineSegment("s1", "visit", datetime(2023, 5, 6, 8, tzinfo=UTC),
                                boundary, place=a),
                TimelineSegment("s2", "visit", boundary,
                                datetime(2023, 5, 6, 18, tzinfo=UTC), place=b),
            ],
            track=[TrackPoint(datetime(2023, 5, 6, 8, tzinfo=UTC), 38.71, -9.15),
                   TrackPoint(datetime(2023, 5, 6, 18, tzinfo=UTC), 38.79, -9.39)],
        )
        photo = Photo(photo_id="edge", path=Path("edge.jpg"), taken_utc=boundary,
                      tz_offset_source=TzSource.SIDECAR, camera_key="Cam/A")

        trip = join_trip(timeline, [photo])
        placements = sum(len(b.photos) for b in trip.beats)
        assert placements == 1, (
            f"photo landed in {placements} beats; one photo belongs to one beat"
        )


class TestJsonOutputStaysMachineReadable:
    """P2: the manifest diagnostic printed before the JSON payload, so stdout
    stopped being parseable exactly when a machine was reading it."""

    @pytest.fixture
    def setup(self, tmp_path):
        photos = tmp_path / "photos"
        photos.mkdir()
        _takeout_photo(photos, "a.jpg", epoch=1683191553, lat=38.7223, lon=-9.1393)
        manifest_path = build_manifest(load_photos(photos), source_dir=photos).save(
            tmp_path / "trip.json")
        return photos, manifest_path

    def test_json_mode_emits_only_json(self, setup):
        from cli import main
        photos, manifest_path = setup
        result = CliRunner().invoke(main, [
            "timeline", "inspect", "--photos", str(photos),
            "--manifest", str(manifest_path), "--json",
        ])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)          # raises if diagnostics leaked
        assert payload["photos"] == 1

    def test_manifest_details_appear_inside_the_json(self, setup):
        from cli import main
        photos, manifest_path = setup
        result = CliRunner().invoke(main, [
            "timeline", "inspect", "--photos", str(photos),
            "--manifest", str(manifest_path), "--json",
        ])
        payload = json.loads(result.output)
        assert payload["manifest"]["entries"] == 1
        assert payload["manifest"]["matched"] == 1

    def test_human_mode_still_reports_the_manifest(self, setup):
        from cli import main
        photos, manifest_path = setup
        result = CliRunner().invoke(main, [
            "timeline", "inspect", "--photos", str(photos),
            "--manifest", str(manifest_path),
        ])
        assert result.exit_code == 0, result.output
        assert "manifest:" in result.output
