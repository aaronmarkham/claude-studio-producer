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
@click.argument("provider", type=click.Choice(["luma", "runway", "dalle", "elevenlabs", "openai-tts", "google-tts", "mock"]))
@click.option("--prompt", "-p", help="Text prompt for generation")
@click.option("--text", "-t", help="Text to speak (for TTS providers)")
@click.option("--duration", "-d", type=float, default=5.0, help="Video duration in seconds")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--aspect-ratio", "-a", default="16:9", help="Aspect ratio (16:9, 9:16, 1:1)")
@click.option("--image", "-i", help="Input image path or URL (for image-to-video)")
@click.option("--voice", help="Voice ID or name (for TTS providers)")
@click.option("--live", is_flag=True, help="Use live API (otherwise uses mock mode)")
def test_provider_cmd(
    provider: str,
    prompt: str,
    text: str,
    duration: float,
    output: str,
    aspect_ratio: str,
    image: str,
    voice: str,
    live: bool
):
    """
    Test a provider with a single generation.

    Quick way to verify API credentials and see output without running full pipeline.

    Examples:

        # Test video providers
        claude-studio test-provider luma -p "A rocket launching" --live
        claude-studio test-provider runway -i input.jpg -p "Make it alive" --live

        # Test image providers
        claude-studio test-provider dalle -p "Coffee on table" --live

        # Test audio providers
        claude-studio test-provider elevenlabs -t "Hello world" --voice lily --live
        claude-studio test-provider openai-tts -t "Hello world" --voice nova --live
    """
    console.print(Panel.fit(
        f"[bold cyan]Provider Test: {provider.upper()}[/bold cyan]",
        border_style="cyan"
    ))

    # Show relevant options based on provider type
    if provider in ["elevenlabs", "openai-tts", "google-tts"]:
        display_text = text or "A perfect morning begins with coffee."
        console.print(f"Text: {display_text[:80]}{'...' if len(display_text) > 80 else ''}")
        if voice:
            console.print(f"Voice: {voice}")
    else:
        display_prompt = prompt or "A steaming cup of coffee on a wooden table"
        console.print(f"Prompt: {display_prompt[:80]}{'...' if len(display_prompt) > 80 else ''}")
        if provider not in ["dalle"]:
            console.print(f"Duration: {duration}s")
            console.print(f"Aspect Ratio: {aspect_ratio}")
        if image:
            console.print(f"Input Image: {image}")

    console.print(f"Mode: {'LIVE' if live else 'MOCK'}")
    console.print()

    try:
        result = asyncio.run(_test_provider(
            provider=provider,
            prompt=prompt,
            text=text,
            duration=duration,
            aspect_ratio=aspect_ratio,
            image_path=image,
            output_path=output,
            voice=voice,
            live=live
        ))

        if result["success"]:
            console.print("[green]Generation successful![/green]")
            if result.get('type') == 'audio':
                duration = result.get('duration') or 0
                console.print(f"  Duration: {duration:.1f}s")
                console.print(f"  Format: {result.get('format', 'N/A')}")
                console.print(f"  Sample Rate: {result.get('sample_rate', 'N/A')} Hz")
            elif result.get('type') == 'image':
                console.print(f"  Image URL: {result.get('image_url', 'N/A')}")
                console.print(f"  Size: {result.get('width', 'N/A')}x{result.get('height', 'N/A')}")
            else:  # video
                console.print(f"  Video URL: {result.get('video_url', 'N/A')}")
                duration = result.get('duration') or 0
                console.print(f"  Duration: {duration:.1f}s")

            cost = result.get('cost') or 0
            console.print(f"  Cost: ${cost:.4f}")
            if result.get("local_path"):
                console.print(f"  Saved to: {result['local_path']}")
        else:
            console.print(f"[red]Generation failed: {result.get('error')}[/red]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


async def _test_provider(
    provider: str,
    prompt: str = None,
    text: str = None,
    duration: float = 5.0,
    aspect_ratio: str = "16:9",
    image_path: str = None,
    output_path: str = None,
    voice: str = None,
    live: bool = False
) -> dict:
    """Run the provider test"""

    # Check live mode requirement
    if not live and provider not in ["mock"]:
        console.print("[yellow]Running in MOCK mode. Use --live for real API calls.[/yellow]")
        console.print()

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

    elif provider == "dalle":
        if not live:
            return {"success": False, "error": "DALL-E requires --live flag (no mock mode)"}

        api_key = get_api_key("OPENAI_API_KEY")
        if not api_key:
            return {"success": False, "error": "OPENAI_API_KEY not set (check keychain or env)"}

        from core.providers.image.dalle import DalleProvider
        image_provider = DalleProvider()

    elif provider == "elevenlabs":
        if not live:
            return {"success": False, "error": "ElevenLabs requires --live flag (no mock mode)"}

        api_key = get_api_key("ELEVENLABS_API_KEY")
        if not api_key:
            return {"success": False, "error": "ELEVENLABS_API_KEY not set (check keychain or env)"}

        from core.providers.audio.elevenlabs import ElevenLabsProvider
        audio_provider = ElevenLabsProvider()

    elif provider == "openai-tts":
        if not live:
            return {"success": False, "error": "OpenAI TTS requires --live flag (no mock mode)"}

        api_key = get_api_key("OPENAI_API_KEY")
        if not api_key:
            return {"success": False, "error": "OPENAI_API_KEY not set (check keychain or env)"}

        from core.providers.audio.openai_tts import OpenAITTSProvider
        audio_provider = OpenAITTSProvider()

    elif provider == "google-tts":
        if not live:
            return {"success": False, "error": "Google TTS requires --live flag (no mock mode)"}

        api_key = get_api_key("GOOGLE_CLOUD_API_KEY")
        if not api_key:
            return {"success": False, "error": "GOOGLE_CLOUD_API_KEY not set (check keychain or env)"}

        from core.providers.audio.google_tts import GoogleTTSProvider
        audio_provider = GoogleTTSProvider()

    elif provider == "mock":
        from core.providers import MockVideoProvider
        video_provider = MockVideoProvider()

    else:
        return {"success": False, "error": f"Unknown provider: {provider}"}

    # Handle different provider types
    if provider in ["elevenlabs", "openai-tts", "google-tts"]:
        # Audio generation
        if not text:
            text = "A perfect morning begins with the gentle aroma of freshly brewed coffee."

        console.print("[dim]Generating audio...[/dim]")

        # Set output path
        if output_path:
            local_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = Path(f"test_{provider}_{timestamp}.mp3")

        # Map voice names to IDs for ElevenLabs
        voice_id = voice
        if provider == "elevenlabs" and voice:
            voice_map = {
                "lily": "pFZP5JQG7iQjIQuC4Bku",
                "rachel": "21m00Tcm4TlvDq8ikWAM",
                "adam": "pNInz6obpgDQGcFmaJgB"
            }
            voice_id = voice_map.get(voice.lower(), voice)

        result = await audio_provider.generate_speech(
            text=text,
            voice_id=voice_id
        )

        if not result.success:
            return {"success": False, "error": result.error_message}

        # Write audio data to file
        if result.audio_data:
            local_path.write_bytes(result.audio_data)

        return {
            "success": True,
            "type": "audio",
            "duration": result.duration,
            "format": result.format,
            "sample_rate": result.sample_rate,
            "cost": result.cost or 0,
            "local_path": str(local_path),
            "metadata": result.provider_metadata
        }

    elif provider == "dalle":
        # Image generation
        if not prompt:
            prompt = "A steaming cup of artisan coffee on a wooden table, morning sunlight"

        console.print("[dim]Generating image...[/dim]")

        result = await image_provider.generate_image(
            prompt=prompt,
            size="1024x1024"
        )

        if not result.success:
            return {"success": False, "error": result.error_message}

        response = {
            "success": True,
            "type": "image",
            "image_url": result.image_url,
            "width": result.width,
            "height": result.height,
            "cost": result.cost,
            "metadata": result.provider_metadata
        }

        # Download if we have a URL
        if result.image_url:
            if output_path:
                local_path = Path(output_path)
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_path = Path(f"test_{provider}_{timestamp}.png")

            console.print(f"[dim]Downloading to {local_path}...[/dim]")
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(result.image_url) as resp:
                    if resp.status == 200:
                        local_path.write_bytes(await resp.read())
                        response["local_path"] = str(local_path)

        return response

    else:
        # Video generation
        if not prompt:
            prompt = "A steaming cup of coffee on a wooden table, morning light"

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
            "type": "video",
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
