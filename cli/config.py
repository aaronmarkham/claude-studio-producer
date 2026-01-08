"""Configuration commands"""

import click
from rich.console import Console
from rich.table import Table
from rich import box
from pathlib import Path

console = Console()


@click.group()
def config_cmd():
    """Configuration management"""
    pass


@config_cmd.command()
def show():
    """Show current configuration"""

    import os
    from dotenv import dotenv_values

    # Load from .env if exists
    env_file = Path(".env")
    env_values = dotenv_values(env_file) if env_file.exists() else {}

    table = Table(title="Configuration", box=box.ROUNDED)
    table.add_column("Key", style="cyan")
    table.add_column("Source")
    table.add_column("Status")

    keys = [
        ("ANTHROPIC_API_KEY", "Required"),
        ("RUNWAY_API_KEY", "Video"),
        ("PIKA_API_KEY", "Video"),
        ("LUMA_API_KEY", "Video"),
        ("KLING_API_KEY", "Video"),
        ("STABILITY_API_KEY", "Video/Image"),
        ("ELEVENLABS_API_KEY", "Audio"),
        ("OPENAI_API_KEY", "Audio/Image"),
        ("MUBERT_API_KEY", "Music"),
        ("SUNO_API_KEY", "Music"),
    ]

    for key, category in keys:
        in_env = key in env_values
        in_environ = key in os.environ

        if in_environ:
            source = "environment"
            status = "[green]✓ Set[/green]"
        elif in_env:
            source = ".env file"
            status = "[green]✓ Set[/green]"
        else:
            source = "—"
            status = "[dim]Not set[/dim]"

        table.add_row(f"{key} ({category})", source, status)

    console.print(table)

    if not env_file.exists():
        console.print("\n[yellow]No .env file found. Run 'claude-studio config init' to create one.[/yellow]")


@config_cmd.command()
def validate():
    """Validate API keys by making test calls"""

    import os
    import asyncio
    from dotenv import load_dotenv

    # Load .env
    load_dotenv()

    console.print("Validating API keys...\n")

    validations = [
        ("ANTHROPIC_API_KEY", validate_anthropic),
        ("RUNWAY_API_KEY", validate_runway),
        ("ELEVENLABS_API_KEY", validate_elevenlabs),
    ]

    for key_name, validator in validations:
        if os.getenv(key_name):
            console.print(f"Checking {key_name}...", end=" ")
            try:
                asyncio.run(validator())
                console.print("[green]✓ Valid[/green]")
            except Exception as e:
                console.print(f"[red]✗ Invalid: {e}[/red]")
        else:
            console.print(f"{key_name}: [dim]Not set, skipping[/dim]")


@config_cmd.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing .env")
def init(force: bool):
    """Create .env template file"""

    env_file = Path(".env")

    if env_file.exists() and not force:
        console.print("[yellow].env file already exists. Use --force to overwrite.[/yellow]")
        return

    template = '''# Claude Studio Producer Configuration
# Copy this file to .env and fill in your API keys

# ===================
# REQUIRED
# ===================
ANTHROPIC_API_KEY=

# ===================
# VIDEO PROVIDERS
# ===================
# At least one recommended for video generation
RUNWAY_API_KEY=
PIKA_API_KEY=
LUMA_API_KEY=
KLING_API_KEY=
STABILITY_API_KEY=

# ===================
# AUDIO PROVIDERS
# ===================
# At least one recommended for voiceover
ELEVENLABS_API_KEY=
OPENAI_API_KEY=

# ===================
# MUSIC PROVIDERS
# ===================
MUBERT_API_KEY=
SUNO_API_KEY=

# ===================
# STORAGE (Optional)
# ===================
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-west-2
S3_BUCKET=

# ===================
# DEVELOPMENT
# ===================
ENV=development
DEBUG=true
PROVIDER_MODE=mock
'''

    env_file.write_text(template)
    console.print(f"[green]Created {env_file}[/green]")
    console.print("Edit the file to add your API keys.")


async def validate_anthropic():
    """Validate Anthropic API key"""
    from anthropic import Anthropic
    import os
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    # Make a minimal API call
    await client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=10,
        messages=[{"role": "user", "content": "Hi"}]
    )


async def validate_runway():
    """Validate Runway API key"""
    import httpx
    import os
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.runwayml.com/v1/account",
            headers={"Authorization": f"Bearer {os.getenv('RUNWAY_API_KEY')}"}
        )
        response.raise_for_status()


async def validate_elevenlabs():
    """Validate ElevenLabs API key"""
    import httpx
    import os
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY")}
        )
        response.raise_for_status()
