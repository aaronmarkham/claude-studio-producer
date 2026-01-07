# Providers Implementation Specification

## Overview

This document defines all provider implementations needed for video, audio, music, and storage services. Each provider implements the abstract interface from `core/providers/base.py`.

## Directory Structure

```
core/providers/
├── __init__.py
├── base.py                    # Abstract interfaces (exists)
│
├── video/
│   ├── __init__.py
│   ├── runway.py              # Runway Gen-3 Alpha
│   ├── pika.py                # Pika Labs
│   ├── stability.py           # Stability AI Video
│   ├── luma.py                # Luma AI Dream Machine
│   └── kling.py               # Kling AI
│
├── audio/
│   ├── __init__.py
│   ├── elevenlabs.py          # ElevenLabs TTS
│   ├── openai_tts.py          # OpenAI TTS
│   └── google_tts.py          # Google Cloud TTS
│
├── music/
│   ├── __init__.py
│   ├── mubert.py              # Mubert AI music
│   ├── soundraw.py            # Soundraw AI music
│   └── suno.py                # Suno AI music
│
├── sfx/
│   ├── __init__.py
│   ├── freesound.py           # Freesound (free)
│   └── elevenlabs_sfx.py      # ElevenLabs sound effects
│
├── image/
│   ├── __init__.py
│   ├── dalle.py               # OpenAI DALL-E 3
│   ├── midjourney.py          # Midjourney (via API proxy)
│   └── stability_image.py     # Stability AI images
│
└── storage/
    ├── __init__.py
    ├── local.py               # Local filesystem
    └── s3.py                  # AWS S3
```

## Video Providers

### runway.py - Runway Gen-3 Alpha

```python
"""Runway Gen-3 Alpha video generation provider"""

import os
import asyncio
import httpx
from typing import Dict, Any

from ..base import VideoProvider, GeneratedVideo


class RunwayProvider(VideoProvider):
    """
    Runway Gen-3 Alpha - High quality photorealistic video
    
    Features:
    - Text-to-video and image-to-video
    - 5-10 second clips
    - 720p and 1080p output
    - Motion brush for controlled animation
    
    Pricing (as of 2025):
    - Gen-3 Alpha: ~$0.50/second
    - Gen-3 Alpha Turbo: ~$0.25/second
    """
    
    BASE_URL = "https://api.runwayml.com/v1"
    
    def __init__(self, model: str = "gen3a_turbo"):
        """
        Args:
            model: "gen3a_turbo" (fast, cheaper) or "gen3a" (higher quality)
        """
        self.api_key = os.getenv("RUNWAY_API_KEY")
        self.model = model
        self._cost_per_second = 0.25 if "turbo" in model else 0.50
        
        if not self.api_key:
            raise ValueError("RUNWAY_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "runway"
    
    @property
    def cost_per_second(self) -> float:
        return self._cost_per_second
    
    async def generate(
        self,
        prompt: str,
        duration: float,
        width: int = 1280,
        height: int = 768,
        **kwargs
    ) -> GeneratedVideo:
        """Generate video from text prompt"""
        
        # Runway max duration is 10 seconds
        duration = min(duration, 10.0)
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Start generation job
            response = await client.post(
                f"{self.BASE_URL}/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "duration": int(duration),
                    "width": width,
                    "height": height,
                    "seed": kwargs.get("seed"),
                }
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data["id"]
            
            # Poll for completion
            video_url = await self._wait_for_completion(client, job_id)
            
            return GeneratedVideo(
                video_id=job_id,
                video_url=video_url,
                duration=duration,
                width=width,
                height=height,
                format="mp4",
                generation_cost=duration * self._cost_per_second,
                provider=self.name,
                metadata={"model": self.model, "prompt": prompt[:200]}
            )
    
    async def _wait_for_completion(
        self, 
        client: httpx.AsyncClient, 
        job_id: str,
        max_wait: int = 300,
        poll_interval: int = 5
    ) -> str:
        """Poll until generation completes"""
        
        elapsed = 0
        while elapsed < max_wait:
            status = await self.check_status(job_id)
            
            if status["status"] == "completed":
                return status["output_url"]
            elif status["status"] == "failed":
                raise Exception(f"Generation failed: {status.get('error')}")
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        raise TimeoutError(f"Generation timed out after {max_wait}s")
    
    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check generation job status"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/generations/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            return response.json()
    
    async def download(self, video_url: str, local_path: str) -> str:
        """Download video to local path"""
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            response.raise_for_status()
            
            with open(local_path, "wb") as f:
                f.write(response.content)
            
            return local_path
```

### pika.py - Pika Labs

```python
"""Pika Labs video generation provider"""

import os
import asyncio
import httpx
from typing import Dict, Any

from ..base import VideoProvider, GeneratedVideo


class PikaProvider(VideoProvider):
    """
    Pika Labs - Stylized and animated video generation
    
    Features:
    - Text-to-video and image-to-video
    - 3-4 second clips
    - Great for stylized/animated content
    - Lip sync capabilities
    
    Pricing (as of 2025):
    - ~$0.20/second
    """
    
    BASE_URL = "https://api.pika.art/v1"
    
    def __init__(self):
        self.api_key = os.getenv("PIKA_API_KEY")
        if not self.api_key:
            raise ValueError("PIKA_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "pika"
    
    @property
    def cost_per_second(self) -> float:
        return 0.20
    
    async def generate(
        self,
        prompt: str,
        duration: float,
        width: int = 1024,
        height: int = 576,
        **kwargs
    ) -> GeneratedVideo:
        """Generate video from text prompt"""
        
        # Pika max duration is 4 seconds
        duration = min(duration, 4.0)
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/generate",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "prompt": prompt,
                    "duration": duration,
                    "width": width,
                    "height": height,
                    "style": kwargs.get("style", "default"),
                }
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data["id"]
            
            # Poll for completion
            video_url = await self._wait_for_completion(client, job_id)
            
            return GeneratedVideo(
                video_id=job_id,
                video_url=video_url,
                duration=duration,
                width=width,
                height=height,
                format="mp4",
                generation_cost=duration * self.cost_per_second,
                provider=self.name,
                metadata={"prompt": prompt[:200]}
            )
    
    async def _wait_for_completion(self, client, job_id: str) -> str:
        """Poll until generation completes"""
        for _ in range(60):  # Max 5 minutes
            status = await self.check_status(job_id)
            if status["status"] == "completed":
                return status["video_url"]
            elif status["status"] == "failed":
                raise Exception(f"Generation failed: {status.get('error')}")
            await asyncio.sleep(5)
        raise TimeoutError("Generation timed out")
    
    async def check_status(self, job_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/status/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()
    
    async def download(self, video_url: str, local_path: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            with open(local_path, "wb") as f:
                f.write(response.content)
            return local_path
```

### stability.py - Stability AI Video

```python
"""Stability AI video generation provider"""

import os
import httpx
from ..base import VideoProvider, GeneratedVideo


class StabilityVideoProvider(VideoProvider):
    """
    Stability AI - Stable Video Diffusion
    
    Features:
    - Image-to-video (requires input image)
    - 2-4 second clips
    - Good for motion graphics and abstract
    
    Pricing (as of 2025):
    - ~$0.10/second
    """
    
    BASE_URL = "https://api.stability.ai/v2beta"
    
    def __init__(self):
        self.api_key = os.getenv("STABILITY_API_KEY")
        if not self.api_key:
            raise ValueError("STABILITY_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "stability"
    
    @property
    def cost_per_second(self) -> float:
        return 0.10
    
    async def generate(
        self,
        prompt: str,
        duration: float,
        width: int = 1024,
        height: int = 576,
        **kwargs
    ) -> GeneratedVideo:
        """Generate video - requires input_image in kwargs"""
        
        input_image = kwargs.get("input_image")
        if not input_image:
            raise ValueError("Stability Video requires input_image")
        
        duration = min(duration, 4.0)
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            # Stability uses multipart form data
            files = {"image": open(input_image, "rb")}
            data = {
                "seed": kwargs.get("seed", 0),
                "cfg_scale": kwargs.get("cfg_scale", 2.5),
                "motion_bucket_id": kwargs.get("motion_bucket_id", 40),
            }
            
            response = await client.post(
                f"{self.BASE_URL}/image-to-video",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                data=data
            )
            response.raise_for_status()
            result = response.json()
            
            return GeneratedVideo(
                video_id=result["id"],
                video_url=result["video_url"],
                duration=duration,
                width=width,
                height=height,
                format="mp4",
                generation_cost=duration * self.cost_per_second,
                provider=self.name
            )
    
    async def check_status(self, job_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/results/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()
    
    async def download(self, video_url: str, local_path: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            with open(local_path, "wb") as f:
                f.write(response.content)
            return local_path
```

### luma.py - Luma AI Dream Machine

```python
"""Luma AI Dream Machine video generation provider"""

import os
import httpx
from ..base import VideoProvider, GeneratedVideo


class LumaProvider(VideoProvider):
    """
    Luma AI Dream Machine - High quality video generation
    
    Features:
    - Text-to-video and image-to-video
    - 5 second clips
    - Excellent camera motion control
    - Good for cinematic shots
    
    Pricing (as of 2025):
    - ~$0.30/second
    """
    
    BASE_URL = "https://api.lumalabs.ai/v1"
    
    def __init__(self):
        self.api_key = os.getenv("LUMA_API_KEY")
        if not self.api_key:
            raise ValueError("LUMA_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "luma"
    
    @property
    def cost_per_second(self) -> float:
        return 0.30
    
    async def generate(
        self,
        prompt: str,
        duration: float,
        width: int = 1280,
        height: int = 720,
        **kwargs
    ) -> GeneratedVideo:
        """Generate video from text prompt"""
        
        duration = min(duration, 5.0)
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "prompt": prompt,
                    "aspect_ratio": f"{width}:{height}",
                    "loop": kwargs.get("loop", False),
                    "keyframes": kwargs.get("keyframes"),  # For camera control
                }
            )
            response.raise_for_status()
            result = response.json()
            
            # Poll for completion
            video_url = await self._wait_for_completion(client, result["id"])
            
            return GeneratedVideo(
                video_id=result["id"],
                video_url=video_url,
                duration=duration,
                width=width,
                height=height,
                format="mp4",
                generation_cost=duration * self.cost_per_second,
                provider=self.name
            )
    
    async def _wait_for_completion(self, client, job_id: str) -> str:
        import asyncio
        for _ in range(60):
            status = await self.check_status(job_id)
            if status["state"] == "completed":
                return status["video"]["url"]
            elif status["state"] == "failed":
                raise Exception(f"Generation failed")
            await asyncio.sleep(5)
        raise TimeoutError("Generation timed out")
    
    async def check_status(self, job_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/generations/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()
    
    async def download(self, video_url: str, local_path: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            with open(local_path, "wb") as f:
                f.write(response.content)
            return local_path
```

### kling.py - Kling AI

```python
"""Kling AI video generation provider"""

import os
import httpx
from ..base import VideoProvider, GeneratedVideo


class KlingProvider(VideoProvider):
    """
    Kling AI - High quality Chinese video model
    
    Features:
    - Text-to-video and image-to-video
    - Up to 10 second clips
    - Good motion and physics
    
    Pricing (as of 2025):
    - ~$0.15/second (Standard)
    - ~$0.30/second (Pro)
    """
    
    BASE_URL = "https://api.klingai.com/v1"
    
    def __init__(self, mode: str = "standard"):
        self.api_key = os.getenv("KLING_API_KEY")
        self.mode = mode
        self._cost = 0.15 if mode == "standard" else 0.30
        
        if not self.api_key:
            raise ValueError("KLING_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "kling"
    
    @property
    def cost_per_second(self) -> float:
        return self._cost
    
    async def generate(
        self,
        prompt: str,
        duration: float,
        width: int = 1280,
        height: int = 720,
        **kwargs
    ) -> GeneratedVideo:
        """Generate video from text prompt"""
        
        duration = min(duration, 10.0)
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/video/generate",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "prompt": prompt,
                    "duration": duration,
                    "mode": self.mode,
                }
            )
            response.raise_for_status()
            result = response.json()
            
            return GeneratedVideo(
                video_id=result["task_id"],
                video_url=result["video_url"],
                duration=duration,
                width=width,
                height=height,
                format="mp4",
                generation_cost=duration * self._cost,
                provider=self.name
            )
    
    async def check_status(self, job_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/video/status/{job_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()
    
    async def download(self, video_url: str, local_path: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            with open(local_path, "wb") as f:
                f.write(response.content)
            return local_path
```

## Audio Providers

### elevenlabs.py - ElevenLabs TTS

```python
"""ElevenLabs text-to-speech provider"""

import os
import httpx
from typing import List, Dict, Any

from ..base import AudioProvider, GeneratedAudio


class ElevenLabsProvider(AudioProvider):
    """
    ElevenLabs - Premium AI voice synthesis
    
    Features:
    - Ultra-realistic voices
    - Voice cloning
    - Multilingual support
    - Emotion control
    
    Pricing (as of 2025):
    - ~$0.30 per 1K characters
    """
    
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    # Default voice IDs
    VOICES = {
        "professional_male": "pNInz6obpgDQGcFmaJgB",     # Adam
        "professional_female": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        "casual_male": "TxGEqnHWrfWFTfGW9XjX",          # Josh
        "casual_female": "EXAVITQu4vr4xnSDxMaL",        # Sarah
        "narrator": "VR6AewLTigWG4xSOukaG",              # Arnold
    }
    
    def __init__(self, voice_id: str = None):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.default_voice = voice_id or self.VOICES["professional_male"]
        
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "elevenlabs"
    
    async def generate_speech(
        self,
        text: str,
        voice_id: str = None,
        speed: float = 1.0,
        **kwargs
    ) -> GeneratedAudio:
        """Generate speech from text"""
        
        voice_id = voice_id or self.default_voice
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text,
                    "model_id": kwargs.get("model_id", "eleven_multilingual_v2"),
                    "voice_settings": {
                        "stability": kwargs.get("stability", 0.5),
                        "similarity_boost": kwargs.get("similarity_boost", 0.75),
                        "style": kwargs.get("style", 0.5),
                        "use_speaker_boost": kwargs.get("speaker_boost", True)
                    }
                }
            )
            response.raise_for_status()
            
            # Response is audio bytes
            audio_bytes = response.content
            
            # Estimate duration (~150 words per minute)
            word_count = len(text.split())
            estimated_duration = (word_count / 150) * 60 / speed
            
            # Calculate cost (~$0.30 per 1K chars)
            cost = (len(text) / 1000) * 0.30
            
            # For real implementation, save to file/storage and return URL
            audio_id = f"el_{hash(text) % 100000}"
            
            return GeneratedAudio(
                audio_id=audio_id,
                audio_url=f"file://{audio_id}.mp3",  # Would be real URL
                duration=estimated_duration,
                format="mp3",
                sample_rate=44100,
                channels=1,
                generation_cost=cost,
                provider=self.name,
                metadata={
                    "voice_id": voice_id,
                    "char_count": len(text),
                    "word_count": word_count
                }
            )
    
    async def list_voices(self) -> List[Dict[str, Any]]:
        """List available voices"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/voices",
                headers={"xi-api-key": self.api_key}
            )
            response.raise_for_status()
            return response.json()["voices"]
```

### openai_tts.py - OpenAI TTS

```python
"""OpenAI text-to-speech provider"""

import os
import httpx
from typing import List, Dict, Any

from ..base import AudioProvider, GeneratedAudio


class OpenAITTSProvider(AudioProvider):
    """
    OpenAI TTS - Fast, affordable voice synthesis
    
    Features:
    - 6 built-in voices
    - Fast generation
    - Good quality for the price
    
    Pricing (as of 2025):
    - TTS-1: ~$0.015 per 1K characters
    - TTS-1-HD: ~$0.030 per 1K characters
    """
    
    BASE_URL = "https://api.openai.com/v1"
    
    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def __init__(self, model: str = "tts-1"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = model
        self._cost_per_1k = 0.015 if model == "tts-1" else 0.030
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "openai_tts"
    
    async def generate_speech(
        self,
        text: str,
        voice_id: str = "alloy",
        speed: float = 1.0,
        **kwargs
    ) -> GeneratedAudio:
        """Generate speech from text"""
        
        if voice_id not in self.VOICES:
            voice_id = "alloy"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": text,
                    "voice": voice_id,
                    "speed": speed,
                    "response_format": kwargs.get("format", "mp3")
                }
            )
            response.raise_for_status()
            
            audio_bytes = response.content
            
            word_count = len(text.split())
            estimated_duration = (word_count / 150) * 60 / speed
            cost = (len(text) / 1000) * self._cost_per_1k
            
            audio_id = f"oai_{hash(text) % 100000}"
            
            return GeneratedAudio(
                audio_id=audio_id,
                audio_url=f"file://{audio_id}.mp3",
                duration=estimated_duration,
                format="mp3",
                sample_rate=24000,
                channels=1,
                generation_cost=cost,
                provider=self.name,
                metadata={"voice": voice_id, "model": self.model}
            )
    
    async def list_voices(self) -> List[Dict[str, Any]]:
        return [{"id": v, "name": v.title()} for v in self.VOICES]
```

### google_tts.py - Google Cloud TTS

```python
"""Google Cloud text-to-speech provider"""

import os
from typing import List, Dict, Any

from ..base import AudioProvider, GeneratedAudio


class GoogleTTSProvider(AudioProvider):
    """
    Google Cloud TTS - Affordable, wide language support
    
    Features:
    - 200+ voices
    - 40+ languages
    - WaveNet and Neural2 options
    
    Pricing (as of 2025):
    - Standard: $4 per 1M characters
    - WaveNet: $16 per 1M characters
    - Neural2: $16 per 1M characters
    """
    
    def __init__(self, voice_type: str = "Neural2"):
        self.voice_type = voice_type
        # Pricing per 1K chars
        if voice_type == "Standard":
            self._cost_per_1k = 0.004
        else:
            self._cost_per_1k = 0.016
    
    @property
    def name(self) -> str:
        return "google_tts"
    
    async def generate_speech(
        self,
        text: str,
        voice_id: str = "en-US-Neural2-D",
        speed: float = 1.0,
        **kwargs
    ) -> GeneratedAudio:
        """Generate speech from text using Google Cloud TTS"""
        
        # Would use google-cloud-texttospeech library
        # from google.cloud import texttospeech
        
        word_count = len(text.split())
        estimated_duration = (word_count / 150) * 60 / speed
        cost = (len(text) / 1000) * self._cost_per_1k
        
        audio_id = f"gcp_{hash(text) % 100000}"
        
        return GeneratedAudio(
            audio_id=audio_id,
            audio_url=f"file://{audio_id}.mp3",
            duration=estimated_duration,
            format="mp3",
            sample_rate=24000,
            channels=1,
            generation_cost=cost,
            provider=self.name,
            metadata={"voice_id": voice_id, "type": self.voice_type}
        )
    
    async def list_voices(self) -> List[Dict[str, Any]]:
        # Would call Google API
        return [
            {"id": "en-US-Neural2-D", "name": "US Male", "language": "en-US"},
            {"id": "en-US-Neural2-F", "name": "US Female", "language": "en-US"},
            {"id": "en-GB-Neural2-A", "name": "UK Female", "language": "en-GB"},
        ]
```

## Music Providers

### mubert.py - Mubert AI Music

```python
"""Mubert AI music generation provider"""

import os
import httpx
from ..base import MusicProvider, GeneratedAudio


class MubertProvider(MusicProvider):
    """
    Mubert - AI-generated royalty-free music
    
    Features:
    - Infinite unique tracks
    - Genre and mood control
    - Commercial license included
    
    Pricing (as of 2025):
    - ~$0.50 per track
    """
    
    BASE_URL = "https://api.mubert.com/v2"
    
    MOODS = ["upbeat", "calm", "energetic", "melancholic", "epic", "ambient"]
    GENRES = ["electronic", "acoustic", "orchestral", "rock", "jazz", "ambient"]
    
    def __init__(self):
        self.api_key = os.getenv("MUBERT_API_KEY")
        if not self.api_key:
            raise ValueError("MUBERT_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "mubert"
    
    async def generate(
        self,
        mood: str,
        duration: float,
        tempo: str = "medium",
        **kwargs
    ) -> GeneratedAudio:
        """Generate background music"""
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/generate",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "duration": duration,
                    "mood": mood,
                    "tempo": tempo,
                    "genre": kwargs.get("genre", "electronic"),
                    "intensity": kwargs.get("intensity", 0.5),
                }
            )
            response.raise_for_status()
            result = response.json()
            
            return GeneratedAudio(
                audio_id=result["track_id"],
                audio_url=result["url"],
                duration=duration,
                format="mp3",
                sample_rate=44100,
                channels=2,
                generation_cost=0.50,
                provider=self.name,
                metadata={"mood": mood, "tempo": tempo}
            )
```

### suno.py - Suno AI Music

```python
"""Suno AI music generation provider"""

import os
import httpx
from ..base import MusicProvider, GeneratedAudio


class SunoProvider(MusicProvider):
    """
    Suno - AI music with vocals and lyrics
    
    Features:
    - Full songs with vocals
    - Custom lyrics support
    - Multiple genres
    
    Pricing (as of 2025):
    - ~$0.05 per second
    """
    
    BASE_URL = "https://api.suno.ai/v1"
    
    def __init__(self):
        self.api_key = os.getenv("SUNO_API_KEY")
        if not self.api_key:
            raise ValueError("SUNO_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "suno"
    
    async def generate(
        self,
        mood: str,
        duration: float,
        tempo: str = "medium",
        **kwargs
    ) -> GeneratedAudio:
        """Generate music (optionally with vocals)"""
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/generate",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "prompt": kwargs.get("prompt", f"{mood} {tempo} instrumental"),
                    "duration": duration,
                    "instrumental": kwargs.get("instrumental", True),
                    "lyrics": kwargs.get("lyrics"),
                }
            )
            response.raise_for_status()
            result = response.json()
            
            return GeneratedAudio(
                audio_id=result["id"],
                audio_url=result["audio_url"],
                duration=duration,
                format="mp3",
                sample_rate=44100,
                channels=2,
                generation_cost=duration * 0.05,
                provider=self.name,
                metadata={"mood": mood, "has_vocals": not kwargs.get("instrumental", True)}
            )
```

## Image Providers

### dalle.py - OpenAI DALL-E 3

```python
"""OpenAI DALL-E 3 image generation provider"""

import os
import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneratedImage:
    image_id: str
    image_url: str
    width: int
    height: int
    format: str
    generation_cost: float
    provider: str
    revised_prompt: Optional[str] = None


class DalleProvider:
    """
    DALL-E 3 - High quality image generation
    
    Pricing (as of 2025):
    - 1024x1024: $0.04
    - 1024x1792 / 1792x1024: $0.08
    """
    
    BASE_URL = "https://api.openai.com/v1"
    
    SIZES = {
        "square": "1024x1024",
        "portrait": "1024x1792",
        "landscape": "1792x1024"
    }
    
    COSTS = {
        "1024x1024": 0.04,
        "1024x1792": 0.08,
        "1792x1024": 0.08
    }
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
    
    @property
    def name(self) -> str:
        return "dalle"
    
    async def generate(
        self,
        prompt: str,
        size: str = "landscape",
        **kwargs
    ) -> GeneratedImage:
        """Generate image from text prompt"""
        
        size_str = self.SIZES.get(size, size)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/images/generations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "size": size_str,
                    "quality": kwargs.get("quality", "standard"),
                    "n": 1
                }
            )
            response.raise_for_status()
            result = response.json()
            
            image_data = result["data"][0]
            width, height = map(int, size_str.split("x"))
            
            return GeneratedImage(
                image_id=f"dalle_{hash(prompt) % 100000}",
                image_url=image_data["url"],
                width=width,
                height=height,
                format="png",
                generation_cost=self.COSTS[size_str],
                provider=self.name,
                revised_prompt=image_data.get("revised_prompt")
            )
```

## Storage Providers

### local.py - Local Filesystem

```python
"""Local filesystem storage provider"""

import os
import shutil
import aiofiles
from pathlib import Path
from ..base import StorageProvider, StoredFile


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage for development"""
    
    def __init__(self, base_path: str = "./artifacts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "local"
    
    async def upload(self, local_path: str, remote_path: str) -> StoredFile:
        dest = self.base_path / remote_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(local_path, dest)
        
        stat = dest.stat()
        return StoredFile(
            file_id=remote_path,
            url=f"file://{dest.absolute()}",
            size_bytes=stat.st_size,
            content_type=self._guess_content_type(remote_path)
        )
    
    async def download(self, remote_path: str, local_path: str) -> str:
        src = self.base_path / remote_path
        shutil.copy2(src, local_path)
        return local_path
    
    async def get_url(self, remote_path: str, expires_in: int = 3600) -> str:
        return f"file://{(self.base_path / remote_path).absolute()}"
    
    def _guess_content_type(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        types = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".json": "application/json",
        }
        return types.get(ext, "application/octet-stream")
```

### s3.py - AWS S3

```python
"""AWS S3 storage provider"""

import os
from pathlib import Path
from ..base import StorageProvider, StoredFile


class S3StorageProvider(StorageProvider):
    """AWS S3 storage for production"""
    
    def __init__(self, bucket: str, prefix: str = ""):
        self.bucket = bucket
        self.prefix = prefix
        
        # Would use boto3
        # import boto3
        # self.client = boto3.client('s3')
    
    @property
    def name(self) -> str:
        return "s3"
    
    async def upload(self, local_path: str, remote_path: str) -> StoredFile:
        key = f"{self.prefix}/{remote_path}" if self.prefix else remote_path
        
        # self.client.upload_file(local_path, self.bucket, key)
        
        size = Path(local_path).stat().st_size
        
        return StoredFile(
            file_id=key,
            url=f"s3://{self.bucket}/{key}",
            size_bytes=size,
            content_type=self._guess_content_type(remote_path)
        )
    
    async def download(self, remote_path: str, local_path: str) -> str:
        key = f"{self.prefix}/{remote_path}" if self.prefix else remote_path
        # self.client.download_file(self.bucket, key, local_path)
        return local_path
    
    async def get_url(self, remote_path: str, expires_in: int = 3600) -> str:
        key = f"{self.prefix}/{remote_path}" if self.prefix else remote_path
        # return self.client.generate_presigned_url(
        #     'get_object',
        #     Params={'Bucket': self.bucket, 'Key': key},
        #     ExpiresIn=expires_in
        # )
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"
    
    def _guess_content_type(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        types = {".mp4": "video/mp4", ".mp3": "audio/mpeg", ".png": "image/png"}
        return types.get(ext, "application/octet-stream")
```

## Provider Registry Update

```python
# core/providers/__init__.py

from .base import (
    VideoProvider, AudioProvider, MusicProvider, StorageProvider,
    GeneratedVideo, GeneratedAudio, StoredFile,
    ProviderRegistry
)

# Video
from .video.runway import RunwayProvider
from .video.pika import PikaProvider
from .video.stability import StabilityVideoProvider
from .video.luma import LumaProvider
from .video.kling import KlingProvider

# Audio
from .audio.elevenlabs import ElevenLabsProvider
from .audio.openai_tts import OpenAITTSProvider
from .audio.google_tts import GoogleTTSProvider

# Music
from .music.mubert import MubertProvider
from .music.suno import SunoProvider

# Image
from .image.dalle import DalleProvider

# Storage
from .storage.local import LocalStorageProvider
from .storage.s3 import S3StorageProvider


def create_default_registry(mode: str = "mock") -> ProviderRegistry:
    """Create a provider registry with default providers"""
    
    registry = ProviderRegistry()
    
    if mode == "mock":
        from tests.mocks.providers import (
            MockVideoProvider, MockAudioProvider, MockMusicProvider
        )
        registry.register_video(MockVideoProvider())
        registry.register_audio(MockAudioProvider())
        registry.register_music(MockMusicProvider())
    else:
        # Live providers - will raise if API keys missing
        registry.register_video(RunwayProvider())
        registry.register_audio(ElevenLabsProvider())
        registry.register_music(MubertProvider())
    
    # Storage - always use local for now
    registry.register_storage(LocalStorageProvider())
    
    return registry


__all__ = [
    # Base
    "VideoProvider", "AudioProvider", "MusicProvider", "StorageProvider",
    "GeneratedVideo", "GeneratedAudio", "StoredFile",
    "ProviderRegistry",
    
    # Video
    "RunwayProvider", "PikaProvider", "StabilityVideoProvider",
    "LumaProvider", "KlingProvider",
    
    # Audio
    "ElevenLabsProvider", "OpenAITTSProvider", "GoogleTTSProvider",
    
    # Music
    "MubertProvider", "SunoProvider",
    
    # Image
    "DalleProvider",
    
    # Storage
    "LocalStorageProvider", "S3StorageProvider",
    
    # Factory
    "create_default_registry",
]
```

## Cost Summary

| Provider | Type | Cost | Max Duration |
|----------|------|------|--------------|
| Runway Gen-3 | Video | $0.25-0.50/sec | 10s |
| Pika Labs | Video | $0.20/sec | 4s |
| Stability Video | Video | $0.10/sec | 4s |
| Luma AI | Video | $0.30/sec | 5s |
| Kling AI | Video | $0.15-0.30/sec | 10s |
| ElevenLabs | Audio | $0.30/1K chars | - |
| OpenAI TTS | Audio | $0.015-0.030/1K chars | - |
| Google TTS | Audio | $0.004-0.016/1K chars | - |
| Mubert | Music | $0.50/track | 5min |
| Suno | Music | $0.05/sec | 2min |
| DALL-E 3 | Image | $0.04-0.08/image | - |

## Implementation Priority

1. **Now**: Create stub files with interfaces
2. **After Audio Pipeline**: Implement ElevenLabs + Mubert
3. **After Docker**: Implement Runway + Pika
4. **As Needed**: Other providers

All providers follow the same pattern - implement interface, add to registry, done!
