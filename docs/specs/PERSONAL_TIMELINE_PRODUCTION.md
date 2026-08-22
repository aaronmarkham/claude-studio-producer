# Personal Timeline Production

> Status: Proposed (August 22, 2026)
> Priority: Medium — opens a new source class (personal media) without disturbing the document pipeline
> Depends on: UNIFIED_PRODUCTION_ARCHITECTURE.md (StructuredScript, ContentLibrary, DoP), TRANSCRIPT_LED_VIDEO_PRODUCTION.md (budget tiers)
> Related prior art: [mahlernim/google-timeline-visualizer](https://github.com/mahlernim/google-timeline-visualizer) (MIT)
> Date: August 22, 2026

## Problem

Every source type CSP currently accepts is *documentary*: a paper, a topic to research, a
transcript, a pre-written script. The pipeline's job is to take text someone else wrote and
find visuals for it. Visual assets are therefore always **generated** (DALL-E, Luma) or
**extracted** (KB figures, Wikimedia), and the budget tiers in `core/video_production.py:660`
exist to ration that generation spend.

Personal media inverts both halves of that:

1. **The narrative structure already exists as data, not prose.** A Google Timeline export
   knows "four days in Lisbon, a flight, two days in Porto." That is a scene list with real
   durations, distances, and place names — an itinerary is an outline. There is no document
   to atomize.

2. **The visual assets already exist and cost nothing.** A folder of photos is a content
   library that has already been paid for. The scarce resource stops being dollars and starts
   being *coverage*: which moments have a photo, and which don't.

Neither fact fits the existing ingestion paths. `cs produce topic` would research the city on
the web and generate imagery of a Lisbon that isn't the one in the photos. `cs produce script`
would take a hand-written travelogue but throw away the timestamps that make the photos
placeable. There is currently no way to say "here is where I was and here is what I shot,
make a video out of it."

### Why the timestamps matter more than the coordinates

The obvious framing is "photos have GPS, plot them on a map." That framing is wrong, and
getting it wrong early would shape the whole design badly.

Only *some* photos carry GPS. Screenshots don't. Scans don't. Photos from a camera with no
GPS radio don't. Photos received from a travelling companion usually don't — messaging apps
strip EXIF. Photos taken with location services off don't. In a realistic trip folder, the
GPS-bearing fraction is often well under half.

But **every** photo carries a capture time. And a location history is a continuous function
from time to position. So the join key is the timestamp, and the timeline supplies the
location for photos that never had one. GPS, where present, becomes a *validator* rather than
the input — which is what catches the failure mode that otherwise silently ruins the output:
a camera clock set to the wrong timezone.

That inversion — time as key, location as check — is the core idea of this spec.

---

## Design

### Core Idea: The Timeline Is the Outline, the Photos Are the Library

```
Timeline export ─┐
                 ├─► TripJoin ─► TripKnowledge ─► StructuredScript ─► VisualGrammar ─► assembly
Photo folder   ──┘   (time-      (beats, places,   (segments with      (cuts, holds,    (audio,
                      indexed     photographers,     intents,            map moves,       render)
                      join)       photo clusters)    salience)           credits)
                          │                              │
                          │                              └─► DoP (which asset per segment)
                          └─► ContentLibrary (photos as pre-approved assets, cost $0)
```

Three properties fall out of this shape:

- **Ingestion is a new module, not a new pipeline.** Everything downstream of
  `StructuredScript` is untouched. The DoP, the audio producer, the assembler, the asset
  review workflow all work as they do today.
- **The join is deterministic and offline.** No LLM, no network. It is a pure function of two
  local files, which makes it exhaustively unit-testable and keeps personal data on the box
  by construction.
- **The LLM enters late and only for prose.** Claude writes narration *over* a beat structure
  that was computed from data. It is never asked to invent where someone was.

### Content model reuse

The `SegmentIntent` vocabulary from CONTENT_MODEL_EXPANSION.md was designed to be
content-agnostic, and this is the first real test of that claim. It passes — a travelogue
needs **no new intents**:

| Beat | Existing intent |
|------|-----------------|
| "This is the trip we took" | `INTRO` |
| "We landed in Lisbon on a Tuesday" | `CONTEXT` |
| "The Alfama is built on seven hills, which is why…" | `EXPLANATION` |
| "The second morning we walked to the castle" | `NARRATIVE` |
| "Then a three-hour train north" | `TRANSITION` |
| "This was the best meal of the trip" | `COMMENTARY` |
| "Looking at the map, we covered 340 km" | `DATA_WALKTHROUGH` |
| "We'd go back in a heartbeat" | `OUTRO` |

`TRANSITION` is the interesting one: in a travelogue it is not a rhetorical bridge but a
literal one — a movement between two places — and it is exactly the segment a rendered map
animation binds to (Component 6).

---

## Component 1: Timeline Ingestion

```python
# NEW — core/ingest/timeline.py
```

### Formats to support

Google has shipped at least four shapes of this data, and a user's export will contain
whichever one matches when they pulled it. All four must parse, because telling someone
"re-export your location history" is often impossible — old exports are the only copy of old
trips.

| Format | Where | Shape |
|--------|-------|-------|
| Legacy raw records | `Takeout/Location History/Records.json` | `{"locations": [{"latitudeE7": 386820000, "longitudeE7": -1223950000, "timestamp": "2023-05-04T09:12:33Z", "accuracy": 12}]}` |
| Legacy semantic | `Takeout/Location History/Semantic Location History/2023/2023_MAY.json` | `{"timelineObjects": [{"placeVisit": {...}}, {"activitySegment": {...}}]}` |
| On-device export (wrapped) | `Timeline.json`, `location-history.json` | `{"semanticSegments": [...]}` |
| On-device export (bare) | same filenames, newer | top-level `[{"startTime": ..., "endTime": ..., "visit": {...}}, ...]` |

Coordinates appear as E7 integers, `"geo:38.682,-122.395"` strings, `"38.682°, -122.395°"`
degree strings, or nested `latLng` objects. Normalize all of it at the edge; nothing
downstream should ever see a raw Google shape.

The `google-timeline-visualizer` project already handles this matrix and is MIT-licensed;
its parsing logic is worth reading as a reference for the coordinate-shape edge cases even
where we don't vendor code.

### Normalized model

```python
# core/ingest/timeline.py

class TrackConfidence(str, Enum):
    """How much to trust a position at a given instant."""
    VISIT = "visit"                 # inside a placeVisit — highest
    INTERPOLATED = "interpolated"   # between track points, gap under threshold
    INFERRED = "inferred"           # gap exceeds threshold, extrapolated
    UNKNOWN = "unknown"             # outside the track entirely


@dataclass
class TrackPoint:
    """A single normalized position fix."""
    ts: datetime                    # always tz-aware UTC
    lat: float
    lon: float
    accuracy_m: Optional[int] = None
    source: str = "record"          # record | visit | activity


@dataclass
class Place:
    """A named location the timeline says the user stopped at."""
    place_id: str                   # stable hash of rounded coords + name
    name: Optional[str]             # Google's placeVisit name when present
    lat: float
    lon: float
    address: Optional[str] = None


@dataclass
class TimelineSegment:
    """A visit or a movement, in chronological order."""
    seg_id: str
    kind: str                       # "visit" | "move"
    start: datetime                 # UTC
    end: datetime                   # UTC
    place: Optional[Place] = None           # set when kind == "visit"
    from_place: Optional[Place] = None      # set when kind == "move"
    to_place: Optional[Place] = None
    activity: Optional[str] = None          # "flying", "in_passenger_vehicle", "walking"
    distance_m: Optional[float] = None
    path: List[TrackPoint] = field(default_factory=list)


@dataclass
class Timeline:
    """A parsed, normalized, chronologically sorted location history."""
    segments: List[TimelineSegment]
    track: List[TrackPoint]         # flattened, sorted by ts — the join index
    tz_hint: Optional[str] = None   # IANA zone inferred from the dominant location
```

### Filtering

Raw location history is noisy: cell-tower fixes with 3 km accuracy, occasional
teleports to the other side of the country, duplicated points. Filter conservatively —
the goal is a plausible narrative, not a survey-grade track:

- Drop points with `accuracy_m` above a threshold (default 2000 m, configurable).
- Drop points implying an instantaneous speed above 1200 km/h unless the enclosing
  `activitySegment` is `"flying"`.
- Collapse runs of points within 25 m of each other into a single point at the median
  timestamp — a stationary phone emits hundreds of these and they add nothing.

Log every drop count. A track that loses 80% of its points to filtering is a bug report,
not a clean track, and the user should be told.

---

## Component 2: Photo Ingestion

```python
# NEW — core/ingest/photos.py
```

### Where the metadata comes from

Two sources, in priority order.

**1. Google Takeout sidecars** (preferred when present). A photo Takeout writes a JSON
sidecar next to each file containing `photoTakenTime.timestamp` as **epoch seconds in UTC**
and a `geoData` block. This is the best possible input: unambiguous UTC, no timezone
guessing, and it survives EXIF stripping.

```json
{
  "title": "IMG_4471.jpg",
  "photoTakenTime": { "timestamp": "1683191553", "formatted": "May 4, 2023, 9:12:33 AM UTC" },
  "geoData": { "latitude": 38.682, "longitude": -122.395, "altitude": 41.0 },
  "geoDataExif": { "latitude": 38.682, "longitude": -122.395 }
}
```

The sidecar *naming* is a genuine minefield and needs a resolver, not a `f"{name}.json"`:

- `IMG_4471.jpg.json` (older exports)
- `IMG_4471.jpg.supplemental-metadata.json` (newer)
- truncated when the combined name exceeds the filesystem limit — `IMG_4471.jp.json`
- duplicate-suffixed as `IMG_4471(1).jpg.json` for `IMG_4471(1).jpg`
- occasionally `.MP.json` / `.HEIC.json` casing mismatches

Implement `resolve_sidecar(photo_path) -> Optional[Path]` with these fallbacks, and report
the match rate. A 60% sidecar hit rate usually means the resolver is wrong, not the export.

**2. EXIF, via Pillow** (already a dependency, `pyproject.toml`). Read
`DateTimeOriginal` (36867), `OffsetTimeOriginal` (36881) when present, the GPS IFD (34853)
for `GPSLatitude`/`GPSLatitudeRef` DMS rationals, and `Make`/`Model` (used for the
per-camera clock offset in Component 4). `DateTimeOriginal` is **local wall-clock with no
zone** unless `OffsetTimeOriginal` is there — never treat it as UTC.

### Model

```python
@dataclass
class Photo:
    photo_id: str                   # content hash, stable across re-imports
    path: Path
    # Time
    taken_utc: Optional[datetime]   # resolved to UTC (see Component 4)
    taken_local_naive: Optional[datetime]   # raw EXIF wall-clock, kept for debugging
    tz_offset_source: str = "unknown"       # sidecar | exif_offset | inferred | assumed
    # Space — may be filled by the join rather than the file
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_source: str = "none"           # exif | sidecar | timeline | none
    confidence: TrackConfidence = TrackConfidence.UNKNOWN
    # Provenance
    camera: Optional[str] = None            # "Apple iPhone 14 Pro"
    camera_key: str = "unknown"             # Make/Model/Serial fingerprint — see Attribution
    credit: Optional[str] = None            # Photographer name, resolved from camera_key
    width: int = 0
    height: int = 0
    is_screenshot: bool = False             # heuristic: no camera, display aspect ratio
```

Screenshots should be detected and excluded by default (`--include-screenshots` to keep
them). They have timestamps, so they will happily join to a location and appear in the
video as a photo of someone's home screen.

### Attribution: who took the picture

A trip is usually shot by more than one person, and crediting them is both the decent thing
to do and a genuine narrative device — knowing a shot is someone else's changes how it reads.

**Google will not tell us.** Two paths look promising and neither survives contact:

- **Takeout of a collaborative album** exports only the items *you* uploaded. Photos other
  people added to a shared or collaborative album are silently excluded from the export — not
  merely unattributed, but absent. An export of a collab album is an export of your own half
  of it.
- **`MediaItem.contributorInfo`** in the Library API carries exactly the wanted
  `displayName` and profile picture of whoever added an item, but only for albums *created by
  the calling app*, only with the sharing scope — and that scope was removed on
  March 31, 2025. It is legacy surface.

There is a partial workaround worth testing: saving a shared album's items into your own
library should make them yours and therefore exportable, with `googlePhotosOrigin` marking
them as having come from a shared album. It still would not say who shot them.

**So attribute by camera, not by account.** EXIF `Make`, `Model`, and — on most dedicated
bodies and some phones — `BodySerialNumber` fingerprint a device precisely enough to
partition a mixed folder into its contributing cameras with essentially no ambiguity:

```python
def camera_key(exif: dict) -> str:
    # Stable per-device fingerprint. Falls back gracefully as tags go missing.
    parts = [exif.get("Make"), exif.get("Model"), exif.get("BodySerialNumber")]
    return "/".join(p.strip() for p in parts if p) or "unknown"
```

The user names each cluster once, and the mapping is reusable across every trip that device
shot:

```bash
cs produce timeline ~/Takeout --photos ~/trip \
    --credit "Apple iPhone 14 Pro=Aaron" \
    --credit "Canon EOS R6=Dana"
```

This is strictly better than depending on Google: it works on a folder assembled from
AirDrop, a messaging thread, a shared Drive, or three separate Takeouts — which is what a
real multi-person trip folder actually is. It also costs nothing extra, because Component 4
already groups photos by camera to infer clock offsets. Same partition, second use: a camera
that needed a +1h correction is also a distinct photographer.

Photos whose `camera_key` has no configured credit are simply uncredited. Never guess a name.

> **Do not use the sidecar's `people` field for this.** It holds face-recognition tags —
> who is *in* the photograph, not who took it. Wiring it to credits would confidently
> attribute every photo to its subject, and the error would look plausible enough to ship.

---

## Component 3: Metadata Capture

```python
# NEW — core/ingest/manifest.py, core/ingest/content_key.py
```

Component 2 assumes the photo still knows what it knew when it was taken. Increasingly it
does not.

Sanitizers strip EXIF in transit — messaging apps, upload pipelines, "remove location before
sharing" toggles, platform ingest. This is not a bug to route around and it is not going
away: for almost every other use of a photo, dropping location is the correct default.
Measured on three real frames while building this feature, from two different phones across
three separate uploads, every one arrived with a complete GPS block emptied to NaN. One
iPhone frame still carried `GPSHPositioningError: 7.02` — a value that only exists because
there *was* a fix — while every coordinate beside it had been blanked. The photos knew where
they were. Something in the middle decided we shouldn't.

The answer is to stop asking the photo. Read the metadata once, on the machine that holds the
originals, and write it to a file that travels separately:

```bash
cs timeline extract ~/Pictures/portugal          # -> trip-manifest.json
```

From there the manifest is the source of truth. The images can be copied, shared,
re-uploaded and stripped without losing anything the pipeline needs.

This is the same pattern CSP already uses for generated work. `ContentLibrary`
(`core/models/content_library.py:163`) is a registry of assets that outlives any single run;
`RunManifest` (`core/models/run_manifest.py`) records the state of a production. `TripManifest`
is that idea pointed at material the system did not create and therefore cannot regenerate —
which is exactly why losing its metadata is unrecoverable in a way a re-runnable DALL-E prompt
never is.

### The identity problem

A manifest is only useful if an entry can be matched back to its photo later, and the obvious
key does not work. Stripping metadata rewrites the file, so a content hash of the bytes no
longer matches.

What survives is the picture. A sanitizer rewrites the JPEG container and leaves the
entropy-coded scan untouched, so hashing **from the start-of-scan marker onward** produces an
identifier that no metadata segment can affect. Measured across the three cases:

| | file sha256 | scan-based content key |
|---|---|---|
| original | `496d5c34…` | `8039d7fe…` |
| EXIF stripped (lossless) | changed | **unchanged** |
| re-encoded at q85 | changed | changed |

Hashing decoded pixels gives the same invariance, but the scan hash needs no decode at all:
2.8 ms versus 196 ms on a 12 MP frame, which is 3 seconds against 3 minutes across a
thousand-photo trip. So JPEG takes the scan path and everything else falls back to pixels.

Matching then runs three keys in descending order of what each proves — exact bytes, the
metadata-invariant content key, then filename plus dimensions.

**An ambiguous key resolves to nothing, never to a guess.** Two copies of one image have
identical scan data and therefore an identical content key; the first implementation collapsed
them in a dict and silently gave both photos the *last* entry's time and place. Attaching one
photo's location to another is precisely the failure this mechanism exists to prevent, and an
unmatched photo is visible in the report while a mismatched one is invisible forever.

### Precedence

Manifest, then sidecar, then EXIF. Where the manifest and the file disagree, the file is the
degraded copy and loses — that is what it means to have been captured from the original. A
manifest may be partial, and a redacted one deliberately is, so absent fields leave whatever
the file knew.

### Redaction happens at capture

```bash
cs timeline extract ~/Pictures/portugal --location coarse    # ~1 km, 2 decimals
cs timeline extract ~/Pictures/portugal --location none      # time and camera only
```

The reduction is applied when the manifest is written, so a redacted manifest never contains
the precise value at all. This is stronger than carrying it behind a flag and trusting every
future reader to honor it.

Which makes the arrangement privacy-preferable rather than a privacy compromise: the photos
never have to leave the machine for their metadata to be usable, and what does leave can be
coarsened first. It is the local-first stance in Privacy, made operational.

### Knock-on for the join

Component 4's clock-offset inference needs GPS-bearing photos to cross-correlate against, and
in a folder assembled from shared sources there may be none — the sanitizer took exactly the
signal the inference runs on. The refusal rule already handles this correctly (under three
votes, it declines and falls back), but the spec should not describe GPS-less photos as the
edge case. In shared folders they are the norm, and a manifest captured before sharing is the
only thing that restores the signal.

---

## Component 4: The Join

```python
# NEW — core/ingest/trip_join.py
```

This is the heart of the feature and the part most worth getting right.

### Step 1: Resolve every photo to UTC

Four cases, in order:

1. **Sidecar present** → `photoTakenTime.timestamp` is epoch UTC. Done. `tz_offset_source = "sidecar"`.
2. **`OffsetTimeOriginal` present** → apply it to `DateTimeOriginal`. Done. `"exif_offset"`.
3. **Neither, but some photos from the same camera have EXIF GPS** → infer the offset
   (below). `"inferred"`.
4. **Nothing** → assume the timeline's dominant timezone for that date. `"assumed"`, and
   flag it in the report.

**Offset inference.** For each photo that has both a wall-clock time and EXIF GPS, find the
offset `k` (in whole quarter-hours, −12h…+14h) that minimizes the distance between the
photo's own GPS and the timeline's position at `wall_clock − k`. Take the mode of `k` across
all such photos **grouped by camera** (`Make`/`Model`), and apply that camera's offset to its
GPS-less photos.

This is what catches the classic failure: you flew to Portugal, your camera clock stayed on
Pacific time, and every photo joins to a location eight hours displaced — putting the castle
photos at the hotel and the dinner photos in mid-air. Cross-correlating against the photos
that *do* know where they were recovers the offset without asking the user anything.

If the mode is weak (fewer than 3 agreeing photos, or the winning offset beats the runner-up
by less than 2×), do not apply it — fall back to case 4 and say so.

### Step 2: Locate each photo

```python
def locate(photo: Photo, timeline: Timeline, max_gap: timedelta) -> Photo:
    """Attach a position and a confidence to a photo. Pure function."""
```

- If the photo time falls inside a `TimelineSegment` of kind `"visit"`, take the place's
  coordinates and name → `TrackConfidence.VISIT`. This is both the most accurate and the
  most *useful* result, because it comes with a human place name for free.
- Otherwise binary-search the sorted `track` for the bracketing points. If the gap between
  them is under `max_gap` (default 30 min), interpolate — great-circle when the enclosing
  activity is `"flying"`, linear otherwise → `INTERPOLATED`.
- If the gap is larger, still interpolate but mark `INFERRED`; a 6-hour gap means the phone
  was off and the position is a guess.
- Outside the track's range entirely → `UNKNOWN`, and the photo carries no location.

### Step 3: Validate against EXIF GPS

For photos that have their own GPS, compare it to what the timeline says. Disagreement over
a threshold (default 5 km) means one of the two is wrong. Do not silently prefer either:

- If **many** photos disagree consistently in the same direction → a clock offset survived
  Step 1. Re-run inference or warn loudly.
- If **one** photo disagrees → trust the photo's own GPS (it is a direct measurement) and
  note the discrepancy.

Emit a `JoinReport` with these counts. It is the primary debugging artifact.

```python
@dataclass
class JoinReport:
    photos_total: int
    photos_dated: int
    photos_located: int
    by_confidence: Dict[str, int]           # visit: 812, interpolated: 140, ...
    by_location_source: Dict[str, int]      # exif: 400, timeline: 552, ...
    tz_offsets_applied: Dict[str, str]      # camera -> "+01:00 (inferred, 47 photos)"
    gps_disagreements: List[Tuple[str, float]]   # photo_id, km apart
    warnings: List[str]
```

### Step 4: Build beats

A **beat** is a story unit: a place worth talking about, or a movement worth showing.

```python
@dataclass
class TripBeat:
    beat_id: str
    kind: str                       # "stay" | "move"
    start: datetime
    end: datetime
    place: Optional[Place]
    from_place: Optional[Place]
    to_place: Optional[Place]
    photos: List[Photo]             # chronological
    distance_m: Optional[float]
    day_index: int                  # 1-based day of trip
    salience: float                 # 0..1 — see below


@dataclass
class TripKnowledge:
    """The ingestion output. Analogue of a KB for personal media."""
    trip_id: str
    title: str                      # "Portugal, May 2023" — derived, user-overridable
    start: datetime
    end: datetime
    beats: List[TripBeat]
    places: List[Place]
    photos: List[Photo]
    total_distance_m: float
    report: JoinReport
```

Beat construction:

- Merge consecutive visits to the same place separated by short moves (a walk to lunch and
  back is not two beats).
- Drop visits with no photos **and** duration under a threshold — the video has nothing to
  show and nothing to say.
- Keep photo-less `"move"` beats only when the distance is significant (default > 25 km);
  these become map animations, which need no photos.

**Salience** drives budget allocation later and is deliberately simple and explainable:

```
salience = 0.4 * norm(photo_count)
         + 0.2 * norm(duration)
         + 0.2 * norm(distance_from_trip_centroid)   # the unusual places
         + 0.2 * (1.0 if first_visit_to_this_place else 0.0)
```

Photo count dominates because it is the strongest available proxy for "the person cared
about this." It maps directly onto `ScriptSegment.importance_score`.

### Degenerate inputs

Both halves must work alone:

- **Photos, no timeline.** Build a pseudo-track from the GPS-bearing photos and interpolate
  between them. Coarser, but produces beats. This is the common case for someone who never
  had Location History on.
- **Timeline, no photos.** A pure map-animation travelogue with generated or web-sourced
  imagery for the places. This is essentially what the reference project does, and it should
  fall out of the same code path.

---

## Component 5: Reverse Geocoding

Places need names. "38.682, −122.395" is not narration.

Three tiers, offline-first, because sending someone's coordinates to a web service is a
privacy decision the tool should not make on their behalf:

1. **Google's own place names.** `placeVisit` records usually already carry a name and
   address. Free, offline, and already in the export. Always try this first — it typically
   covers most beats.
2. **Bundled coarse gazetteer.** A GeoNames `cities15000` extract (CC BY 4.0, ~25k rows,
   ~2 MB) shipped with the package gives nearest-city + country for any coordinate with no
   network. Enough for "outside Sintra, Portugal."
3. **Online geocoder, opt-in only.** `--geocode online` enables Nominatim (or a configured
   provider) for precise POI names. Requires an explicit flag, respects the service's usage
   policy (1 req/s, identifying User-Agent), and caches to
   `artifacts/geocode_cache.json` so a re-run costs nothing.

Never fall through to tier 3 implicitly.

---

## Component 6: The `timeline_map` Video Provider

```python
# NEW — core/providers/video/timeline_map.py
```

Movement between places is the one thing a photo library cannot show, and it is exactly what
the reference project renders well. Implemented as a standard `VideoProvider`
(`core/providers/base.py:69`) with **zero dollar cost**, in the same family as
`core/providers/local_asset.py`:

```python
class TimelineMapProvider(VideoProvider):
    """Renders an animated map fly-through for a movement beat. Cost: $0."""

    @property
    def name(self) -> str:
        return "timeline_map"

    async def generate_video(
        self,
        prompt: str,              # unused; kept for interface conformance
        duration: float,
        aspect_ratio: str = "16:9",
        **kwargs,                 # track: List[TrackPoint], camera: "dynamic"|"steady",
                                  # style: "light"|"dark", label: str
    ) -> GenerationResult:
        ...
```

Rendering approach — two backends behind one flag:

- **`vector` (default).** Draw coastlines/borders/roads from bundled Natural Earth data with
  matplotlib, animate the path, encode with FFmpeg. **No network at all.** Lower fidelity,
  but it always works, it is fast, and it has no terms-of-service surface.
- **`tiles` (opt-in).** Raster basemap tiles for a prettier result. This carries real
  obligations that must be honored, not hand-waved: OSM's tile usage policy forbids bulk
  downloading and requires attribution rendered into the frame. Default to a commercial tile
  key from config if the user has one; never point heavy automated rendering at the free OSM
  tile servers.

Reusable ideas from the reference implementation (MIT, so vendoring with the license header
and a `NOTICE` entry is fine): great-circle interpolation for flights, long-trip time
compression so a 12-hour flight doesn't eat 40% of the animation, and the dynamic-vs-steady
camera modes.

Attribution requirements go in `docs/providers.md` alongside the other providers.

---

## Component 7: Script Generation

```python
# NEW — core/ingest/trip_script.py
```

`TripKnowledge → StructuredScript`. The beat list *is* the segment list; Claude writes prose
over a fixed skeleton and is not permitted to alter it.

The prompt gets, per beat: place name, dates, duration, photo count, a handful of photo
filenames with times, distance and mode of travel from the previous beat, and — only when the
user has opted into cloud vision — Claude-generated captions for the highest-salience photos.
Without that opt-in, the model narrates from *metadata alone*, which works better than it
sounds: "three hours in the Alfama on your second morning, forty photos" is enough to write a
line over.

Rules encoded in the prompt:

- One segment per beat. No inventing beats, no merging them.
- Never state a fact not present in the beat data. No claims about what a building is, what
  the food was, or what the weather did.
- Intent assignment follows the table in **Design** above.
- Second person by default ("you landed in Lisbon") — configurable to first person plural
  for family videos via `--voice-person`.

`ScriptSegment.importance_score` is set from beat salience, and
`SourceAttribution` records the beat as the source so the existing provenance machinery keeps
working. This needs two additions to `core/models/structured_script.py:68`:

```python
class SourceType(str, Enum):
    ...
    TIMELINE = "timeline"       # A location-history segment
    PHOTO = "photo"             # A personal photograph
```

A new narrative style `travelogue` joins the existing podcast/educational/documentary set.

---

## Component 8: DoP Extension

`core/dop.py:34` currently allocates a scarce DALL-E budget across segments. Personal photos
break its central assumption — the best asset for most segments is free and already exists —
so the assignment order changes:

1. **`personal_photo`** — the beat has photos. Pick the highest-salience one. Cost $0.
2. **`photo_montage`** — the beat has many photos and enough narration time. A Ken Burns
   sequence, rendered by the existing `local_asset` provider. Cost $0.
3. **`map_animation`** — a `"move"` beat. Rendered by `timeline_map`. Cost $0.
4. **`web_image` / `dall_e`** — only for beats with no photos. This is where the tier ratios
   from `core/video_production.py:660` still apply, but computed against **the uncovered
   segments only**, not the total.

That last point is the substantive change. Today `medium` means "27% of all segments get a
DALL-E image." For a trip, it should mean "27% of the segments that photos *couldn't* cover."
A well-photographed trip may spend nothing at all and still land at `full`-tier visual
density — which is the right outcome and is exactly why this source type is worth supporting.

Map clips are free in dollars but not in wall-clock, so tiers gain a `max_map_clips` cap
(micro 0, low 2, medium 5, high 12, full unlimited) rather than a cost ratio.

`AssetSource` (`core/models/content_library.py:32`) gains two members:

```python
    PERSONAL_PHOTO = "personal_photo"   # User's own photograph
    TIMELINE_MAP = "timeline_map"       # Rendered map animation
```

and `AssetRecord` (`core/models/content_library.py:47`) gains a personal-media block
alongside its existing audio/image blocks:

```python
    # Personal media (populated for PERSONAL_PHOTO)
    captured_at: Optional[str] = None       # ISO 8601 UTC
    place_name: Optional[str] = None        # Human-readable, safe to display
    beat_id: Optional[str] = None
    location_confidence: Optional[str] = None
    # NOTE: raw lat/lon deliberately NOT stored here — see Privacy
```

Photos enter the library as `AssetStatus.APPROVED` rather than `DRAFT`. They are the user's
own images; there is nothing to review for generation quality. The existing
`cs assets reject` flow still lets them pull individual photos out, which is the interaction
that actually matters here — "not that one" is the common edit.

---

## Component 9: Visual Grammar

```python
# NEW — core/visual_grammar.py
```

The DoP decides *which* asset a segment shows. Something still has to decide how one shot
becomes the next — and that decision is where a photo-driven video either reads as authored
or reads as a screensaver.

Two obvious approaches both fail, in opposite directions:

- **Pinned photos on a map, zooming in, every beat.** The map is *information*: it answers
  "where are we now." Once answered, repeating it spends the viewer's attention on a question
  nobody is still asking. This is the auto-generated year-in-review look.
- **A pool of transitions rotated through.** Rotation *is* arbitrariness. Viewers register it
  — not consciously, but as a sense that no cut means anything.

The principle instead: **every cut is caused by something in the join data.** The output of
Component 4 is unusually rich — time deltas, place changes, day boundaries, burst structure,
salience — and it is enough to derive the edit rather than decorate it. Transitions become
grammar, and grammar carries meaning.

### The rules

| Condition between consecutive shots | Cut |
|---|---|
| Δt < 90 s, same place, same camera — a burst | hard cut, short holds (0.6–1.2 s) |
| Δt < 5 min, same place, **different cameras** — one moment, two angles | hard cut, short holds |
| Same place, Δt beyond the burst window | short dissolve (~0.5 s) |
| New place within walking distance | dissolve + place label |
| New place, real travel | **map move** — the only context in which the map appears |
| Day boundary crossed | date card |
| First and last beat of the trip | establishing zoom, country → city, once each |

### Why the burst window widens across cameras

The first two rows differ only in whose camera fired, and the looser threshold is on the
*harder-looking* case. That is deliberate.

Within one camera, Δt is a shutter interval: 90 seconds is generous for "the same moment,
tried twice." Across two cameras it measures something else entirely — how long it took two
people to both decide a thing was worth photographing. That is a stronger signal of a single
moment than any one person's shutter rhythm, because it took two independent judgments to
produce it, and it runs on human reaction time rather than burst mode.

The threshold comes from real photos rather than a guess: two frames of the same scene, one
from a Pixel and one from an iPhone, landed 194 seconds apart. Under a single 90-second rule
they would have dissolved as if unrelated, when they are the most cuttable pair in the set.

Both rows require the same place, so a five-minute window cannot bridge a move. The condition
is `same beat AND different camera_key`, which is exactly the partition Component 2 already
computes — no new state, and it degrades to the single-camera rule on a trip shot by one
person.

The map earning its impact through scarcity is the point of the map-move and
establishing-zoom rows. It is the
establishing shot of film convention: arrive, establish once, then stay in the scene.
`max_map_clips` (Component 8) is the hard ceiling that keeps this honest even on a trip with
forty movements.

### Pacing follows salience

Hold duration and photos-per-beat come from `importance_score`, not a fixed cadence. A beat
with four hundred photos and a full day earns a long sequence; a two-hour stop with three
photos gets one shot and moves on. The edit then breathes where the trip did, which is the
cheapest available source of the feeling that someone made this on purpose.

### Motion is motivated, and rationed

Ken Burns direction is derived, never random: portraits take a slow vertical push, landscapes
drift along the bearing toward the *next* beat — so the movement points where the trip is
going. Most usefully, a meaningful fraction of shots hold completely still. Constant motion is
exhausting and reads as filler; stillness is what makes the moving shots land.

### Credit placement

Two placements with different rules, both driven by `Photo.credit` from Component 2:

- **In-frame** — a small monospace credit, lower left, rendered *only on the shot where the
  photographer changes from the previous one*, then held silently through that run. This is
  the documentary photo-credit convention. Crediting every frame is noise; crediting the
  handoff is information.
- **End credits** — a roll grouped by person with counts: `Photography — Dana (186),
  Aaron (412), Priya (44)`.

Both are suppressed entirely when only one camera is present, which is the common case and
should cost the viewer nothing.

### Output

The grammar emits a list of timed edit decisions consumed by the assembler — it renders
nothing itself and adds no new provider:

```python
@dataclass
class Cut:
    from_asset_id: Optional[str]
    to_asset_id: str
    transition: str                 # "cut" | "dissolve" | "map_move" | "date_card"
    duration_sec: float             # of the transition itself
    hold_sec: float                 # how long the incoming shot rests
    motion: Optional[str] = None    # "push_in" | "drift_bearing:142" | "still"
    cross_camera: bool = False      # the pair that widened the burst window
    overlay: Optional[str] = None   # place label, date, or credit text
    reason: str = ""                # which rule fired — for `cs timeline inspect --edit`
```

`reason` is not decoration. When an edit feels wrong, the question is always "why did it cut
there," and a grammar that cannot answer it is a grammar nobody will trust enough to tune.

---

## Component 10: CLI

```bash
# Inspect first — no video, no cost, no LLM. The debugging entry point.
cs timeline inspect ~/Takeout --photos ~/Pictures/portugal
cs timeline inspect ~/Takeout --photos ~/Pictures/portugal --from 2023-05-01 --to 2023-05-14

# Produce
cs produce timeline ~/Takeout \
    --photos ~/Pictures/portugal \
    --from 2023-05-01 --to 2023-05-14 \
    --credit "Apple iPhone 14 Pro=Aaron" --credit "Canon EOS R6=Dana" \
    --budget 5 --style travelogue --mock

# Explain the edit — every cut with the rule that produced it
cs timeline inspect ~/Takeout --photos ~/Pictures/portugal --edit
```

`cs timeline inspect` prints the `JoinReport` plus the beat list, and is where a user will
spend their first ten minutes. It must make a bad join *obvious*:

```
Trip: Portugal, May 2023  (14 days, 1,043 photos, 612 km)

Join quality
  Dated              1043/1043  (sidecar 1043, exif 0)
  Located            1039/1043  (timeline 641, exif 398)
  Confidence         visit 812 · interpolated 190 · inferred 37 · unknown 4
  Cameras            Apple iPhone 14 Pro   612 photos  May 4–17  → Aaron
                     Canon EOS R6          431 photos  May 4–17  → uncredited
  Clock offsets      Apple iPhone 14 Pro  +01:00 (sidecar)
                     Canon EOS R6         +01:00 (inferred, 47 photos agreeing)
  ⚠  3 photos disagree with the timeline by >5 km  (see --verbose)

Beats (18)
   1  stay  May  4        Lisbon — Alfama            412 photos   salience 0.94
   2  move  May  7  →     Lisbon → Sintra   28 km    map clip
   3  stay  May  7–8      Sintra                     186 photos   salience 0.71
  ...
```

`cli/produce_unified.py:70` gains a `timeline` subcommand alongside `paper`/`topic`/
`project`/`script`, and `SourceType` in `core/models/run_manifest.py:39` gains
`TIMELINE = "timeline"`. Both are additive.

---

## Privacy

This is the first source type made of data that is dangerous to leak, and the constraints
belong in the design rather than in a warning at the end of the README. The reference project
takes a strong line here — no sign-in, no analytics, files stay local, only basemap tiles
touch the network — and that norm should carry over.

**Local by default.** The entire ingest → join → beats path runs offline. Nothing leaves the
machine unless a flag says so.

**Cloud access is opt-in and granular.**

| Flag | What it permits |
|------|-----------------|
| *(default)* | Nothing leaves the box. Narration written from metadata only. |
| `--allow-cloud-vision` | Photos may be sent to Claude Vision for captions/QA. |
| `--geocode online` | Coordinates may be sent to a geocoding service. |
| `--live` | Existing meaning: paid generation APIs for uncovered beats. |

**Coordinates stay out of shared artifacts.** Raw lat/lon live in
`artifacts/runs/<run_id>/private/trip.json`, which is gitignored. The run manifest and the
content library store only `place_name` — human-readable and already a coarsening.

**Rendered output is scrubbed.** Every FFmpeg invocation on personal media passes
`-map_metadata -1`. A travel video that ships your home address in its container metadata is
a bug, and the default path must not be able to produce one.

**Home redaction.** An optional configured home point plus `--redact-radius` (default 2 km
when set) suppresses beats inside it and refuses to render map frames centered there. The
first and last beats of any trip are the user's home, and they are the ones you least want in
a video that gets posted.

Face detection and blurring are explicitly **out of scope** for this spec. It is a real
concern for shared video, it is a substantial subsystem, and pretending to solve it in
passing would be worse than not addressing it.

---

## Implementation

### Phasing

Each phase is independently useful and independently testable.

**Phase 1 — Ingest and join.** `core/ingest/timeline.py`, `core/ingest/photos.py`,
`core/ingest/trip_join.py`, and `cs timeline inspect` — including camera clustering, since
the same partition serves both clock-offset inference and attribution. No video, no LLM, no
network, no cost. This is where the risk lives (format sprawl, timezone inference) and it can
be fully validated on fixtures before anything downstream exists.

**Phase 2 — Trip to script.** `core/ingest/trip_script.py`, the `travelogue` style, the
`SourceType`/`AssetSource` enum additions, `ContentLibrary` population from photos,
`cs produce timeline --mock`. End-to-end video with photos and Ken Burns, still $0.

**Phase 3 — Maps and grammar.** `core/providers/video/timeline_map.py` with the vector
backend, the DoP changes, `max_map_clips` tiers, then `core/visual_grammar.py` and credit
rendering. Maps and grammar ship together because the map-move rule is what makes the map
scarce, and a map provider without that discipline produces exactly the screensaver
Component 9 exists to avoid. Tile backend after the vector one works.

**Phase 4 — Live and hardening.** Generated imagery for uncovered beats, opt-in vision
captions, home redaction, metadata scrubbing verified in tests.

### What NOT to change

- **The document pipeline.** No edits to `document_ingestor`, `kb.py`, or the KB models. A
  trip is not a knowledge base and should not be forced into one.
- **`StructuredScript` semantics.** New enum *members* only; no new required fields, no
  changed defaults. Every existing script must still round-trip.
- **The DoP's existing branches.** The photo-first ordering is a new branch taken only when
  a segment carries a `beat_id`. Document-sourced scripts hit the identical code path they do
  today.
- **The assembler.** Photos and map clips are images and videos; `cli/assemble.py` already
  handles both.

### Dependencies

Pillow is already present (`pyproject.toml`). Phase 3's vector backend adds `matplotlib`
plus a bundled Natural Earth extract; keep both under an optional extra
(`pip install claude-studio-producer[timeline]`) so the core install stays lean. The bundled
GeoNames gazetteer is data, not a dependency, and ships with its CC BY 4.0 attribution.

---

## Validation

**Fixtures.** A synthetic sample of each of the four timeline formats, hand-written and
small, in `tests/fixtures/timeline/`. Plus a photo fixture set covering: sidecar + EXIF GPS,
sidecar only, EXIF with `OffsetTimeOriginal`, EXIF wall-clock only, no EXIF at all, and a
screenshot.

**The tests that matter:**

- Every format parses to the same normalized `Timeline` given equivalent input.
- All coordinate encodings (E7, `geo:`, degree-string, `latLng`) produce identical floats.
- A photo inside a `placeVisit` gets `VISIT` confidence and the place's name.
- A photo in a 6-hour track gap gets `INFERRED`, not `INTERPOLATED`.
- **Clock-skew recovery**: build a fixture where GPS-bearing photos are 8 hours off; assert
  the inferred offset is −8h and that GPS-less photos from the same camera are corrected.
- **Weak-inference refusal**: two disagreeing photos must *not* produce an applied offset.
- Photos-only input (no timeline) still yields beats.
- Timeline-only input (no photos) still yields beats.
- Sidecar resolution hits all five naming variants.
- `-map_metadata -1` is present in every FFmpeg call on the personal-media path — assert on
  the constructed command, not on the output file.
- Redaction: a beat inside the home radius never appears in the resulting `StructuredScript`.
- Camera clustering partitions a mixed fixture folder into the right number of devices, and
  degrades to a stable key when `BodySerialNumber` is absent.
- An uncredited camera yields `credit=None` — never a guessed or inherited name.
- The grammar is a pure function: the same `TripKnowledge` produces byte-identical `Cut`
  lists, and every `Cut` carries a non-empty `reason`.
- Each grammar rule fires on a fixture built to trigger it, and the burst rule does not fire
  across a place change.
- A single-camera trip emits no in-frame credits and no credit roll.

**Manual acceptance.** One real export, one real photo folder, `cs timeline inspect`, and a
human confirming the beat list matches the trip they remember. The join is correct or it
isn't, and a person who was there can tell in fifteen seconds.

---

## Interaction with Other Specs

- **UNIFIED_PRODUCTION_ARCHITECTURE.md** — this is a new front-end onto the same
  `StructuredScript` + `ContentLibrary` spine. It is a useful proof that the spine is
  source-agnostic, since nothing downstream of script generation changes.
- **CONTENT_MODEL_EXPANSION.md** — first non-documentary use of `SegmentIntent`, and it
  needed no new intents. That is the strongest available evidence the vocabulary generalizes.
- **TRANSCRIPT_LED_VIDEO_PRODUCTION.md** — extends the budget-tier model with the
  "ratios apply to uncovered segments" refinement. Worth back-porting: KB figures have the
  same property (free, already exist) and are currently handled by a special case.
- **VIDEO_ASSEMBLY_ARCHITECTURE.md** — the grammar's `Cut` list is the natural input to
  assembly. Worth checking whether it should produce an EDL directly rather than a parallel
  structure the assembler has to reconcile.
- **ASSET_TRACKING_WORKFLOW.md** — photos enter as `APPROVED`; the reject flow carries the
  weight.
- **SEED_ASSETS.md** — related but distinct. Seed assets are *style* references the user
  supplies to steer generation; trip photos are *content* that replaces generation. Different
  role, different lifecycle.

---

## Open Questions

1. **Recovering other people's photos from a collab album.** Saving shared items into your
   own library ought to make them exportable via Takeout. This is one five-minute test with
   three photos, and it decides whether a multi-person trip needs one export or several — so
   it should happen before Phase 1 rather than after.
2. **Video clips in the photo folder.** Phones shoot both. A `.mov` with a timestamp joins
   exactly like a photo and is arguably better material. Deferred to keep Phase 1 small, but
   the model should not preclude it — `Photo` may want to become `MediaItem`.
3. **Live Photos / motion stills.** HEIC pairs with an embedded video. Ken Burns on the
   still is fine; using the motion is nicer. Low priority.
4. **Multi-person trips.** Merging two people's photo folders and one person's timeline is
   the actual family use case, and photo-set union with per-camera clock offsets and credits
   mostly handles it. The open part is *whose* timeline wins when two people diverge for an
   afternoon. Worth a validation pass in Phase 2 rather than a design now.
5. **Music.** A travelogue wants a bed more than a paper does, and the music providers are
   all stubs (`core/providers/music/`). Out of scope, but this is the source type that would
   justify finishing one.
6. **Aggressive trip segmentation.** A single export spans years. `--from`/`--to` is the
   Phase 1 answer; automatic trip detection (gaps in home presence) is a nice Phase 2
   addition.

---

## Appendix: File Map

**New:**

```
core/ingest/__init__.py
core/ingest/timeline.py           # Format parsing → normalized Timeline
core/ingest/photos.py             # EXIF + Takeout sidecar → Photo
core/ingest/trip_join.py          # The join, JoinReport, TripKnowledge
core/ingest/manifest.py           # TripManifest — capture before transit
core/ingest/content_key.py        # Strip-invariant image identity
core/ingest/trip_script.py        # TripKnowledge → StructuredScript
core/ingest/geocode.py            # Three-tier place naming
core/visual_grammar.py            # Cut rules, pacing, credit placement
core/providers/video/timeline_map.py
cli/timeline.py                   # cs timeline extract | inspect [--edit]
data/gazetteer/cities15000.tsv    # Bundled, CC BY 4.0
tests/fixtures/timeline/          # Four format samples
tests/fixtures/photos/            # Six metadata variants
```

**Modified:**

```
core/models/run_manifest.py:39       # SourceType += TIMELINE
core/models/structured_script.py:68  # SourceType += TIMELINE, PHOTO
core/models/content_library.py:32    # AssetSource += PERSONAL_PHOTO, TIMELINE_MAP
core/models/content_library.py:47    # AssetRecord += personal-media block
core/dop.py:34                       # Photo-first assignment, uncovered-only ratios
core/video_production.py:660         # BUDGET_TIERS += max_map_clips
cli/produce_unified.py:70            # produce timeline subcommand, --credit
cli/assemble.py                      # consume Cut list from the grammar
docs/providers.md                    # timeline_map, tile attribution obligations
```
