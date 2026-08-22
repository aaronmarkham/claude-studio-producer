"""Generates the fixture tree consumed by tests/unit/test_photo_ingest.py.

Run directly to (re)build `tests/fixtures/photos/data/`:

    python3 tests/fixtures/photos/make_fixtures.py

The generated files are tiny (mostly 16x16) JPEGs plus their Takeout JSON sidecars,
so they're cheap to commit. Regenerating is deterministic — running this twice
produces byte-identical output — which is what lets the "identical bytes -> same
photo_id" test rely on `hashes/duplicate.jpg` matching `hashes/original.jpg` exactly.

Layout:

    data/sidecars/    -- one pair per resolve_sidecar() naming variant, plus a
                          sidecar-priority and a zero-geoData case
    data/exif/         -- EXIF-only metadata (no sidecar): offsets, GPS hemispheres
    data/cameras/      -- camera_key / cluster_by_camera / credits fixtures
    data/screenshots/  -- screenshot heuristic (aspect ratio) fixtures
    data/hashes/       -- photo_id stability fixtures

Constants below are re-declared (not imported) in the test module, so the test
module has no import-time dependency on this script — it only needs the files it
produces to already be on disk.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PIL.ExifTags import Base
from PIL.TiffImagePlugin import IFDRational

FIXTURES_ROOT = Path(__file__).parent / "data"

# --------------------------------------------------------------------------- #
# Shared constants (also asserted against in the test module — keep in sync)
# --------------------------------------------------------------------------- #

SIDECAR_TIMESTAMP = 1683191553          # -> 2023-05-04T05:12:33Z
SIDECAR_LAT = 38.682
SIDECAR_LON = -122.395

EXIF_LOCAL_DATETIME = "2023:06:15 14:30:00"   # naive wall clock
EXIF_OFFSET_PLUS = "+02:00"                    # -> 2023-06-15T12:30:00Z
EXIF_OFFSET_MINUS = "-05:00"                   # -> 2023-06-15T19:30:00Z

# 38 39' 6" N, 122 23' 42" W  (Point Reyes-ish, decimal ~38.6517, -122.395)
GPS_DEG_LAT, GPS_MIN_LAT, GPS_SEC_LAT = 38, 39, 6.0
GPS_DEG_LON, GPS_MIN_LON, GPS_SEC_LON = 122, 23, 42.0


def _rational_dms(deg: float, minutes: float, seconds: float):
    return (
        IFDRational(int(deg), 1),
        IFDRational(int(minutes), 1),
        IFDRational(int(seconds * 100), 100),
    )


def _save(
    path: Path,
    *,
    size=(16, 16),
    color=(120, 140, 160),
    make=None,
    model=None,
    serial=None,
    date_time_original=None,
    offset_time_original=None,
    gps_lat_ref=None,
    gps_lat=None,
    gps_lon_ref=None,
    gps_lon=None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=color)

    has_exif = any(
        v is not None
        for v in (make, model, serial, date_time_original, offset_time_original, gps_lat)
    )
    exif_bytes = None
    if has_exif:
        exif = img.getexif()
        if make is not None:
            exif[Base.Make] = make
        if model is not None:
            exif[Base.Model] = model
        if serial is not None:
            exif[Base.BodySerialNumber] = serial

        if date_time_original is not None or offset_time_original is not None:
            sub_ifd = exif.get_ifd(0x8769)
            if date_time_original is not None:
                sub_ifd[36867] = date_time_original
            if offset_time_original is not None:
                sub_ifd[36881] = offset_time_original

        if gps_lat is not None:
            gps_ifd = exif.get_ifd(0x8825)
            gps_ifd[1] = gps_lat_ref
            gps_ifd[2] = _rational_dms(*gps_lat)
            gps_ifd[3] = gps_lon_ref
            gps_ifd[4] = _rational_dms(*gps_lon)

        exif_bytes = exif.tobytes()

    if exif_bytes:
        img.save(path, format="JPEG", exif=exif_bytes)
    else:
        img.save(path, format="JPEG")


def _write_sidecar(path: Path, *, timestamp, lat=None, lon=None, title=None) -> None:
    import json

    geo = {"latitude": lat if lat is not None else 0.0,
           "longitude": lon if lon is not None else 0.0,
           "altitude": 0.0}
    payload = {
        "title": title or path.name,
        "photoTakenTime": {
            "timestamp": str(timestamp),
            "formatted": "irrelevant to the ingester, kept for realism",
        },
        "geoData": geo,
        "geoDataExif": geo,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def build() -> None:
    sidecars = FIXTURES_ROOT / "sidecars"
    exif_dir = FIXTURES_ROOT / "exif"
    cameras = FIXTURES_ROOT / "cameras"
    screenshots = FIXTURES_ROOT / "screenshots"
    hashes = FIXTURES_ROOT / "hashes"

    # --- sidecars: resolve_sidecar() naming variants + priority + zero-geo ---

    # 1. Exact: IMG_4471.jpg.json
    _save(sidecars / "IMG_4471.jpg", color=(10, 20, 30))
    _write_sidecar(sidecars / "IMG_4471.jpg.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=SIDECAR_LAT, lon=SIDECAR_LON)

    # 2. Supplemental metadata: IMG_4472.jpg.supplemental-metadata.json
    _save(sidecars / "IMG_4472.jpg", color=(11, 21, 31))
    _write_sidecar(sidecars / "IMG_4472.jpg.supplemental-metadata.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=SIDECAR_LAT, lon=SIDECAR_LON)

    # 3. Truncated: IMG_4473.jp.json for IMG_4473.jpg
    _save(sidecars / "IMG_4473.jpg", color=(12, 22, 32))
    _write_sidecar(sidecars / "IMG_4473.jp.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=SIDECAR_LAT, lon=SIDECAR_LON)

    # 4. Duplicate-suffixed: IMG_4474(1).jpg.json for IMG_4474(1).jpg
    _save(sidecars / "IMG_4474(1).jpg", color=(13, 23, 33))
    _write_sidecar(sidecars / "IMG_4474(1).jpg.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=SIDECAR_LAT, lon=SIDECAR_LON)

    # 5. Case-mismatched extension: IMG_4475.HEIC.json for img_4475.heic
    #    (content sniffs as JPEG regardless of the .heic filename — Pillow reads by
    #    magic bytes, not extension, so this stays a decodable fixture).
    _save(sidecars / "img_4475.heic", color=(14, 24, 34))
    _write_sidecar(sidecars / "IMG_4475.HEIC.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=SIDECAR_LAT, lon=SIDECAR_LON)

    # 6. geoData exactly 0.0/0.0 must be treated as absent, not as a real fix.
    _save(sidecars / "IMG_4476_zerogeo.jpg", color=(15, 25, 35))
    _write_sidecar(sidecars / "IMG_4476_zerogeo.jpg.json",
                    timestamp=SIDECAR_TIMESTAMP, lat=None, lon=None)

    # --- exif: no sidecar present, metadata comes solely from EXIF ---

    _save(exif_dir / "exif_only.jpg", date_time_original=EXIF_LOCAL_DATETIME)

    _save(
        exif_dir / "exif_offset_plus.jpg",
        date_time_original=EXIF_LOCAL_DATETIME,
        offset_time_original=EXIF_OFFSET_PLUS,
    )
    _save(
        exif_dir / "exif_offset_minus.jpg",
        date_time_original=EXIF_LOCAL_DATETIME,
        offset_time_original=EXIF_OFFSET_MINUS,
    )

    _save(
        exif_dir / "gps_south_west.jpg",
        gps_lat_ref="S", gps_lat=(GPS_DEG_LAT, GPS_MIN_LAT, GPS_SEC_LAT),
        gps_lon_ref="W", gps_lon=(GPS_DEG_LON, GPS_MIN_LON, GPS_SEC_LON),
    )
    _save(
        exif_dir / "gps_north_east.jpg",
        gps_lat_ref="N", gps_lat=(GPS_DEG_LAT, GPS_MIN_LAT, GPS_SEC_LAT),
        gps_lon_ref="E", gps_lon=(GPS_DEG_LON, GPS_MIN_LON, GPS_SEC_LON),
    )

    # --- cameras: camera_key / cluster_by_camera / credits ---

    _save(cameras / "apple_a.jpg", make="Apple", model="iPhone 14 Pro", serial="ABC123")
    _save(cameras / "apple_b.jpg", make="Apple", model="iPhone 14 Pro", serial="ABC123")
    _save(cameras / "apple_noserial_a.jpg", make="Apple", model="iPhone 12")
    _save(cameras / "apple_noserial_b.jpg", make="Apple", model="iPhone 12")
    _save(cameras / "canon_a.jpg", make="Canon", model="EOS R6", serial="XYZ999")
    _save(cameras / "no_camera.jpg")  # no EXIF at all -> "unknown"

    # --- screenshots: aspect-ratio heuristic ---

    _save(screenshots / "screenshot.jpg", size=(108, 192))       # 9:16, no EXIF
    _save(screenshots / "not_screenshot.jpg", size=(16, 16))     # 1:1, no EXIF

    # --- hashes: photo_id stability ---

    _save(hashes / "original.jpg", color=(200, 100, 50))
    _save(hashes / "duplicate.jpg", color=(200, 100, 50))  # byte-identical content
    _save(hashes / "different.jpg", color=(50, 100, 200))


if __name__ == "__main__":
    build()
    print(f"Wrote fixtures under {FIXTURES_ROOT}")
