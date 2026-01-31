"""Test provider command - Quick provider testing without full pipeline"""

import asyncio
from pathlib import Path
from datetime import datetime

import click
from rich.console import Console
from rich.panel import Panel

from core.providers.base import VideoProviderConfig, ProviderType
from core.secrets import get_api_key

console = Console()


@click.command()
@click.argument("provider", type=click.Choice(["luma", "runway", "mock"]))
@click.option("--prompt", "-p", default="A steaming cup of coffee on a wooden table, morning light",
              help="Text prompt for video generation")
@click.option("--duration", "-d", type=float, default=5.0, help="Video duration in seconds")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--aspect-ratio", "-a", default="16:9", help="Aspect ratio (16:9, 9:16, 1:1)")
@click.option("--image", "-i", help="Input image path or URL (for image-to-video)")
def test_provider_cmd(
    provider: str,
    prompt: str,
    duration: float,
    output: str,
    aspect_ratio: str,
    image: str
):
    """
    Test a video provider with a single generation.

    Quick way to verify API credentials and see output without running full pipeline.

    Examples:

        # Test Luma with default prompt
        claude-studio test-provider luma

        # Test with custom prompt
        claude-studio test-provider luma -p "A rocket launching into space"

        # Test Runway with input image
        claude-studio test-provider runway -i input.jpg -p "Make it come alive"
    """
    console.print(Panel.fit(
        f"[bold cyan]Provider Test: {provider.upper()}[/bold cyan]",
        border_style="cyan"
    ))

    console.print(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    console.print(f"Duration: {duration}s")
    console.print(f"Aspect Ratio: {aspect_ratio}")
    if image:
        console.print(f"Input Image: {image}")
    console.print()

    try:
        result = asyncio.run(_test_provider(
            provider=provider,
            prompt=prompt,
            duration=duration,
            aspect_ratio=aspect_ratio,
            image_path=image,
            output_path=output
        ))

        if result["success"]:
            console.print("[green]Generation successful![/green]")
            console.print(f"  Video URL: {result.get('video_url', 'N/A')}")
            console.print(f"  Duration: {result.get('duration', 0):.1f}s")
            console.print(f"  Cost: ${result.get('cost', 0):.4f}")
            if result.get("local_path"):
                console.print(f"  Saved to: {result['local_path']}")
        else:
            console.print(f"[red]Generation failed: {result.get('error')}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


async def _test_provider(
    provider: str,
    prompt: str,
    duration: float,
    aspect_ratio: str,
    image_path: str = None,
    output_path: str = None
) -> dict:
    """Run the provider test"""

    # Get provider instance
    if provider == "luma":
        api_key = get_api_key("LUMA_API_KEY")
        if not api_key:
            return {"success": False, "error": "LUMA_API_KEY not set (check keychain or env)"}

        from core.providers.video.luma import LumaProvider
        video_provider = LumaProvider()

    elif provider == "runway":
        api_key = get_api_key("RUNWAY_API_KEY")
        if not api_key:
            return {"success": False, "error": "RUNWAY_API_KEY not set (check keychain or env)"}

        if not image_path:
            return {"success": False, "error": "Runway requires --image input"}

        from core.providers.video.runway import RunwayProvider
        config = VideoProviderConfig(
            provider_type=ProviderType.RUNWAY,
            api_key=api_key,
            timeout=300
        )
        video_provider = RunwayProvider(config=config)

    elif provider == "mock":
        from core.providers import MockVideoProvider
        video_provider = MockVideoProvider()

    else:
        return {"success": False, "error": f"Unknown provider: {provider}"}

    # Build kwargs
    kwargs = {}
    if image_path:
        # Luma uses start_image_url, Runway uses image_url
        if provider == "luma":
            kwargs["start_image_url"] = image_path
        else:
            kwargs["image_url"] = image_path

    # Generate
    console.print("[dim]Generating video...[/dim]")

    result = await video_provider.generate_video(
        prompt=prompt,
        duration=duration,
        aspect_ratio=aspect_ratio,
        **kwargs
    )

    if not result.success:
        return {"success": False, "error": result.error_message}

    response = {
        "success": True,
        "video_url": result.video_url,
        "duration": result.duration,
        "cost": result.cost,
        "metadata": result.provider_metadata
    }

    # Download if URL is remote
    if result.video_url and result.video_url.startswith("http"):
        if output_path:
            local_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = Path(f"test_{provider}_{timestamp}.mp4")

        console.print(f"[dim]Downloading to {local_path}...[/dim]")
        success = await video_provider.download_video(result.video_url, str(local_path))

        if success:
            response["local_path"] = str(local_path)
        else:
            console.print("[yellow]Download failed - video available at URL[/yellow]")

    return response
