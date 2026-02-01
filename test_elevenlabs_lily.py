"""Test ElevenLabs with Lily's voice"""
import asyncio
from core.providers.audio.elevenlabs import ElevenLabsProvider

async def main():
    # Create provider
    provider = ElevenLabsProvider()

    # Coffee narration script
    text = """A perfect morning begins with the gentle aroma of freshly brewed coffee.
Watch as delicate wisps of steam rise and dance in the golden morning light,
creating a peaceful moment of tranquility before the day begins."""

    print("Generating audio with Lily's voice...")
    print(f"Text: {text}")
    print()

    # Generate with Lily's voice
    result = await provider.generate_speech(
        text=text,
        voice_id="pFZP5JQG7iQjIQuC4Bku",  # Lily
        output_path="coffee_narration_lily.mp3"
    )

    if result.success:
        print(f"✓ Success!")
        print(f"  Output: {result.output_path}")
        print(f"  Duration: {result.duration:.2f}s")
        print(f"  Format: {result.format}")
        print(f"  Sample rate: {result.sample_rate} Hz")
        if result.cost:
            print(f"  Cost: ${result.cost:.4f}")
    else:
        print(f"✗ Failed: {result.error_message}")

if __name__ == "__main__":
    asyncio.run(main())
