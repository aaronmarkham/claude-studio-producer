"""
Inworld TTS Provider

Text-to-speech provider using Inworld AI's TTS API.

Features:
- Ultra-realistic, context-aware speech synthesis
- Voice cloning (instant and professional)
- Multiple models (TTS-1, TTS-1-Max)
- 12+ language support
- Audio markups for emotion and style
- Streaming and non-streaming modes

Documentation: https://docs.inworld.ai/docs/tts/tts

Auto-generated stub. Complete using:
    claude-studio provider onboard -n inworld -t audio -s core/providers/audio/inworld.py -d https://docs.inworld.ai/docs/tts/tts
"""

import os
import asyncio
import base64
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, AsyncGenerator
from enum import Enum

import httpx

from ..base import AudioProvider, AudioProviderConfig, AudioGenerationResult


# =============================================================================
# DATA MODELS
# =============================================================================

class InworldModel(Enum):
    """Available Inworld TTS models"""
    TTS_1 = "inworld-tts-1"          # Fast, cost-efficient
    TTS_1_MAX = "inworld-tts-1-max"  # More expressive, better multilingual


class AudioFormat(Enum):
    """Supported audio output formats"""
    MP3 = "MP3"
    WAV = "LINEAR_PCM"
    OPUS = "OPUS"


class TimestampType(Enum):
    """Timestamp alignment options"""
    NONE = "NONE"
    WORD = "WORD"
    CHARACTER = "CHARACTER"


@dataclass
class VoiceInfo:
    """Information about a voice"""
    voice_id: str
    name: str
    gender: str  # "MALE", "FEMALE", "NEUTRAL"
    age_group: str  # "YOUNG", "ADULT", "SENIOR"
    accent: str
    language_codes: List[str] = field(default_factory=list)
    preview_url: Optional[str] = None


@dataclass
class InworldConfig(AudioProviderConfig):
    """Configuration for Inworld TTS provider"""
    base_url: str = "https://api.inworld.ai/v1"
    model: InworldModel = InworldModel.TTS_1
    default_voice: str = "Hades"
    audio_format: AudioFormat = AudioFormat.MP3
    sample_rate: int = 24000
    streaming: bool = False


# =============================================================================
# MAIN PROVIDER
# =============================================================================

class InworldProvider(AudioProvider):
    """
    Inworld AI text-to-speech provider.

    Environment Variables:
        INWORLD_API_KEY: API key from Inworld Portal

    Usage:
        from core.providers.base import AudioProviderConfig
        config = AudioProviderConfig(api_key=os.environ.get("INWORLD_API_KEY"))
        inworld_config = InworldConfig(**config.__dict__)
        provider = InworldProvider(inworld_config)
        result = await provider.generate_speech("Hello, world!", voice_id="Hades")

        # With emotion markup
        result = await provider.generate_speech("[happy] Great news!", voice_id="Hades")

    Supported Audio Markups (experimental, English only):
        Emotions: [happy], [sad], [angry], [surprised], [whisper]
        Non-verbals: [sigh], [cough], [breathe], [laugh], [clear_throat]
    """

    _is_stub = True  # Not fully implemented yet

    # Pricing per character (as of 2025)
    PRICING = {
        InworldModel.TTS_1: 0.000015,      # $0.015 per 1K chars
        InworldModel.TTS_1_MAX: 0.00003,   # $0.03 per 1K chars
    }

    # Supported languages
    SUPPORTED_LANGUAGES = [
        "en", "es", "fr", "de", "it", "pt",
        "zh", "ja", "ko", "nl", "pl", "ru"
    ]

    # Built-in voices
    VOICES = [
        "Hades", "Timothy", "Deborah", "Marcus", "Julia",
        "Kai", "Luna", "Oliver", "Sophia", "Viktor"
    ]

    def __init__(self, config: InworldConfig):
        super().__init__(config)
        self.inworld_config = config

        if not self.config.api_key:
            self.config.api_key = os.environ.get("INWORLD_API_KEY", "")

        if not self.config.api_key:
            raise ValueError(
                "INWORLD_API_KEY environment variable not set. "
                "Get your API key from https://platform.inworld.ai"
            )

        # The API key from Inworld Portal is base64-encoded
        self.client = httpx.AsyncClient(
            base_url=self.inworld_config.base_url,
            headers={
                "Authorization": f"Basic {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.config.timeout,
        )

    @property
    def name(self) -> str:
        return "inworld"

    # =========================================================================
    # MAIN SYNTHESIS
    # =========================================================================

    async def generate_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        language: str = "en",
        pitch: float = 0.0,
        temperature: float = 0.8,
        timestamp_type: TimestampType = TimestampType.NONE,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Generate speech from text.

        Args:
            text: Text to synthesize (supports audio markups)
            voice_id: Voice ID (built-in or cloned)
            speed: Speaking rate (0.5 to 1.5, default 1.0)
            language: Language code (en, es, fr, etc.)
            pitch: Voice pitch adjustment (-20 to 20, default 0)
            temperature: Expressiveness (0.6 to 1.0 recommended)
            timestamp_type: Word/character timestamp alignment
            **kwargs: Additional parameters

        Returns:
            AudioGenerationResult with audio data/URL and metadata
        """
        voice_id = voice_id or self.inworld_config.default_voice

        # Build request
        request_body = {
            "input": {
                "text": text
            },
            "voice": {
                "name": voice_id,
                "languageCode": language,
            },
            "audioConfig": {
                "audioEncoding": self.inworld_config.audio_format.value,
                "sampleRateHertz": self.inworld_config.sample_rate,
                "speakingRate": speed,
                "pitch": pitch,
            },
            "modelConfig": {
                "model": self.inworld_config.model.value,
                "temperature": temperature,
            }
        }

        # Add timestamp if requested
        if timestamp_type != TimestampType.NONE:
            request_body["timestampType"] = timestamp_type.value

        # Call API
        if self.inworld_config.streaming:
            return await self._synthesize_streaming(request_body)
        else:
            return await self._synthesize_sync(request_body, text)

    async def _synthesize_sync(
        self,
        request_body: Dict[str, Any],
        original_text: str
    ) -> AudioGenerationResult:
        """Non-streaming synthesis"""

        # TODO: Implement actual API call
        # Endpoint: POST /tts/synthesize

        response = await self.client.post(
            "/tts/synthesize",
            json=request_body
        )
        response.raise_for_status()

        data = response.json()

        # Decode audio content
        audio_content = base64.b64decode(data.get("audioContent", ""))

        return AudioGenerationResult(
            success=True,
            audio_url=None,
            duration=data.get("audioDuration", 0.0),
            format=self.inworld_config.audio_format.value.lower(),
            sample_rate=self.inworld_config.sample_rate,
            cost=self.estimate_cost(original_text),
            provider_metadata={
                "model": self.inworld_config.model.value,
                "voice": request_body["voice"]["name"],
                "character_count": len(original_text),
                "timepoints": data.get("timepoints"),
            }
        )

    async def _synthesize_streaming(
        self,
        request_body: Dict[str, Any]
    ) -> AudioGenerationResult:
        """Streaming synthesis (lower latency)"""

        # TODO: Implement streaming endpoint
        # Endpoint: POST /tts/synthesize:stream

        raise NotImplementedError("Streaming synthesis not yet implemented")

    # =========================================================================
    # VOICE MANAGEMENT
    # =========================================================================

    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        List available voices.

        Returns:
            List of voice info dicts
        """
        # TODO: Implement actual API call
        # Endpoint: GET /voices

        response = await self.client.get("/voices")
        response.raise_for_status()

        voices = []
        for v in response.json().get("voices", []):
            voice_info = {
                "voice_id": v.get("name", ""),
                "name": v.get("displayName", ""),
                "gender": v.get("properties", {}).get("gender", "NEUTRAL"),
                "age_group": v.get("properties", {}).get("ageGroup", "ADULT"),
                "accent": v.get("properties", {}).get("accent", ""),
                "language_codes": v.get("languageCodes", []),
                "preview_url": v.get("previewAudioUri"),
            }
            voices.append(voice_info)

        return voices

    async def clone_voice(
        self,
        audio_sample: bytes,
        name: str,
        description: Optional[str] = None,
    ) -> str:
        """
        Clone a voice from an audio sample (instant cloning).

        Requires 5-15 seconds of clear audio.

        Args:
            audio_sample: Audio file bytes (WAV or MP3)
            name: Name for the cloned voice
            description: Optional description

        Returns:
            Voice ID for the cloned voice
        """
        # TODO: Implement voice cloning
        # Endpoint: POST /voices:clone

        raise NotImplementedError("Voice cloning not yet implemented")

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def estimate_cost(self, text: str, **kwargs) -> float:
        """
        Estimate the cost of synthesizing text.

        Args:
            text: Text to synthesize

        Returns:
            Estimated cost in USD
        """
        char_count = len(text)
        price_per_char = self.PRICING.get(
            self.inworld_config.model,
            self.PRICING[InworldModel.TTS_1]
        )
        return char_count * price_per_char

    def estimate_duration(self, text: str, speed: float = 1.0) -> float:
        """
        Estimate audio duration for text.

        Args:
            text: Text to synthesize
            speed: Speaking rate

        Returns:
            Estimated duration in seconds
        """
        # Average speaking rate: ~150 words per minute
        words = len(text.split())
        base_duration = words / 150 * 60  # seconds
        return base_duration / speed

    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.

        Returns:
            True if credentials are valid
        """
        try:
            # Try listing voices as a credential check
            await self.list_voices()
            return True
        except Exception:
            return False

    async def close(self):
        """Clean up resources"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def quick_synthesize(
    text: str,
    voice: str = "Hades",
    output_path: Optional[str] = None,
) -> AudioGenerationResult:
    """
    Quick synthesis for simple use cases.

    Example:
        result = await quick_synthesize("Hello world!", "Hades", "output.mp3")
    """
    config = InworldConfig(api_key=os.environ.get("INWORLD_API_KEY", ""))
    async with InworldProvider(config) as provider:
        result = await provider.generate_speech(text, voice_id=voice)

        if output_path and result.success:
            # Would need to save audio data here
            pass

        return result


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        config = InworldConfig(api_key=os.environ.get("INWORLD_API_KEY", ""))
        provider = InworldProvider(config)

        # List voices
        print("Available voices:")
        voices = await provider.list_voices()
        for v in voices[:5]:
            print(f"  - {v['name']} ({v['gender']}, {v['accent']})")

        # Test synthesis
        print("\nSynthesizing test audio...")
        result = await provider.generate_speech(
            "Hello! This is a test of the Inworld TTS provider.",
            voice_id="Hades",
        )
        print(f"Duration: {result.duration:.2f}s")
        print(f"Cost: ${result.cost:.4f}")

        await provider.close()

    asyncio.run(test())
