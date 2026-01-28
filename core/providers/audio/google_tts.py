"""
Google Cloud Text-to-Speech Provider Implementation

This module provides integration with Google Cloud Text-to-Speech API for speech synthesis.
Supports synchronous and asynchronous synthesis, multiple voices, languages, and audio formats.
"""

import os
import asyncio
import base64
from typing import Optional, Dict, Any, List
import aiohttp
from ..base import AudioProvider, AudioProviderConfig, AudioGenerationResult


class GoogleTTSProvider(AudioProvider):
    """
    Google Cloud Text-to-Speech provider implementation.

    Provides high-quality speech synthesis with support for multiple languages,
    voice types (Standard, WaveNet, Neural2, Studio, Polyglot), and audio formats.

    API Documentation: https://cloud.google.com/text-to-speech/docs
    """

    _is_stub = False

    # API endpoint
    API_URL = "https://texttospeech.googleapis.com/v1"

    def __init__(self, config: Optional[AudioProviderConfig] = None):
        """
        Initialize Google Cloud Text-to-Speech provider.

        Args:
            config: Provider configuration. If None, creates default config
                   using GOOGLE_CLOUD_API_KEY from environment.
        """
        if config is None:
            api_key = os.getenv("GOOGLE_CLOUD_API_KEY")
            config = AudioProviderConfig(api_key=api_key)

        if not config.api_key:
            raise ValueError(
                "Google Cloud API key required. Set GOOGLE_CLOUD_API_KEY environment variable."
            )

        super().__init__(config)

        # Default settings
        self.default_voice_name = "en-US-Neural2-A"
        self.default_language_code = "en-US"
        self.default_ssml_gender = "NEUTRAL"
        self.default_audio_encoding = "MP3"
        self.default_speaking_rate = 1.0
        self.default_pitch = 0.0
        self.default_volume_gain_db = 0.0
        self.default_sample_rate_hertz = None
        self.default_effects_profile_id = []
    
    @property
    def name(self) -> str:
        """Return provider name."""
        return "google_tts"
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for API requests.
        
        Returns:
            Dictionary of headers including authentication
        """
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
    
    def _build_voice_config(
        self,
        voice_name: Optional[str],
        language_code: Optional[str],
        ssml_gender: Optional[str]
    ) -> Dict[str, Any]:
        """
        Build voice configuration object.
        
        Args:
            voice_name: Specific voice name
            language_code: Language code
            ssml_gender: Voice gender
            
        Returns:
            Voice configuration dictionary
        """
        voice_config = {
            "languageCode": language_code or self.default_language_code
        }
        
        if voice_name:
            voice_config["name"] = voice_name
        elif self.default_voice_name:
            voice_config["name"] = self.default_voice_name
        
        gender = ssml_gender or self.default_ssml_gender
        if gender:
            voice_config["ssmlGender"] = gender
        
        return voice_config
    
    def _build_audio_config(
        self,
        audio_encoding: Optional[str],
        speaking_rate: Optional[float],
        pitch: Optional[float],
        volume_gain_db: Optional[float],
        sample_rate_hertz: Optional[int],
        effects_profile_id: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Build audio configuration object.
        
        Args:
            audio_encoding: Output format
            speaking_rate: Speech speed
            pitch: Voice pitch
            volume_gain_db: Volume adjustment
            sample_rate_hertz: Sample rate
            effects_profile_id: Audio effects profiles
            
        Returns:
            Audio configuration dictionary
        """
        audio_config = {
            "audioEncoding": audio_encoding or self.default_audio_encoding
        }
        
        rate = speaking_rate if speaking_rate is not None else self.default_speaking_rate
        audio_config["speakingRate"] = max(0.25, min(4.0, rate))
        
        p = pitch if pitch is not None else self.default_pitch
        audio_config["pitch"] = max(-20.0, min(20.0, p))
        
        vol = volume_gain_db if volume_gain_db is not None else self.default_volume_gain_db
        audio_config["volumeGainDb"] = max(-96.0, min(16.0, vol))
        
        if sample_rate_hertz is not None:
            audio_config["sampleRateHertz"] = sample_rate_hertz
        elif self.default_sample_rate_hertz is not None:
            audio_config["sampleRateHertz"] = self.default_sample_rate_hertz
        
        effects = effects_profile_id if effects_profile_id is not None else self.default_effects_profile_id
        if effects:
            audio_config["effectsProfileId"] = effects
        
        return audio_config
    
    async def generate_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        ssml: bool = False,
        language_code: Optional[str] = None,
        ssml_gender: Optional[str] = None,
        audio_encoding: Optional[str] = None,
        pitch: Optional[float] = None,
        volume_gain_db: Optional[float] = None,
        sample_rate_hertz: Optional[int] = None,
        effects_profile_id: Optional[List[str]] = None,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Generate speech audio from text using Google Cloud Text-to-Speech API.
        
        Args:
            text: Text or SSML to convert to speech (max 5000 bytes UTF-8 for sync)
            voice_id: Voice name (e.g., en-US-Neural2-A, en-US-Wavenet-B)
            speed: Speech speed multiplier (0.25 to 4.0, default 1.0)
            ssml: Whether input text is SSML markup
            language_code: Language code (e.g., en-US, es-ES)
            ssml_gender: Voice gender (MALE, FEMALE, NEUTRAL)
            audio_encoding: Output format (LINEAR16, MP3, OGG_OPUS, MULAW, ALAW)
            pitch: Voice pitch adjustment (-20.0 to 20.0)
            volume_gain_db: Volume adjustment (-96.0 to 16.0)
            sample_rate_hertz: Sample rate in Hz
            effects_profile_id: Audio effects profiles list
            **kwargs: Additional parameters
            
        Returns:
            AudioGenerationResult containing audio data and metadata
            
        Raises:
            ValueError: If API key is missing or parameters are invalid
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError(
                "Google Cloud API key is required. Set GOOGLE_CLOUD_API_KEY environment variable."
            )
        
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # Check text length (5000 bytes for sync synthesis)
        text_bytes = text.encode('utf-8')
        if len(text_bytes) > 5000:
            raise ValueError(
                f"Text too long ({len(text_bytes)} bytes). "
                "Maximum 5000 bytes for synchronous synthesis. "
                "Use synthesizeLongAudio for longer texts."
            )
        
        # Build request body
        input_config = {}
        if ssml:
            input_config["ssml"] = text
        else:
            input_config["text"] = text
        
        voice_config = self._build_voice_config(
            voice_name=voice_id,
            language_code=language_code,
            ssml_gender=ssml_gender
        )
        
        audio_config = self._build_audio_config(
            audio_encoding=audio_encoding,
            speaking_rate=speed,
            pitch=pitch,
            volume_gain_db=volume_gain_db,
            sample_rate_hertz=sample_rate_hertz,
            effects_profile_id=effects_profile_id
        )
        
        request_body = {
            "input": input_config,
            "voice": voice_config,
            "audioConfig": audio_config
        }
        
        url = f"{self.API_URL}/text:synthesize"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Google Cloud TTS API error (status {response.status}): {error_text}"
                    )
                
                response_data = await response.json()
                
                # Decode base64 audio content
                audio_content_b64 = response_data.get("audioContent")
                if not audio_content_b64:
                    raise RuntimeError("No audio content in response")
                
                audio_data = base64.b64decode(audio_content_b64)
                
                # Determine format from audio encoding
                encoding = audio_config["audioEncoding"]
                format_map = {
                    "MP3": "mp3",
                    "OGG_OPUS": "ogg",
                    "LINEAR16": "wav",
                    "MULAW": "wav",
                    "ALAW": "wav"
                }
                audio_format = format_map.get(encoding, "mp3")
                
                # Calculate character count
                character_count = len(text)
                
                return AudioGenerationResult(
                    success=True,
                    audio_data=audio_data,
                    format=audio_format,
                    sample_rate=audio_config.get("sampleRateHertz", 24000),
                    duration=None,
                    provider_metadata={
                        "provider": self.name,
"voice": voice_config,
                        "audio_config": audio_config,
                        "character_count": character_count,
                        "input_type": "ssml" if ssml else "text"
                    }
                )
    
    async def generate(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Alias for generate_speech for CLI compatibility.
        
        Args:
            text: Text to convert to speech
            voice_id: Voice name
            speed: Speech speed
            **kwargs: Additional parameters
            
        Returns:
            AudioGenerationResult
        """
        return await self.generate_speech(
            text=text,
            voice_id=voice_id,
            speed=speed,
            **kwargs
        )
    
    async def list_voices(
        self,
        language_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List available voices for synthesis.
        
        Args:
            language_code: Optional language code to filter voices (e.g., en-US)
            
        Returns:
            List of voice information dictionaries
            
        Raises:
            ValueError: If API key is missing
            RuntimeError: If API request fails
        """
        if not self.config.api_key:
            raise ValueError(
                "Google Cloud API key is required. Set GOOGLE_CLOUD_API_KEY environment variable."
            )
        
        url = f"{self.API_URL}/voices"
        if language_code:
            url += f"?languageCode={language_code}"
        
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
                        f"Google Cloud TTS API error (status {response.status}): {error_text}"
                    )
                
                response_data = await response.json()
                voices = response_data.get("voices", [])
                
                # Format voice information
                formatted_voices = []
                for voice in voices:
                    formatted_voices.append({
                        "voice_id": voice.get("name"),
                        "name": voice.get("name"),
                        "language_codes": voice.get("languageCodes", []),
                        "ssml_gender": voice.get("ssmlGender"),
                        "natural_sample_rate_hertz": voice.get("naturalSampleRateHertz")
                    })
                
                return formatted_voices
    
    async def synthesize_long_audio(
        self,
        text: str,
        output_gcs_uri: str,
        parent: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        ssml: bool = False,
        language_code: Optional[str] = None,
        ssml_gender: Optional[str] = None,
        audio_encoding: Optional[str] = None,
        pitch: Optional[float] = None,
        volume_gain_db: Optional[float] = None,
        sample_rate_hertz: Optional[int] = None,
        effects_profile_id: Optional[List[str]] = None,
        poll_interval: int = 5,
        max_wait_time: int = 600,
        **kwargs
    ) -> AudioGenerationResult:
        """
        Synthesize long-form audio asynchronously (for texts over 5000 characters).
        
        Args:
            text: Text or SSML to convert to speech
            output_gcs_uri: Google Cloud Storage URI for output (e.g., gs://bucket/output.mp3)
            parent: Project location (e.g., projects/PROJECT_ID/locations/LOCATION)
            voice_id: Voice name
            speed: Speech speed multiplier (0.25 to 4.0)
            ssml: Whether input text is SSML markup
            language_code: Language code
            ssml_gender: Voice gender
            audio_encoding: Output format
            pitch: Voice pitch adjustment
            volume_gain_db: Volume adjustment
            sample_rate_hertz: Sample rate in Hz
            effects_profile_id: Audio effects profiles list
            poll_interval: Seconds between status polls (default 5)
            max_wait_time: Maximum wait time in seconds (default 600)
            **kwargs: Additional parameters
            
        Returns:
            AudioGenerationResult with GCS URI in metadata
            
        Raises:
            ValueError: If API key is missing or parameters are invalid
            RuntimeError: If API request fails or operation times out
        """
        if not self.config.api_key:
            raise ValueError(
                "Google Cloud API key is required. Set GOOGLE_CLOUD_API_KEY environment variable."
            )
        
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not output_gcs_uri.startswith("gs://"):
            raise ValueError("output_gcs_uri must be a valid GCS URI (gs://bucket/path)")
        
        # Build request body
        input_config = {}
        if ssml:
            input_config["ssml"] = text
        else:
            input_config["text"] = text
        
        voice_config = self._build_voice_config(
            voice_name=voice_id,
            language_code=language_code,
            ssml_gender=ssml_gender
        )
        
        audio_config = self._build_audio_config(
            audio_encoding=audio_encoding,
            speaking_rate=speed,
            pitch=pitch,
            volume_gain_db=volume_gain_db,
            sample_rate_hertz=sample_rate_hertz,
            effects_profile_id=effects_profile_id
        )
        
        request_body = {
            "parent": parent,
            "input": input_config,
            "voice": voice_config,
            "audioConfig": audio_config,
            "outputGcsUri": output_gcs_uri
        }
        
        url = f"{self.API_URL}/text:synthesizeLongAudio"
        headers = self._get_headers()
        
        async with aiohttp.ClientSession() as session:
            # Submit long audio synthesis job
            async with session.post(
                url,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Google Cloud TTS API error (status {response.status}): {error_text}"
                    )
                
                operation_data = await response.json()
                operation_name = operation_data.get("name")
                
                if not operation_name:
                    raise RuntimeError("No operation name in response")
            
            # Poll for completion
            operation_url = f"{self.API_URL}/{operation_name}"
            start_time = asyncio.get_event_loop().time()
            
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait_time:
                    raise RuntimeError(
                        f"Long audio synthesis timed out after {max_wait_time} seconds"
                    )
                
                async with session.get(
                    operation_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"Operation status check failed (status {response.status}): {error_text}"
                        )
                    
                    operation_status = await response.json()
                    
                    if operation_status.get("done"):
                        # Check for errors
                        if "error" in operation_status:
                            error = operation_status["error"]
                            raise RuntimeError(
                                f"Long audio synthesis failed: {error.get('message', 'Unknown error')}"
                            )
                        
                        # Success
                        return AudioGenerationResult(
                            success=True,
                            audio_url=output_gcs_uri,
                            format=audio_config["audioEncoding"].lower(),
                            sample_rate=audio_config.get("sampleRateHertz", 24000),
                            duration=None,
                            provider_metadata={
                                "provider": self.name,
                                "operation_name": operation_name,
                                "output_gcs_uri": output_gcs_uri,
                                "voice": voice_config,
                                "audio_config": audio_config,
                                "character_count": len(text),
                                "input_type": "ssml" if ssml else "text"
                            }
                        )
                
                # Wait before next poll
                await asyncio.sleep(poll_interval)
    
    def estimate_cost(
        self,
        text: str,
        voice_type: str = "Neural2",
        **kwargs
    ) -> float:
        """
        Estimate cost for generating speech from text.
        
        Pricing (as of 2024):
        - Standard voices: $4 per 1 million characters
        - WaveNet/Neural2 voices: $16 per 1 million characters
        - Studio voices: $64 per 1 million characters
        
        Args:
            text: Text to be spoken
            voice_type: Voice type (Standard, WaveNet, Neural2, Studio, Polyglot)
            **kwargs: Additional parameters
            
        Returns:
            Estimated cost in USD
        """
        character_count = len(text)
        
        # Pricing per million characters
        price_map = {
            "Standard": 4.00,
            "WaveNet": 16.00,
            "Neural2": 16.00,
            "Studio": 64.00,
            "Polyglot": 16.00
        }
        
        price_per_million = price_map.get(voice_type, 16.00)
        cost = (character_count / 1_000_000) * price_per_million
        
        return round(cost, 6)
    
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are working.
        
        Returns:
            True if credentials are valid
        """
        try:
            # Try to list voices as a simple validation
            voices = await self.list_voices()
            return len(voices) > 0
        except Exception:
            return False