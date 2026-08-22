"""`cs timeline` — inspect a Google Timeline export joined against a photo folder.

This is the entry point for personal-media production and, deliberately, the first
thing a user runs. It generates no video, spends no money, calls no LLM and touches
no network: it answers one question, which is whether the join is any good.

A bad join is the failure mode that ruins everything downstream, and it is almost
always visible here — an inferred clock offset that should not have been applied,
a timeline that lost most of its points to filtering, photos landing in the wrong
city. Everything printed below exists to make one of those obvious at a glance.

Spec: docs/specs/PERSONAL_TIMELINE_PRODUCTION.md
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import click
from rich.console import Console

console = Console()

CONF_ORDER = ["visit", "interpolated", "inferred", "unknown"]


def _parse_credits(pairs: tuple[str, ...]) -> Dict[str, str]:
    """Turn --credit "Canon EOS R6=Dana" into {camera_key: name}."""
    credits: Dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise click.BadParameter(
                f"--credit expects CAMERA=NAME, got {pair!r}. "
                'Example: --credit "Canon EOS R6=Dana"'
            )
        camera, name = pair.split("=", 1)
        camera, name = camera.strip(), name.strip()
        if not camera or not name:
            raise click.BadParameter(f"--credit needs both halves, got {pair!r}")
        credits[camera] = name
    return credits


def _parse_date(value: Optional[str], *, end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise click.BadParameter(f"expected YYYY-MM-DD, got {value!r}") from exc
    if end:
        d = d.replace(hour=23, minute=59, second=59)
    return d.replace(tzinfo=timezone.utc)


def _fmt_day(dt: datetime) -> str:
    return dt.strftime("%b %-d") if hasattr(dt, "strftime") else str(dt)


def _fmt_span(start: datetime, end: datetime) -> str:
    """'May 4' for one day, 'May 7-8' for a span."""
    if start.date() == end.date():
        return _fmt_day(start)
    if start.month == end.month:
        return f"{_fmt_day(start)}–{end.day}"
    return f"{_fmt_day(start)}–{_fmt_day(end)}"


def _counts(mapping: Dict[str, int], order: Optional[List[str]] = None) -> str:
    keys = order or sorted(mapping)
    parts = [f"{k} {mapping[k]}" for k in keys if mapping.get(k)]
    return " · ".join(parts) if parts else "none"


def _render(trip, *, verbose: bool) -> None:
    r = trip.report
    km = trip.total_distance_m / 1000.0
    console.print()
    console.print(
        f"[bold]Trip:[/bold] {trip.title or trip.trip_id}  "
        f"[dim]({trip.day_count} days, {len(trip.photos):,} photos, {km:,.0f} km)[/dim]"
    )

    console.print("\n[bold]Join quality[/bold]")
    src = _counts(r.by_location_source)
    tz = _counts(r.by_tz_source)
    console.print(f"  {'Dated':<15} {r.photos_dated}/{r.photos_total}  [dim]({tz})[/dim]")
    console.print(f"  {'Located':<15} {r.photos_located}/{r.photos_total}  [dim]({src})[/dim]")
    console.print(f"  {'Confidence':<15} {_counts(r.by_confidence, CONF_ORDER)}")

    if r.cameras:
        label = "Cameras"
        for key, info in r.cameras.items():
            credit = info.get("credit") or "[dim]uncredited[/dim]"
            span = info.get("span", "")
            console.print(
                f"  {label:<15} {key[:26]:<26} {info.get('count', 0):>4}  "
                f"{span:<11} → {credit}"
            )
            label = ""

    if r.tz_offsets_applied:
        label = "Clock offsets"
        for key, detail in r.tz_offsets_applied.items():
            console.print(f"  {label:<15} {key[:26]:<26} {detail}")
            label = ""

    if r.gps_disagreements:
        n = len(r.gps_disagreements)
        worst = max(km for _, km in r.gps_disagreements)
        hint = "" if verbose else "  [dim](--verbose to list)[/dim]"
        console.print(
            f"  [yellow]⚠[/yellow]  {n} photo{'s' if n != 1 else ''} disagree with "
            f"the timeline, worst {worst:,.1f} km{hint}"
        )
        if verbose:
            for pid, dist in sorted(r.gps_disagreements, key=lambda x: -x[1]):
                console.print(f"       [dim]{pid}  {dist:,.1f} km[/dim]")

    for warning in r.warnings:
        console.print(f"  [yellow]⚠[/yellow]  {warning}")

    console.print(f"\n[bold]Beats[/bold] [dim]({len(trip.beats)})[/dim]")
    for i, b in enumerate(trip.beats, 1):
        span = _fmt_span(b.start, b.end)
        if b.kind == "move":
            a = (b.from_place.name if b.from_place else None) or "?"
            z = (b.to_place.name if b.to_place else None) or "?"
            dist = f"{(b.distance_m or 0) / 1000:,.0f} km"
            console.print(
                f"  {i:>3}  [cyan]move[/cyan]  {span:<11} "
                f"{(a + ' → ' + z)[:30]:<30} [dim]{dist:>8}[/dim]"
            )
        else:
            name = (b.place.name if b.place else None) or "unnamed"
            console.print(
                f"  {i:>3}  [green]stay[/green]  {span:<11} {name[:24]:<24} "
                f"{len(b.photos):>4} photos  [dim]salience {b.salience:.2f}[/dim]"
            )
    console.print()


@click.group("timeline")
def timeline_cmd():
    """Inspect Google Timeline exports joined with a photo folder."""


@timeline_cmd.command("extract")
@click.argument("photo_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Manifest path (default: <photo_dir>/trip-manifest.json)")
@click.option("--location", type=click.Choice(["full", "coarse", "none"]), default="full",
              show_default=True,
              help="How much location to record: exact, rounded, or omitted")
@click.option("--coarse-places", type=int, default=2, show_default=True,
              help="Decimal places kept when --location coarse (2 ≈ 1 km)")
@click.option("--include-screenshots", is_flag=True, help="Record screenshots too")
def extract_cmd(photo_dir, out, location, coarse_places, include_screenshots):
    """Capture photo metadata into a portable manifest, before anything strips it.

    \b
    Run this on the machine holding the originals. Everything downstream can then
    work from the manifest, so the photos can be copied, shared or re-uploaded
    without losing what the pipeline needs:

      cs timeline extract ~/Pictures/portugal
      cs timeline extract ~/Pictures/portugal --location coarse -o trip.json

    Metadata is read, not written: your photos are never modified.
    """
    from core.ingest.manifest import DEFAULT_FILENAME, build_manifest
    from core.ingest.photos import load_photos

    photos = load_photos(photo_dir, include_screenshots=include_screenshots)
    if not photos:
        raise click.ClickException(f"No readable images found in {photo_dir}")

    manifest = build_manifest(
        photos, source_dir=photo_dir, location=location, coarse_places=coarse_places
    )
    target = out or (photo_dir / DEFAULT_FILENAME)
    manifest.save(target)

    with_time = sum(1 for e in manifest.entries if e.taken_utc or e.taken_local_naive)
    with_gps = sum(1 for e in manifest.entries if e.lat is not None)
    cameras = {e.camera_key for e in manifest.entries}
    methods = _counts({m: sum(1 for e in manifest.entries if e.content_method == m)
                       for m in {e.content_method for e in manifest.entries}})

    console.print()
    console.print(f"[bold]Captured[/bold] {len(manifest.entries):,} photos → {target}")
    console.print(f"  {'Timestamps':<15} {with_time}/{len(manifest.entries)}")
    console.print(f"  {'Coordinates':<15} {with_gps}/{len(manifest.entries)}"
                  f"  [dim]({manifest.location_policy})[/dim]")
    console.print(f"  {'Cameras':<15} {len(cameras)}")
    console.print(f"  {'Content keys':<15} {methods}")
    if with_gps == 0 and location != "none":
        console.print(
            "  [yellow]⚠[/yellow]  No coordinates found — if these photos have "
            "already passed\n     through a sharing or upload step, capture from "
            "the originals instead."
        )
    console.print()


@timeline_cmd.command("inspect")
@click.argument("export_path", type=click.Path(exists=True, path_type=Path), required=False)
@click.option("--photos", "photo_dir", type=click.Path(exists=True, path_type=Path),
              help="Folder of photos to join against the timeline")
@click.option("--from", "date_from", help="Start date, YYYY-MM-DD")
@click.option("--to", "date_to", help="End date, YYYY-MM-DD")
@click.option("--credit", "credit_pairs", multiple=True,
              help='Attribute a camera: --credit "Canon EOS R6=Dana"')
@click.option("--manifest", "manifest_path", type=click.Path(exists=True, path_type=Path),
              help="Metadata manifest from `cs timeline extract` (wins over EXIF)")
@click.option("--include-screenshots", is_flag=True, help="Keep screenshots in the set")
@click.option("--max-accuracy", type=int, default=2000, show_default=True,
              help="Drop location fixes worse than this, in meters")
@click.option("--max-gap", type=int, default=30, show_default=True,
              help="Minutes of track gap before a position is only INFERRED")
@click.option("--verbose", "-V", is_flag=True, help="List every GPS disagreement")
@click.option("--json", "as_json", is_flag=True, help="Emit the join report as JSON")
def inspect_cmd(export_path, photo_dir, date_from, date_to, credit_pairs, manifest_path,
                include_screenshots, max_accuracy, max_gap, verbose, as_json):
    """Parse, join, and report. No video, no cost, no network.

    \b
    Either half works alone:
      cs timeline inspect ~/Takeout                      # timeline only
      cs timeline inspect --photos ~/Pictures/trip       # photos only (GPS-bearing)
      cs timeline inspect ~/Takeout --photos ~/Pictures/trip
    """
    # Imported lazily so `cs --help` stays fast and the CLI loads without Pillow.
    from datetime import timedelta

    from core.ingest.models import Timeline
    from core.ingest.photos import load_photos
    from core.ingest.timeline import parse_timeline
    from core.ingest.trip_join import join_trip

    if not export_path and not photo_dir:
        raise click.UsageError(
            "Give a Timeline export, a --photos folder, or both.\n"
            "  cs timeline inspect ~/Takeout --photos ~/Pictures/trip"
        )

    credits = _parse_credits(credit_pairs)
    start, end = _parse_date(date_from), _parse_date(date_to, end=True)

    timeline = (
        parse_timeline(export_path, max_accuracy_m=max_accuracy)
        if export_path else Timeline(source_format="photos_only")
    )
    manifest = None
    if manifest_path:
        from core.ingest.manifest import TripManifest
        manifest = TripManifest.load(manifest_path)
    photos = (
        load_photos(photo_dir, include_screenshots=include_screenshots,
                    credits=credits, manifest=manifest)
        if photo_dir else []
    )
    manifest_matched = (
        sum(1 for p in photos if p.taken_utc or p.lat is not None)
        if manifest is not None else 0
    )
    if manifest is not None and photos and not as_json:
        console.print(
            f"\n[dim]manifest: {len(manifest.entries)} entries, "
            f"{manifest_matched}/{len(photos)} photos matched "
            f"({manifest.location_policy} location)[/dim]"
        )

    if start or end:
        def in_range(ts) -> bool:
            return (start is None or ts >= start) and (end is None or ts <= end)

        # Photos are bounded inside the join, once their timezone is resolved —
        # an EXIF-only photo has no UTC time yet, so filtering it here would
        # either keep everything or drop everything.
        timeline.track = [pt for pt in timeline.track if in_range(pt.ts)]
        timeline.segments = [s for s in timeline.segments if in_range(s.start)]

    trip = join_trip(timeline, photos, credits=credits,
                     max_gap=timedelta(minutes=max_gap),
                     start_after=start, end_before=end)

    if as_json:
        report = trip.report
        click.echo(json.dumps({
            "trip_id": trip.trip_id,
            "title": trip.title,
            "days": trip.day_count,
            "photos": len(trip.photos),
            "total_distance_km": round(trip.total_distance_m / 1000, 1),
            "beats": len(trip.beats),
            "report": {
                "photos_total": report.photos_total,
                "photos_dated": report.photos_dated,
                "photos_located": report.photos_located,
                "by_confidence": report.by_confidence,
                "by_location_source": report.by_location_source,
                "by_tz_source": report.by_tz_source,
                "tz_offsets_applied": report.tz_offsets_applied,
                "gps_disagreements": [
                    {"photo_id": p, "km": round(d, 2)} for p, d in report.gps_disagreements
                ],
                "warnings": report.warnings,
            },
            **({"manifest": {
                "entries": len(manifest.entries),
                "matched": manifest_matched,
                "location_policy": manifest.location_policy,
            }} if manifest is not None else {}),
        }, indent=2))
        return

    if timeline.stats.points_in and timeline.stats.points_out < timeline.stats.points_in * 0.2:
        console.print(
            f"\n[yellow]⚠  Filtering kept only {timeline.stats.points_out} of "
            f"{timeline.stats.points_in} location fixes.[/yellow] "
            "[dim]Try --max-accuracy 5000.[/dim]"
        )
    _render(trip, verbose=verbose)
