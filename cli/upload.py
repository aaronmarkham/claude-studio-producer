"""Upload command - Upload produced videos to YouTube."""

import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from core.secrets import get_api_key

console = Console()


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
    Set client secrets path: cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/file.json
    
    Example:
        cs upload youtube ./rough_cut.mp4 -t "Hallucination Stations Explained"
    """
    from core.providers.upload.youtube import YouTubeUploader

    # Get client secrets path from secrets store
    client_secrets = get_api_key("YOUTUBE_CLIENT_SECRETS_PATH")
    if not client_secrets:
        console.print(Panel(
            "[red]YouTube OAuth2 client secrets not configured.[/red]\n\n"
            "1. Go to Google Cloud Console → APIs & Services → Credentials\n"
            "2. Create an OAuth 2.0 Client ID (Desktop application)\n"
            "3. Download the client secrets JSON file\n"
            "4. Run: [cyan]cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/client_secrets.json[/cyan]",
            title="YouTube Setup Required",
        ))
        raise click.Abort()

    uploader = YouTubeUploader(client_secrets_path=client_secrets)

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
    from core.providers.upload.youtube import YouTubeUploader

    client_secrets = get_api_key("YOUTUBE_CLIENT_SECRETS_PATH")
    if not client_secrets:
        console.print("[red]Set client secrets first: cs secrets set YOUTUBE_CLIENT_SECRETS_PATH /path/to/file.json[/red]")
        raise click.Abort()

    uploader = YouTubeUploader(client_secrets_path=client_secrets)

    console.print("[yellow]Opening browser for YouTube authorization...[/yellow]")
    try:
        if uploader.check_auth():
            console.print("[green]✓ YouTube authentication successful! Token stored for future uploads.[/green]")
        else:
            console.print("[red]✗ Authentication failed.[/red]")
    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")
