"""Upload command - Upload produced videos to YouTube."""

import json
import click
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.panel import Panel

from core.secrets import get_api_key

console = Console()


def _get_uploader():
    """Create YouTubeUploader from keychain secrets (preferred) or file path (legacy)."""
    from core.providers.upload.youtube import YouTubeUploader

    client_id = get_api_key("YOUTUBE_CLIENT_ID")
    client_secret = get_api_key("YOUTUBE_CLIENT_SECRET")
    client_secrets_path = get_api_key("YOUTUBE_CLIENT_SECRETS_PATH")

    if client_id and client_secret:
        return YouTubeUploader(client_id=client_id, client_secret=client_secret)
    elif client_secrets_path:
        return YouTubeUploader(client_secrets_path=client_secrets_path)
    else:
        console.print(Panel(
            "[red]YouTube OAuth2 credentials not configured.[/red]\n\n"
            "[bold]Option 1 — Keychain (recommended):[/bold]\n"
            "  [cyan]cs secrets set YOUTUBE_CLIENT_ID <your_client_id>[/cyan]\n"
            "  [cyan]cs secrets set YOUTUBE_CLIENT_SECRET <your_client_secret>[/cyan]\n\n"
            "[bold]Option 2 — JSON file:[/bold]\n"
            "  [cyan]cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/client_secrets.json[/cyan]\n\n"
            "Get credentials from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID (Desktop app)",
            title="YouTube Setup Required",
        ))
        raise click.Abort()


def _save_upload_metadata(video_path: str, result, title: str, description: str,
                          tags: list, privacy: str):
    """Save upload metadata to the production directory and assembly manifest."""
    video_file = Path(video_path)
    upload_meta = {
        "platform": "youtube",
        "video_id": result.video_id,
        "url": result.video_url,
        "title": title,
        "description": description,
        "tags": tags,
        "privacy": privacy,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(video_file.name),
    }

    # Save upload record next to the video
    upload_record_path = video_file.parent / "upload_record.json"
    records = []
    if upload_record_path.exists():
        try:
            records = json.loads(upload_record_path.read_text())
        except (json.JSONDecodeError, Exception):
            records = []
    records.append(upload_meta)
    upload_record_path.write_text(json.dumps(records, indent=2))

    # Update assembly manifest if it exists
    manifest_path = video_file.parent / "assembly_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            if "uploads" not in manifest:
                manifest["uploads"] = []
            manifest["uploads"].append(upload_meta)
            manifest_path.write_text(json.dumps(manifest, indent=2))
        except (json.JSONDecodeError, Exception):
            pass  # Don't fail the upload over metadata


@click.group()
def upload_cmd():
    """Upload videos to platforms."""
    pass


@upload_cmd.command("youtube")
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--title", "-t", required=True, help="Video title")
@click.option("--description", "-d", default="", help="Video description")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--category", default="27", help="YouTube category ID (27=Education, 28=Science&Tech)")
@click.option("--privacy", type=click.Choice(["public", "unlisted", "private"]), default="unlisted",
              help="Privacy status")
@click.option("--notify/--no-notify", default=False, help="Notify subscribers")
def youtube(video_path, title, description, tags, category, privacy, notify):
    """Upload a video to YouTube.
    
    Requires OAuth2 setup on first run (opens browser for consent).
    
    Setup:
        cs secrets set YOUTUBE_CLIENT_ID <client_id>
        cs secrets set YOUTUBE_CLIENT_SECRET <client_secret>
    
    Example:
        cs upload youtube ./rough_cut.mp4 -t "Hallucination Stations Explained"
    """
    uploader = _get_uploader()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    with console.status("[bold green]Uploading to YouTube..."):
        result = uploader.upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tag_list,
            category_id=category,
            privacy=privacy,
            notify_subscribers=notify,
        )

    if result.success:
        console.print(Panel(
            f"[green]✓ Upload complete![/green]\n\n"
            f"Video ID: [cyan]{result.video_id}[/cyan]\n"
            f"URL: [cyan]{result.video_url}[/cyan]\n"
            f"Privacy: {privacy}",
            title="YouTube Upload",
        ))

        # Save upload metadata alongside the video
        _save_upload_metadata(video_path, result, title, description, tag_list, privacy)
    else:
        console.print(f"[red]✗ Upload failed: {result.error}[/red]")
        raise click.Abort()


@upload_cmd.command("youtube-update")
@click.argument("video_id")
@click.option("--title", help="New title")
@click.option("--description", help="New description")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--category", help="YouTube category ID (e.g. 27=Education)")
@click.option("--privacy", type=click.Choice(["public","unlisted","private"]), help="Privacy status")
def youtube_update(video_id, title, description, tags, category, privacy):
    """Update YouTube video metadata after upload.

    Example:
        cs upload youtube-update <VIDEO_ID> --title "New Title" --description "New desc" --tags "a,b,c" --privacy public
    """
    uploader = _get_uploader()
    tag_list = None
    if tags is not None:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    console.print(f"[bold green]Updating YouTube video metadata for [cyan]{video_id}[/cyan]...[/bold green]")
    result = uploader.update_video_metadata(
        video_id=video_id,
        title=title,
        description=description,
        tags=tag_list,
        privacy=privacy,
        category_id=category,
    )
    if result.success:
        console.print(Panel(
            f"[green]✓ Metadata updated![/green] Video: https://youtu.be/{video_id}",
            title="YouTube Update",
        ))
    else:
        console.print(f"[red]✗ Update failed: {result.error}[/red]")
        if "re-auth" in str(result.error):
            console.print("[yellow]If you see a scope/insufficient permissions error, run: [bold]cs upload youtube-auth[/bold][/yellow]")
        raise click.Abort()


@upload_cmd.command("youtube-auth")
def youtube_auth():
    """Set up YouTube OAuth2 authentication.
    
    Opens a browser window for Google account authorization.
    Only needed once — token is stored for future uploads.
    """
    uploader = _get_uploader()

    console.print("[yellow]Opening browser for YouTube authorization...[/yellow]")
    try:
        if uploader.check_auth():
            console.print("[green]✓ YouTube authentication successful! Token stored for future uploads.[/green]")
        else:
            console.print("[red]✗ Authentication failed.[/red]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
