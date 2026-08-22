"""Tests for the portable metadata manifest.

The manifest exists because photo metadata does not survive the trip from a
phone to a folder — sanitizers strip EXIF in transit and are not going away. So
the tests that matter here all take the same shape: capture from an intact
original, destroy the original's metadata the way a real sanitizer does, and
assert the pipeline still knows everything it needs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from core.ingest.content_key import content_key, file_key
from core.ingest.manifest import (
    MANIFEST_VERSION,
    PhotoEntry,
    TripManifest,
    build_manifest,
)
from core.ingest.photos import load_photos


def strip_metadata_lossless(data: bytes) -> bytes:
    """What a sanitizer does: drop every metadata segment, leave the scan alone.

    The pixels come out bit-identical and the file bytes do not — which is
    precisely the case a file hash cannot survive and a content key can.
    """
    out, i = bytearray(data[:2]), 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            out.extend(data[i:])
            break
        marker = data[i + 1]
        if marker == 0xDA:
            out.extend(data[i:])
            break
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xE1, 0xE2, 0xED, 0xEE):
            i += 2 + seg_len
            continue
        out.extend(data[i:i + 2 + seg_len])
        i += 2 + seg_len
    return bytes(out)


def write_photo(path: Path, *, taken: datetime, lat=None, lon=None, seed=0,
                make="Google", model="Pixel 8 Pro") -> Path:
    """A JPEG with distinct pixel content, real EXIF, and optional GPS."""
    img = Image.new("RGB", (64, 64), (40 + seed * 7 % 200, 90, 120))
    for x in range(64):                       # make each photo's scan unique
        img.putpixel((x, x), (255, (x * 3 + seed * 29) % 256, 0))
    exif = img.getexif()
    exif[0x010F], exif[0x0110] = make, model
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = taken.strftime("%Y:%m:%d %H:%M:%S")
    ifd[0x9011] = "+01:00"
    if lat is not None:
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = "N", tuple(IFDRational(*r) for r in lat)
        gps[3], gps[4] = "W", tuple(IFDRational(*r) for r in lon)
    img.save(path, "JPEG", exif=exif.tobytes(), quality=95)
    return path


LISBON_LAT = [(38, 1), (43, 1), (2028, 100)]
LISBON_LON = [(9, 1), (8, 1), (2148, 100)]


@pytest.fixture
def originals(tmp_path) -> Path:
    d = tmp_path / "originals"
    d.mkdir()
    write_photo(d / "a.jpg", taken=datetime(2023, 5, 4, 10, 15),
                lat=LISBON_LAT, lon=LISBON_LON, seed=1)
    write_photo(d / "b.jpg", taken=datetime(2023, 5, 4, 14, 30),
                lat=[(38, 1), (43, 1), (2100, 100)], lon=[(9, 1), (8, 1), (2200, 100)],
                seed=2)
    return d


@pytest.fixture
def sanitized(originals, tmp_path) -> Path:
    d = tmp_path / "shared"
    d.mkdir()
    for f in sorted(originals.glob("*.jpg")):
        (d / f.name).write_bytes(strip_metadata_lossless(f.read_bytes()))
    return d


class TestContentKey:
    def test_survives_a_metadata_strip(self, originals, sanitized):
        for name in ("a.jpg", "b.jpg"):
            before, method = content_key(originals / name)
            after, _ = content_key(sanitized / name)
            assert method == "scan"
            assert before == after, "the content key must not depend on metadata"

    def test_file_hash_does_not_survive(self, originals, sanitized):
        assert file_key(originals / "a.jpg") != file_key(sanitized / "a.jpg"), (
            "if this ever passes, the fixture stopped simulating a real sanitizer"
        )

    def test_distinct_images_have_distinct_keys(self, originals):
        assert content_key(originals / "a.jpg")[0] != content_key(originals / "b.jpg")[0]

    def test_falls_back_to_pixels_for_non_jpeg(self, tmp_path):
        png = tmp_path / "x.png"
        Image.new("RGB", (8, 8), (1, 2, 3)).save(png)
        _, method = content_key(png)
        assert method == "pixel"

    def test_a_lossy_reencode_breaks_the_key(self, originals, tmp_path):
        """Documents the boundary: re-encoding really does change the picture."""
        recoded = tmp_path / "recoded.jpg"
        with Image.open(originals / "a.jpg") as im:
            im.convert("RGB").save(recoded, "JPEG", quality=60)
        assert content_key(originals / "a.jpg")[0] != content_key(recoded)[0]


class TestRoundTrip:
    def test_metadata_survives_the_sanitizer(self, originals, sanitized, tmp_path):
        """The whole point, end to end."""
        before = {p.path.name: p for p in load_photos(originals)}
        assert all(p.lat is not None for p in before.values())

        manifest = build_manifest(list(before.values()), source_dir=originals)
        path = manifest.save(tmp_path / "trip.json")

        naked = {p.path.name: p for p in load_photos(sanitized)}
        assert all(p.lat is None and p.taken_utc is None for p in naked.values())

        restored = {p.path.name: p
                    for p in load_photos(sanitized, manifest=TripManifest.load(path))}
        for name, original in before.items():
            assert restored[name].taken_utc == original.taken_utc
            assert restored[name].lat == pytest.approx(original.lat)
            assert restored[name].lon == pytest.approx(original.lon)
            assert restored[name].camera_key == original.camera_key

    def test_each_photo_keeps_its_own_metadata(self, originals, sanitized, tmp_path):
        """Regression: a shared index once gave every photo the last entry's data."""
        manifest = build_manifest(load_photos(originals), source_dir=originals)
        path = manifest.save(tmp_path / "trip.json")
        restored = {p.path.name: p
                    for p in load_photos(sanitized, manifest=TripManifest.load(path))}
        assert restored["a.jpg"].taken_utc != restored["b.jpg"].taken_utc
        assert restored["a.jpg"].lat != restored["b.jpg"].lat

    def test_manifest_beats_intact_exif(self, originals, tmp_path):
        """Precedence: the manifest was read from the original, so it wins."""
        photos = load_photos(originals)
        manifest = build_manifest(photos, source_dir=originals)
        manifest.entries[0].taken_utc = "2001-01-01T00:00:00+00:00"
        entry_name = manifest.entries[0].filename
        path = manifest.save(tmp_path / "trip.json")

        restored = {p.path.name: p
                    for p in load_photos(originals, manifest=TripManifest.load(path))}
        assert restored[entry_name].taken_utc.year == 2001


class TestAmbiguity:
    def test_identical_images_are_not_guessed_at(self, tmp_path):
        """Two copies of one image share a content key. Attaching one photo's
        place to another is the exact failure this mechanism exists to prevent,
        so an ambiguous key must resolve to nothing."""
        d = tmp_path / "orig"
        d.mkdir()
        write_photo(d / "one.jpg", taken=datetime(2023, 5, 4, 10, 0),
                    lat=LISBON_LAT, lon=LISBON_LON, seed=5)
        (d / "two.jpg").write_bytes((d / "one.jpg").read_bytes())

        manifest = build_manifest(load_photos(d), source_dir=d)
        assert len(manifest.entries) == 2
        assert manifest.entries[0].content_hash == manifest.entries[1].content_hash

        renamed = tmp_path / "renamed.jpg"
        renamed.write_bytes(strip_metadata_lossless((d / "one.jpg").read_bytes()))
        assert manifest.match(renamed) is None, "ambiguous key must not guess"

    def test_identical_images_disambiguate_by_filename(self, tmp_path):
        d = tmp_path / "orig"
        d.mkdir()
        write_photo(d / "one.jpg", taken=datetime(2023, 5, 4, 10, 0), seed=5)
        (d / "two.jpg").write_bytes((d / "one.jpg").read_bytes())
        manifest = build_manifest(load_photos(d), source_dir=d)

        shared = tmp_path / "two.jpg"
        shared.write_bytes(strip_metadata_lossless((d / "two.jpg").read_bytes()))
        assert manifest.match(shared).filename == "two.jpg"

    def test_unknown_photo_matches_nothing(self, originals, tmp_path):
        manifest = build_manifest(load_photos(originals), source_dir=originals)
        other = write_photo(tmp_path / "stranger.jpg",
                            taken=datetime(2024, 1, 1, 9, 0), seed=99)
        assert manifest.match(other) is None


class TestRedaction:
    def test_coarse_rounds_coordinates(self, originals):
        manifest = build_manifest(load_photos(originals), source_dir=originals,
                                  location="coarse", coarse_places=2)
        assert manifest.location_policy == "coarse:2"
        entry = manifest.entries[0]
        assert entry.lat == pytest.approx(38.72, abs=1e-9)
        assert entry.location_precision == 2

    def test_none_omits_coordinates_entirely(self, originals, tmp_path):
        manifest = build_manifest(load_photos(originals), source_dir=originals,
                                  location="none")
        assert all(e.lat is None and e.lon is None for e in manifest.entries)
        raw = json.loads(manifest.save(tmp_path / "t.json").read_text())
        assert "38.7" not in json.dumps(raw), "a redacted manifest must not carry the value"

    def test_redaction_still_carries_time_and_camera(self, originals):
        manifest = build_manifest(load_photos(originals), source_dir=originals,
                                  location="none")
        assert all(e.taken_utc for e in manifest.entries)
        assert all(e.camera_key != "unknown" for e in manifest.entries)


class TestPersistence:
    def test_save_load_round_trip(self, originals, tmp_path):
        manifest = build_manifest(load_photos(originals), source_dir=originals)
        loaded = TripManifest.load(manifest.save(tmp_path / "t.json"))
        assert loaded.version == MANIFEST_VERSION
        assert len(loaded.entries) == len(manifest.entries)
        assert loaded.entries[0].content_hash == manifest.entries[0].content_hash

    def test_a_newer_manifest_is_refused_not_guessed_at(self, tmp_path):
        path = tmp_path / "future.json"
        path.write_text(json.dumps({"version": MANIFEST_VERSION + 1, "entries": []}))
        with pytest.raises(ValueError, match="newer version"):
            TripManifest.load(path)

    def test_entries_survive_json_faithfully(self, tmp_path):
        m = TripManifest(entries=[PhotoEntry(content_hash="abc", filename="x.jpg",
                                             lat=1.5, lon=-2.5, camera_key="A/B")])
        loaded = TripManifest.load(m.save(tmp_path / "t.json"))
        assert loaded.entries[0].lat == 1.5
        assert loaded.entries[0].camera_key == "A/B"


class TestCli:
    def test_extract_writes_a_manifest(self, originals):
        from cli import main
        from click.testing import CliRunner

        result = CliRunner().invoke(main, ["timeline", "extract", str(originals)])
        assert result.exit_code == 0, result.output
        written = originals / "trip-manifest.json"
        assert written.exists()
        assert "Captured 2 photos" in result.output
        assert TripManifest.load(written).entries

    def test_extract_honors_redaction(self, originals, tmp_path):
        from cli import main
        from click.testing import CliRunner

        out = tmp_path / "redacted.json"
        result = CliRunner().invoke(
            main, ["timeline", "extract", str(originals), "-o", str(out),
                   "--location", "none"])
        assert result.exit_code == 0, result.output
        assert all(e.lat is None for e in TripManifest.load(out).entries)

    def test_extract_warns_when_nothing_has_coordinates(self, tmp_path):
        from cli import main
        from click.testing import CliRunner

        d = tmp_path / "nogps"
        d.mkdir()
        write_photo(d / "a.jpg", taken=datetime(2023, 5, 4, 10, 0), seed=3)
        result = CliRunner().invoke(main, ["timeline", "extract", str(d)])
        assert result.exit_code == 0, result.output
        assert "No coordinates found" in result.output

    def test_extract_refuses_an_empty_folder(self, tmp_path):
        from cli import main
        from click.testing import CliRunner

        empty = tmp_path / "empty"
        empty.mkdir()
        result = CliRunner().invoke(main, ["timeline", "extract", str(empty)])
        assert result.exit_code != 0
        assert "No readable images" in result.output
