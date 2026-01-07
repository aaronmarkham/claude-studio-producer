"""
OpenAI Text-to-Speech Provider

Pricing (as of 2025):
- TTS-1: $0.015 per 1K characters (standard quality)
- TTS-1-HD: $0.030 per 1K characters (high definition)

Features:
- 6 built-in voices (alloy, echo, fable, onyx, nova, shimmer)
- Fast generation
- Good quality-to-price ratio
- Real-time audio streaming support

API Docs: https://platform.openai.com/docs/guides/text-to-speech
"""

import os
import asyncio
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..base import AudioProvider, AudioProviderConfig, AudioGenerationResult


class OpenAITTSProvider(AudioProvider):
    """OpenAI text-to-speech provider"""

    _is_stub = False  # Fully implemented

    # Available voices
    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    # API endpoint
    API_URL = "https://api.openai.com/v1/audio/speech"

    def __init__(self, config: AudioProviderConfig, model: str = "tts-1"):
        """
        Initialize OpenAI TTS provider.

        Args:
            config: Provider configuration
            model: "tts-1" (standard) or "tts-1-hd" (high quality)
        """
        super().__init__(config)
        self.model = model
        self._cost_per_1k = 0.015 if model == "tts-1" else 0.030

        if not self.config.api_key:
            raise ValueError("OpenAI API key required")

    @property
    def name(self) -> str:
        return "openai_tts"

    async def generate_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Generate speech from text using OpenAI TTS API

        Args:
            text: Text to convert to speech
            voice_id: Voice identifier (alloy, echo, fable, onyx, nova, shimmer)
            speed: Speech speed (0.25 to 4.0, default 1.0)
            **kwargs: Additional parameters:
                - response_format: mp3, opus, aac, flac, wav, pcm (default: mp3)

        Returns:
            AudioGenerationResult with audio file path and metadata
        """
        # Default voice
        voice = voice_id or "alloy"
        if voice not in self.VOICES:
            return AudioGenerationResult(
                success=False,
                error_message=f"Invalid voice '{voice}'. Must be one of: {', '.join(self.VOICES)}"
            )

        # Validate speed
        if not 0.25 <= speed <= 4.0:
            return AudioGenerationResult(
                success=False,
                error_message=f"Speed must be between 0.25 and 4.0, got {speed}"
            )

        # Get response format
        response_format = kwargs.get("response_format", "mp3")

        # Estimate duration: ~150 words per minute
        word_count = len(text.split())
        estimated_duration = (word_count / 150.0) * 60.0 / speed

        # Calculate cost
        cost = self.estimate_cost(text)

        # Create output directory
        output_dir = Path("artifacts/audio")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        output_path = output_dir / f"openai_tts_{text_hash}_{voice}.{response_format}"

        try:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": text,
                        "voice": voice,
                        "speed": speed,
                        "response_format": response_format
                    }
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return AudioGenerationResult(
                            success=False,
                            error_message=f"OpenAI TTS API error ({response.status}): {error_text}",
                            cost=cost
                        )

                    # Save audio bytes to file
                    audio_bytes = await response.read()
                    output_path.write_bytes(audio_bytes)

                # Determine sample rate and channels based on format
                if response_format == "pcm":
                    sample_rate = 24000
                    channels = 1
                elif response_format == "wav":
                    sample_rate = 24000
                    channels = 1
                else:
                    sample_rate = 24000  # OpenAI TTS default
                    channels = 1  # Mono

                return AudioGenerationResult(
                    success=True,
                    audio_url=str(output_path),  # Local file path
                    audio_path=str(output_path),
                    duration=estimated_duration,
                    format=response_format,
                    sample_rate=sample_rate,
                    channels=channels,
                    cost=cost,
                    provider_metadata={
                        "model": self.model,
                        "voice": voice,
                        "speed": speed,
                        "text_length": len(text),
                        "word_count": word_count
                    }
                )

        except aiohttp.ClientError as e:
            return AudioGenerationResult(
                success=False,
                error_message=f"OpenAI TTS request failed: {str(e)}",
                cost=cost
            )
        except asyncio.TimeoutError:
            return AudioGenerationResult(
                success=False,
                error_message=f"OpenAI TTS request timed out after {self.config.timeout}s",
                cost=cost
            )
        except Exception as e:
            return AudioGenerationResult(
                success=False,
                error_message=f"OpenAI TTS generation failed: {str(e)}",
                cost=cost
            )

    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        List available OpenAI voices.

        Returns:
            List of 6 built-in voice options
        """
        return [
            {"id": voice, "name": voice.title(), "language": "en"}
            for voice in self.VOICES
        ]

    def estimate_cost(self, text: str, **kwargs) -> float:
        """
        Estimate OpenAI TTS generation cost.

        Args:
            text: Text to be spoken

        Returns:
            Estimated cost in USD
        """
        char_count = len(text)
        return (char_count / 1000) * self._cost_per_1k

    async def validate_credentials(self) -> bool:
        """
        Validate OpenAI API key by attempting a minimal request

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            # Try generating a very short speech sample
            result = await self.generate_speech(
                text="Test",
                voice_id="alloy"
            )
            return result.success
        except Exception:
            return False
