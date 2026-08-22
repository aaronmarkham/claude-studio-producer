"""End-to-end integration for personal-media ingestion.

The three ingestion modules were built independently against the shared model
contract, so each one's unit tests prove only that it honors that contract in
isolation. This file exercises the seam between them: a real Timeline export
parsed by `timeline.py`, real JPEGs with real EXIF read by `photos.py`, joined
by `trip_join.py`, and finally rendered through the actual CLI.

The bug class this exists to catch is the one unit tests structurally cannot:
two modules that each pass their own tests while disagreeing about what they
hand each other.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

from core.ingest.models import LocationSource, TrackConfidence, TzSource
from core.ingest.photos import load_photos
from core.ingest.timeline import parse_timeline
from core.ingest.trip_join import join_trip

FIXTURE = Path(__file__).parent.parent / "fixtures" / "timeline" / "trip_semantic.json"

# Matches the visits in trip_semantic.json.
ALFAMA = (38.7223, -9.1393)
SINTRA = (38.7975, -9.3906)


def _write_photo(
    path: Path,
    *,
    taken: datetime,
    make: str,
    model: str,
    serial: str | None = None,
    size: tuple[int, int] = (16, 16),
) -> Path:
    """A tiny JPEG carrying the EXIF tags the ingester actually reads."""
    img = Image.new("RGB", size, (90, 120, 110))
    exif = img.getexif()
    exif[0x010F] = make                                     # Make
    exif[0x0110] = model                                    # Model
    if serial:
        exif[0xA431] = serial                               # BodySerialNumber
    # DateTimeOriginal lives in the Exif IFD, not the root — wall-clock, no zone.
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
    img.save(path, "JPEG", exif=exif.tobytes())
    return path


@pytest.fixture
def photo_dir(tmp_path: Path) -> Path:
    """Two cameras shooting across the trip, no GPS and no sidecars.

    This is the hard case and the common one: the location has to come entirely
    from the timeline, via the timestamp.
    """
    d = tmp_path / "trip"
    d.mkdir()
    # Day 1, Alfama — the phone shoots most of the trip.
    for i, hour in enumerate([9, 10, 11, 14, 16]):
        _write_photo(d / f"IMG_{i:04d}.jpg",
                     taken=datetime(2023, 5, 4, hour, 15), make="Apple", model="iPhone 14 Pro")
    # Day 2, Belém — fewer frames.
    for i, hour in enumerate([10, 15], start=5):
        _write_photo(d / f"IMG_{i:04d}.jpg",
                     taken=datetime(2023, 5, 5, hour, 0), make="Apple", model="iPhone 14 Pro")
    # Day 3, Sintra — the second camera joins.
    for i, hour in enumerate([11, 13, 15], start=7):
        _write_photo(d / f"IMG_{i:04d}.jpg",
                     taken=datetime(2023, 5, 6, hour, 30), make="Apple", model="iPhone 14 Pro")
    for i, hour in enumerate([12, 14], start=10):
        _write_photo(d / f"DSC_{i:04d}.jpg", taken=datetime(2023, 5, 6, hour, 0),
                     make="Canon", model="EOS R6", serial="0123456789")
    return d


def _run(photo_dir: Path, credits: dict[str, str] | None = None):
    timeline = parse_timeline(FIXTURE)
    photos = load_photos(photo_dir, credits=credits or {})
    return timeline, photos, join_trip(timeline, photos, credits=credits or {})


class TestFullChain:
    def test_photos_are_located_from_the_timeline_alone(self, photo_dir):
        """The whole premise: no photo here has GPS, all of them get a place."""
        _, photos, trip = _run(photo_dir)
        assert len(photos) == 12
        assert not any(p.has_own_position for p in photos), "fixture must have no GPS"

        located = [p for p in trip.photos if p.lat is not None]
        assert len(located) == 12, "every photo should inherit a position from the timeline"
        assert all(p.location_source == LocationSource.TIMELINE for p in located)

    def test_photos_inside_a_visit_get_the_place_name(self, photo_dir):
        _, _, trip = _run(photo_dir)
        day1 = [p for p in trip.photos if p.taken_utc and p.taken_utc.day == 4]
        assert day1, "expected photos on day 1"
        assert all(p.confidence == TrackConfidence.VISIT for p in day1)
        assert {p.place_name for p in day1} == {"Alfama"}

    def test_beats_cover_the_trip_in_order(self, photo_dir):
        _, _, trip = _run(photo_dir)
        assert trip.beats, "a timeline with real durations must produce beats"
        starts = [b.start for b in trip.beats]
        assert starts == sorted(starts), "beats must be chronological"

        stays = [b for b in trip.beats if b.kind == "stay"]
        names = [b.place.name for b in stays if b.place]
        assert "Alfama" in names and "Sintra" in names

        # Every photo lands in exactly one beat — none orphaned, none double-counted.
        assigned = sum(len(b.photos) for b in trip.beats)
        assert assigned == len(trip.photos)

    def test_the_move_survives_as_its_own_beat(self, photo_dir):
        """A 28 km transfer clears the 25 km floor, so it becomes a map clip."""
        _, _, trip = _run(photo_dir)
        moves = [b for b in trip.beats if b.kind == "move"]
        assert len(moves) == 1
        assert moves[0].distance_m == pytest.approx(28400, rel=0.01)

    def test_salience_tracks_photo_count(self, photo_dir):
        _, _, trip = _run(photo_dir)
        stays = {b.place.name: b for b in trip.beats if b.kind == "stay" and b.place}
        assert stays["Alfama"].salience > stays["Belém"].salience
        assert all(0.0 <= b.salience <= 1.0 for b in trip.beats)

    def test_day_index_is_one_based_and_advances(self, photo_dir):
        _, _, trip = _run(photo_dir)
        assert min(b.day_index for b in trip.beats) == 1
        assert max(b.day_index for b in trip.beats) == 3
        assert trip.day_count == 3


class TestAttribution:
    def test_cameras_partition_the_folder(self, photo_dir):
        _, photos, _ = _run(photo_dir)
        keys = {p.camera_key for p in photos}
        assert len(keys) == 2, f"expected two cameras, got {keys}"

    def test_credits_apply_per_camera_and_never_guess(self, photo_dir):
        canon = next(k for k in {p.camera_key for p in load_photos(photo_dir)} if "EOS" in k)
        _, photos, trip = _run(photo_dir, credits={canon: "Dana"})

        credited = [p for p in trip.photos if p.credit == "Dana"]
        uncredited = [p for p in trip.photos if p.credit is None]
        assert len(credited) == 2, "only the Canon frames should be credited"
        assert len(uncredited) == 10, "the unmapped camera must stay uncredited"
        assert all("EOS" in p.camera_key for p in credited)

    def test_an_unmapped_camera_yields_no_credit(self, photo_dir):
        _, _, trip = _run(photo_dir)
        assert all(p.credit is None for p in trip.photos)


class TestReadability:
    """These assert on things only visible when the modules are composed —
    each was a real defect the per-module unit tests could not have caught."""

    def test_title_names_the_region_not_the_first_neighborhood(self, photo_dir):
        _, _, trip = _run(photo_dir)
        assert trip.title == "Portugal, May 2023"

    def test_camera_rollup_counts_and_credits(self, photo_dir):
        canon = next(k for k in {p.camera_key for p in load_photos(photo_dir)} if "EOS" in k)
        _, _, trip = _run(photo_dir, credits={canon: "Dana"})
        cams = trip.report.cameras
        assert sum(c["count"] for c in cams.values()) == 12, "every photo counted once"
        assert cams[canon]["count"] == 2
        assert cams[canon]["credit"] == "Dana"
        assert cams[canon]["span"], "a camera with dated photos gets a date span"

    def test_timezone_fallback_warns_once_not_per_photo(self, photo_dir):
        """13 identical warnings bury the one that needs a human."""
        _, _, trip = _run(photo_dir)
        assumed = [w for w in trip.report.warnings if "timezone signal" in w]
        assert len(assumed) == 1, f"expected one aggregate warning, got {trip.report.warnings}"
        assert "12 photos" in assumed[0]

    def test_move_beats_borrow_names_from_their_neighbors(self, photo_dir):
        """An activitySegment has coordinates but no names — without the
        fallback the beat renders as '? → ?'."""
        _, _, trip = _run(photo_dir)
        move = next(b for b in trip.beats if b.kind == "move")
        assert move.from_place and move.from_place.name == "Belém"
        assert move.to_place and move.to_place.name == "Sintra"


class TestJoinReport:
    def test_report_counts_reconcile(self, photo_dir):
        _, _, trip = _run(photo_dir)
        r = trip.report
        assert r.photos_total == 12
        assert r.photos_located == 12
        assert sum(r.by_confidence.values()) == r.photos_total
        # No sidecars and no OffsetTimeOriginal, so nothing resolved to real UTC.
        assert TzSource.SIDECAR.value not in r.by_tz_source

    def test_no_false_gps_disagreements(self, photo_dir):
        """Nothing here has its own GPS, so there is nothing to disagree."""
        _, _, trip = _run(photo_dir)
        assert trip.report.gps_disagreements == []


class TestCli:
    def test_inspect_renders(self, photo_dir):
        from cli import main
        result = CliRunner().invoke(
            main, ["timeline", "inspect", str(FIXTURE), "--photos", str(photo_dir)]
        )
        assert result.exit_code == 0, result.output
        assert "Join quality" in result.output
        assert "Alfama" in result.output
        assert "Beats" in result.output

    def test_inspect_json_is_machine_readable(self, photo_dir):
        from cli import main
        result = CliRunner().invoke(
            main, ["timeline", "inspect", str(FIXTURE), "--photos", str(photo_dir), "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["photos"] == 12
        assert payload["beats"] >= 3
        assert payload["report"]["photos_located"] == 12

    def test_credit_flag_is_validated(self, photo_dir):
        from cli import main
        result = CliRunner().invoke(
            main, ["timeline", "inspect", str(FIXTURE), "--credit", "no-equals-sign"]
        )
        assert result.exit_code != 0
        assert "CAMERA=NAME" in result.output

    def test_requires_some_input(self):
        from cli import main
        result = CliRunner().invoke(main, ["timeline", "inspect"])
        assert result.exit_code != 0
        assert "--photos" in result.output


class TestDegenerateInputs:
    def test_photos_only_still_produces_a_trip(self, photo_dir, tmp_path):
        """No timeline at all — the pseudo-track path."""
        photos = load_photos(photo_dir)
        trip = join_trip(None, photos)
        assert trip.report.photos_total == 12

    def test_timeline_only_still_produces_beats(self):
        timeline = parse_timeline(FIXTURE)
        trip = join_trip(timeline, [])
        assert trip.beats, "a photo-less trip should still yield beats to narrate"
        assert trip.report.photos_total == 0
