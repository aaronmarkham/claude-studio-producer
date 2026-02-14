"""Upload command - Upload produced videos to YouTube."""

import click
from pathlib import Path
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
    else:
        console.print(f"[red]✗ Upload failed: {result.error}[/red]")
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
