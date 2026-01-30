"""
ElevenLabs Text-to-Speech Provider Implementation

This module provides integration with ElevenLabs API for text-to-speech generation.
Supports voice selection, voice settings customization, streaming, and model selection.
"""

import asyncio
from typing import Optional, Dict, Any, List, AsyncIterator
import aiohttp
from ..base import AudioProvider, AudioProviderConfig, AudioGenerationResult
from core.secrets import get_api_key


class ElevenLabsProvider(AudioProvider):
    """
    ElevenLabs text-to-speech provider implementation.
    
    Provides high-quality speech synthesis with multiple voices and languages.
    Supports advanced voice control features like stability, similarity boost,
    style control, and speaker boost.
    
    API Documentation: https://api.elevenlabs.io/docs
    """
    
    _is_stub = False
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "eleven_monolingual_v1",
        voice_id: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None,
        **kwargs
    ):
        """
        Initialize ElevenLabs provider.
        
        Args:
            api_key: ElevenLabs API key. If not provided, reads from ELEVENLABS_API_KEY env var
            model: Model ID to use (default: eleven_monolingual_v1)
            voice_id: Default voice ID to use for generation
            stability: Voice stability setting (0-1). Higher = more consistent, lower = more expressive
            similarity_boost: Voice similarity boost (0-1). Higher = closer to original voice
            style: Style exaggeration (0-1). Higher = more expressive variation
            use_speaker_boost: Whether to use speaker boost for improved clarity
            **kwargs: Additional configuration options
        """
        config = AudioProviderConfig(
            api_key=api_key or get_api_key("ELEVENLABS_API_KEY"),
            base_url="https://api.elevenlabs.io",
            **kwargs
        )
        super().__init__(config)
        
        self.model = model
        self.default_voice_id = voice_id
        self.default_voice_settings = {}
        
        if stability is not None:
            self.default_voice_settings["stability"] = stability
        if similarity_boost is not None:
            self.default_voice_settings["similarity_boost"] = similarity_boost
        if style is not None:
            self.default_voice_settings["style"] = style
        if use_speaker_boost is not None:
            self.default_voice_settings["use_speaker_boost"] = use_speaker_boost
    
    @property
    def name(self) -> str:
        """Return provider name."""
        return "elevenlabs"
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for API requests.
        
        Returns:
            Dictionary of headers including authentication
        """
        return {
            "xi-api-key": self.config.api_key,
            "Content-Type": "application/json"
        }
    
    async def generate_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        model: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None,
        output_format: str = "mp3_44100_128",
        stream: bool = False,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Generate speech audio from text using ElevenLabs API.
        
        Args:
            text: Text to convert to speech (max ~5000 characters depending on tier)
            voice_id: Voice ID to use. If not provided, uses default or first available voice
            speed: Speech speed multiplier (note: not directly supported by API, placeholder for interface compatibility)
            model: Model ID to use (e.g., eleven_monolingual_v1, eleven_multilingual_v2, eleven_turbo_v2)
            stability: Voice stability (0-1). Higher = more consistent
            similarity_boost: Voice similarity boost (0-1). Higher = closer to original
            style: Style exaggeration (0-1). Higher = more expressive
            use_speaker_boost: Enable speaker boost for improved clarity
            output_format: Audio output format (default: mp3_44100_128)
            stream: Whether to use streaming endpoint for lower latency
            **kwargs: Additional parameters
            
        Returns:
            AudioGenerationResult containing audio data and metadata
            
        Raises:
            ValueError: If API key is missing or parameters are invalid
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required. Set ELEVENLABS_API_KEY environment variable.")
        
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # Get voice_id
        effective_voice_id = voice_id or self.default_voice_id
        if not effective_voice_id:
            # Get first available voice
            voices = await self.list_voices()
            if not voices:
                raise RuntimeError("No voices available")
            effective_voice_id = voices[0]["voice_id"]
        
        # Build voice settings
        voice_settings = dict(self.default_voice_settings)
        if stability is not None:
            voice_settings["stability"] = max(0.0, min(1.0, stability))
        if similarity_boost is not None:
            voice_settings["similarity_boost"] = max(0.0, min(1.0, similarity_boost))
        if style is not None:
            voice_settings["style"] = max(0.0, min(1.0, style))
        if use_speaker_boost is not None:
            voice_settings["use_speaker_boost"] = use_speaker_boost
        
        # Build request body
        request_body = {
            "text": text,
            "model_id": model or self.model
        }
        
        if voice_settings:
            request_body["voice_settings"] = voice_settings
        
        # Choose endpoint based on stream parameter
        endpoint = "stream" if stream else ""
        path = f"/v1/text-to-speech/{effective_voice_id}"
        if endpoint:
            path += f"/{endpoint}"
        
        url = f"{self.config.base_url}{path}"
        
        # Add output format as query parameter
        if output_format:
            url += f"?output_format={output_format}"
        
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                audio_data = await response.read()
                
                # Calculate character count for metadata
                character_count = len(text)
                
                return AudioGenerationResult(
                    success=True,
                    audio_data=audio_data,
                    format="mp3",
                    sample_rate=44100,
                    duration=None,  # ElevenLabs doesn't provide duration in response
                    provider_metadata={
                        "provider": self.name,
                        "voice_id": effective_voice_id,
                        "model": model or self.model,
                        "character_count": character_count,
                        "voice_settings": voice_settings,
                        "output_format": output_format
                    }
                )
    
    async def generate_speech_stream(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None,
        **kwargs
    ) -> AsyncIterator[bytes]:
        """
        Stream speech audio from text using ElevenLabs streaming API.
        
        Yields audio chunks as they are generated for lower latency.
        
        Args:
            text: Text to convert to speech
            voice_id: Voice ID to use
            model: Model ID to use
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            style: Style exaggeration (0-1)
            use_speaker_boost: Enable speaker boost
            **kwargs: Additional parameters
            
        Yields:
            Audio data chunks as bytes
            
        Raises:
            ValueError: If API key is missing or parameters are invalid
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        # Get voice_id
        effective_voice_id = voice_id or self.default_voice_id
        if not effective_voice_id:
            voices = await self.list_voices()
            if not voices:
                raise RuntimeError("No voices available")
            effective_voice_id = voices[0]["voice_id"]
        
        # Build voice settings
        voice_settings = dict(self.default_voice_settings)
        if stability is not None:
            voice_settings["stability"] = max(0.0, min(1.0, stability))
        if similarity_boost is not None:
            voice_settings["similarity_boost"] = max(0.0, min(1.0, similarity_boost))
        if style is not None:
            voice_settings["style"] = max(0.0, min(1.0, style))
        if use_speaker_boost is not None:
            voice_settings["use_speaker_boost"] = use_speaker_boost
        
        # Build request body
        request_body = {
            "text": text,
            "model_id": model or self.model
        }
        
        if voice_settings:
            request_body["voice_settings"] = voice_settings
        
        url = f"{self.config.base_url}/v1/text-to-speech/{effective_voice_id}/stream"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs streaming API error (status {response.status}): {error_text}"
                    )
                
                async for chunk in response.content.iter_any():
                    if chunk:
                        yield chunk
    
    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        Retrieve list of available ElevenLabs voices.
        
        Returns:
List of voice dictionaries containing:
                - voice_id: Unique voice identifier
                - name: Human-readable voice name
                - category: Voice category (e.g., premade, cloned)
                - labels: Additional metadata about the voice
                - preview_url: URL to preview audio sample
                
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        url = f"{self.config.base_url}/v1/voices"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                data = await response.json()
                return data.get("voices", [])
    
    async def get_voice(self, voice_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific voice.
        
        Args:
            voice_id: The voice ID to retrieve
            
        Returns:
            Dictionary containing voice details including:
                - voice_id: Voice identifier
                - name: Voice name
                - samples: Audio samples
                - category: Voice category
                - settings: Default voice settings
                
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        url = f"{self.config.base_url}/v1/voices/{voice_id}"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                return await response.json()
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """
        Get list of available ElevenLabs models.
        
        Returns:
            List of model dictionaries containing:
                - model_id: Model identifier
                - name: Model name
                - description: Model description
                - languages: Supported languages
                
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        url = f"{self.config.base_url}/v1/models"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                data = await response.json()
                return data.get("models", [])
    
    async def get_user_subscription(self) -> Dict[str, Any]:
        """
        Get user subscription information and usage limits.
        
        Returns:
            Dictionary containing:
                - character_count: Characters used this period
                - character_limit: Total character limit for period
                - status: Subscription status
                - next_character_count_reset_unix: When usage resets
                
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        url = f"{self.config.base_url}/v1/user/subscription"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                return await response.json()
    
    async def get_history(self) -> List[Dict[str, Any]]:
        """
        Get history of generated audio.
        
        Returns:
            List of history items containing:
                - history_item_id: Unique identifier
                - text: Original text used
                - voice_id: Voice used
                - date_unix: Generation timestamp
                - character_count_change_from: Characters used
                
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        url = f"{self.config.base_url}/v1/history"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs API error (status {response.status}): {error_text}"
                    )
                
                data = await response.json()
                return data.get("history", [])
    
    async def speech_to_speech(
        self,
        audio_data: bytes,
        voice_id: str,
        model: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Convert audio to speech in a different voice.
        
        Args:
            audio_data: Input audio data as bytes
            voice_id: Target voice ID to convert to
            model: Model ID to use
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            **kwargs: Additional parameters
            
        Returns:
            AudioGenerationResult containing converted audio
            
        Raises:
            ValueError: If API key is missing or parameters are invalid
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError("ElevenLabs API key is required.")
        
        if not audio_data:
            raise ValueError("Audio data cannot be empty")
        
        # Build voice settings
        voice_settings = dict(self.default_voice_settings)
        if stability is not None:
            voice_settings["stability"] = max(0.0, min(1.0, stability))
        if similarity_boost is not None:
            voice_settings["similarity_boost"] = max(0.0, min(1.0, similarity_boost))
        
        url = f"{self.config.base_url}/v1/speech-to-speech/{voice_id}"
        
        # Prepare multipart form data
        form = aiohttp.FormData()
        form.add_field('audio', audio_data, filename='audio.mp3', content_type='audio/mpeg')
        form.add_field('model_id', model or self.model)
        
        if voice_settings:
            import json
            form.add_field('voice_settings', json.dumps(voice_settings))
        
        headers = {
            "xi-api-key": self.config.api_key
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=form,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"ElevenLabs speech-to-speech API error (status {response.status}): {error_text}"
                    )
                
                output_audio = await response.read()
                
                return AudioGenerationResult(
                    success=True,
                    audio_data=output_audio,
                    format="mp3",
                    sample_rate=44100,
                    duration=None,
                    provider_metadata={
                        "provider": self.name,
                        "voice_id": voice_id,
                        "model": model or self.model,
                        "voice_settings": voice_settings,
                        "conversion_type": "speech_to_speech"
                    }
                )
    
    async def validate_credentials(self) -> bool:
        """
        Validate that the ElevenLabs API key is valid and working.
        
        Makes a test API call to verify authentication.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        if not self.config.api_key:
            return False
        
        try:
            # Try to get user subscription info as a lightweight validation call
            await self.get_user_subscription()
            return True
        except Exception:
            return False
    
    def estimate_cost(self, text: str, **kwargs) -> float:
        """
        Estimate the cost of generating speech for the given text.
        
        ElevenLabs pricing is approximately $0.30 per 1K characters.
        Actual pricing varies by subscription tier.
        
        Args:
            text: Text to estimate cost for
            **kwargs: Additional parameters (unused)
            
        Returns:
            Estimated cost in USD
        """
        character_count = len(text)
        cost_per_1k_chars = 0.30
        return (character_count / 1000.0) * cost_per_1k_chars