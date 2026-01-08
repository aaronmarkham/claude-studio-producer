# Luma AI Provider - Comprehensive Specification

## Overview

Luma AI's Dream Machine API offers advanced video generation with features that align perfectly with Claude Studio Producer's architecture: keyframes for scene continuity, character references for consistent characters, camera motion concepts, and video extension/looping.

## API Details

### Base URL
```
https://api.lumalabs.ai/dream-machine/v1
```

### Authentication
```
Authorization: Bearer <LUMA_API_KEY>
```

### Official SDK
```bash
pip install lumaai
```

```python
from lumaai import LumaAI

client = LumaAI(auth_token=os.environ["LUMA_API_KEY"])
```

## Models Available

| Model | Description | Best For |
|-------|-------------|----------|
| `ray-2` | Latest stable, high quality | Production use |
| `ray-1-6` | Previous generation | Fallback |
| `ray-3` | Newest (reasoning, HDR) | Advanced features |

## Core Features

### 1. Text-to-Video (Basic)

```python
generation = await client.generations.create(
    prompt="A teddy bear in sunglasses playing electric guitar",
    model="ray-2",
    aspect_ratio="16:9",  # "1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21"
    resolution="720p",     # "540p", "720p", "1080p", "4k"
    duration="5s",         # "5s" or "9s"
    loop=False
)
```

### 2. Image-to-Video (Start Frame)

Perfect for seed assets - animate a still image:

```python
generation = await client.generations.create(
    prompt="Camera slowly zooms into the sketch, lines begin to animate",
    model="ray-2",
    keyframes={
        "frame0": {
            "type": "image",
            "url": "https://example.com/notebook_sketch.jpg"
        }
    }
)
```

### 3. Keyframes - Start AND End Frame Control

**This is huge for scene continuity!** Define both where a scene starts and ends:

```python
generation = await client.generations.create(
    prompt="Character walks from left side to right side of frame",
    model="ray-2",
    keyframes={
        "frame0": {
            "type": "image",
            "url": "https://example.com/start_frame.jpg"
        },
        "frame1": {
            "type": "image",
            "url": "https://example.com/end_frame.jpg"
        }
    }
)
```

### 4. Generation-to-Generation (Video Continuity)

Chain videos together using previous generation IDs:

```python
# First scene
scene1 = await client.generations.create(
    prompt="A woman walks into a coffee shop",
    model="ray-2"
)

# Second scene - continues from scene1
scene2 = await client.generations.create(
    prompt="She orders a latte at the counter",
    model="ray-2",
    keyframes={
        "frame0": {
            "type": "generation",
            "id": scene1.id  # Start from where scene1 ended!
        }
    }
)

# Third scene - continues from scene2
scene3 = await client.generations.create(
    prompt="She sits down and opens her laptop",
    model="ray-2",
    keyframes={
        "frame0": {
            "type": "generation",
            "id": scene2.id
        }
    }
)
```

### 5. Video Extension

Extend an existing video:

```python
# Extend a previous generation
extended = await client.generations.create(
    prompt="The action continues as...",
    model="ray-2",
    keyframes={
        "frame0": {
            "type": "generation",
            "id": previous_generation.id
        }
    }
)
```

### 6. Camera Motion Concepts

Pre-defined camera movements for cinematic shots:

```python
# Get available camera motions
cameras = await client.generations.camera_motion.list()
# Returns: ["bolt_cam", "dolly_zoom", "orbit", "pan_left", "pan_right", ...]

# Use a camera motion
generation = await client.generations.create(
    prompt="A car driving through mountains",
    model="ray-2",
    concepts=[
        {"key": "bolt_cam"}  # Epic slow-motion camera
    ]
)
```

### 7. Character Reference (Ray3)

**Maintain consistent character across shots:**

```python
generation = await client.generations.create(
    prompt="The woman walks through a neon-lit city",
    model="ray-3",
    character_ref={
        "type": "image",
        "url": "https://example.com/character_reference.jpg"
    }
)
```

### 8. Video-to-Video Modification (Ray3 Modify)

Transform existing footage while preserving motion:

```python
generation = await client.generations.create(
    prompt="Transform the setting to a futuristic cyberpunk city",
    model="ray-3",
    modify_video={
        "url": "https://example.com/original_footage.mp4"
    },
    modify_strength="flex_2"  # adhere_1 to reimagine_3
)
```

Modify strength levels:
- `adhere_1`, `adhere_2`, `adhere_3` - Minimal changes, preserve original
- `flex_1`, `flex_2`, `flex_3` - Balanced modification
- `reimagine_1`, `reimagine_2`, `reimagine_3` - Maximum creative freedom

## Polling for Completion

```python
import asyncio

async def wait_for_generation(client, generation_id, timeout=300):
    """Poll until generation completes"""
    elapsed = 0
    poll_interval = 5
    
    while elapsed < timeout:
        generation = await client.generations.get(generation_id)
        
        if generation.state == "completed":
            return generation.assets.video  # Video URL
        elif generation.state == "failed":
            raise Exception(f"Generation failed: {generation.failure_reason}")
        
        # Still "dreaming" or "queued"
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    
    raise TimeoutError(f"Generation timed out after {timeout}s")
```

## Response Structure

```python
{
    "id": "generation-uuid",
    "state": "completed",  # queued, dreaming, completed, failed
    "failure_reason": null,
    "created_at": "2025-01-08T...",
    "assets": {
        "video": "https://storage.lumalabs.ai/..../video.mp4"
    },
    "version": "ray-2",
    "request": {
        "prompt": "...",
        "aspect_ratio": "16:9",
        ...
    }
}
```

## Pricing (as of 2025)

| Resolution | 5s Video | 9s Video |
|------------|----------|----------|
| 540p | ~$0.20 | ~$0.36 |
| 720p | ~$0.40 | ~$0.72 |
| 1080p | ~$0.80 | ~$1.44 |

Draft Mode (Ray3): 5x cheaper for rapid iteration

## Integration with Claude Studio Producer

### Scene Continuity via Keyframes

```python
# In VideoGeneratorAgent

async def generate_continuous_scenes(self, scenes: List[Scene]) -> List[GeneratedVideo]:
    """Generate scenes with continuity using Luma keyframes"""
    
    results = []
    previous_generation_id = None
    
    for scene in scenes:
        keyframes = {}
        
        # If scene has seed asset, use as start frame
        if scene.seed_asset_refs:
            start_asset = scene.seed_asset_refs[0]
            if start_asset.usage == "source_frame":
                keyframes["frame0"] = {
                    "type": "image",
                    "url": start_asset.url
                }
        
        # If continuing from previous scene, chain generations
        elif previous_generation_id:
            keyframes["frame0"] = {
                "type": "generation",
                "id": previous_generation_id
            }
        
        generation = await self.luma_client.generations.create(
            prompt=self.build_prompt(scene),
            model="ray-2",
            aspect_ratio="16:9",
            duration="5s",
            keyframes=keyframes if keyframes else None
        )
        
        video_url = await self.wait_for_completion(generation.id)
        
        results.append(GeneratedVideo(
            video_id=generation.id,
            video_url=video_url,
            duration=5.0,
            generation_cost=0.40,  # 720p 5s
            provider="luma",
            scene_id=scene.scene_id
        ))
        
        previous_generation_id = generation.id
    
    return results
```

### Character Consistency

```python
# Extract character reference from seed assets

async def generate_with_character(
    self, 
    scene: Scene, 
    character_ref_url: str
) -> GeneratedVideo:
    """Generate scene with consistent character"""
    
    generation = await self.luma_client.generations.create(
        prompt=self.build_prompt(scene),
        model="ray-3",
        character_ref={
            "type": "image",
            "url": character_ref_url
        }
    )
    
    return await self.wait_and_wrap(generation)
```

### Camera Motion Integration

```python
# Map scene descriptions to Luma camera concepts

CAMERA_MOTION_MAP = {
    "slow_motion": "bolt_cam",
    "orbit": "orbit",
    "zoom_in": "dolly_zoom",
    "pan_left": "pan_left",
    "pan_right": "pan_right",
    "tracking": "tracking_shot",
    "aerial": "drone_shot",
}

async def generate_with_camera(self, scene: Scene) -> GeneratedVideo:
    """Generate scene with specific camera motion"""
    
    concepts = []
    
    # Extract camera hints from scene
    for hint in scene.prompt_hints:
        if hint in CAMERA_MOTION_MAP:
            concepts.append({"key": CAMERA_MOTION_MAP[hint]})
    
    generation = await self.luma_client.generations.create(
        prompt=self.build_prompt(scene),
        model="ray-2",
        concepts=concepts if concepts else None
    )
    
    return await self.wait_and_wrap(generation)
```

## Full Provider Implementation

```python
# core/providers/video/luma.py

import os
import asyncio
from typing import Dict, Any, Optional, List
from lumaai import LumaAI

from ..base import VideoProvider, GeneratedVideo


class LumaProvider(VideoProvider):
    """
    Luma AI Dream Machine - Advanced video generation
    
    Features:
    - Text-to-video and image-to-video
    - Keyframes (start + end frame control)
    - Generation chaining for scene continuity
    - Character reference for consistent characters
    - Camera motion concepts
    - Video modification (Ray3)
    - 5s and 9s durations
    - Up to 4K resolution
    
    Models:
    - ray-2: Production quality
    - ray-3: Advanced features (reasoning, HDR, character ref)
    
    Pricing (720p):
    - 5s: ~$0.40
    - 9s: ~$0.72
    """
    
    _is_stub = False
    
    COST_MAP = {
        ("540p", "5s"): 0.20,
        ("540p", "9s"): 0.36,
        ("720p", "5s"): 0.40,
        ("720p", "9s"): 0.72,
        ("1080p", "5s"): 0.80,
        ("1080p", "9s"): 1.44,
    }
    
    def __init__(self, model: str = "ray-2"):
        self.api_key = os.getenv("LUMA_API_KEY")
        self.model = model
        
        if not self.api_key:
            raise ValueError("LUMA_API_KEY environment variable required")
        
        self.client = LumaAI(auth_token=self.api_key)
    
    @property
    def name(self) -> str:
        return "luma"
    
    @property
    def cost_per_second(self) -> float:
        # Base cost for 720p
        return 0.08  # $0.40 / 5s
    
    async def generate(
        self,
        prompt: str,
        duration: float = 5.0,
        width: int = 1280,
        height: int = 720,
        **kwargs
    ) -> GeneratedVideo:
        """
        Generate video from text prompt
        
        Additional kwargs:
        - keyframes: Dict with frame0/frame1 for start/end frames
        - start_image_url: URL of image to start from
        - end_image_url: URL of image to end at
        - continue_from: Generation ID to continue from
        - character_ref_url: URL of character reference image
        - camera_motion: Camera concept key (e.g., "bolt_cam")
        - loop: Whether to create a looping video
        - resolution: "540p", "720p", "1080p", "4k"
        """
        
        # Map duration to Luma format
        duration_str = "5s" if duration <= 5 else "9s"
        
        # Determine resolution
        resolution = kwargs.get("resolution", "720p")
        if height >= 1080:
            resolution = "1080p"
        elif height >= 720:
            resolution = "720p"
        else:
            resolution = "540p"
        
        # Build aspect ratio
        aspect_ratio = self._calculate_aspect_ratio(width, height)
        
        # Build keyframes
        keyframes = kwargs.get("keyframes")
        
        if not keyframes:
            keyframes = {}
            
            # Start frame from image
            if kwargs.get("start_image_url"):
                keyframes["frame0"] = {
                    "type": "image",
                    "url": kwargs["start_image_url"]
                }
            
            # Continue from previous generation
            elif kwargs.get("continue_from"):
                keyframes["frame0"] = {
                    "type": "generation",
                    "id": kwargs["continue_from"]
                }
            
            # End frame
            if kwargs.get("end_image_url"):
                keyframes["frame1"] = {
                    "type": "image",
                    "url": kwargs["end_image_url"]
                }
        
        # Build concepts (camera motion)
        concepts = []
        if kwargs.get("camera_motion"):
            concepts.append({"key": kwargs["camera_motion"]})
        
        # Build request
        request_params = {
            "prompt": prompt,
            "model": kwargs.get("model", self.model),
            "aspect_ratio": aspect_ratio,
            "loop": kwargs.get("loop", False),
        }
        
        # Add optional params
        if keyframes:
            request_params["keyframes"] = keyframes
        
        if concepts:
            request_params["concepts"] = concepts
        
        if kwargs.get("character_ref_url"):
            request_params["character_ref"] = {
                "type": "image",
                "url": kwargs["character_ref_url"]
            }
        
        # Create generation
        generation = self.client.generations.create(**request_params)
        
        # Wait for completion
        video_url = await self._wait_for_completion(generation.id)
        
        # Calculate cost
        cost = self.COST_MAP.get((resolution, duration_str), 0.40)
        
        return GeneratedVideo(
            video_id=generation.id,
            video_url=video_url,
            duration=5.0 if duration_str == "5s" else 9.0,
            width=width,
            height=height,
            format="mp4",
            generation_cost=cost,
            provider=self.name,
            metadata={
                "model": self.model,
                "prompt": prompt[:200],
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "keyframes": bool(keyframes),
                "camera_motion": kwargs.get("camera_motion"),
            }
        )
    
    async def generate_continuous(
        self,
        scenes: List[Dict[str, Any]],
        character_ref_url: Optional[str] = None
    ) -> List[GeneratedVideo]:
        """
        Generate multiple scenes with continuity
        
        Each scene in scenes should have:
        - prompt: str
        - duration: float (optional)
        - start_image_url: str (optional, for first scene or specific start)
        """
        
        results = []
        previous_id = None
        
        for i, scene in enumerate(scenes):
            kwargs = {
                "character_ref_url": character_ref_url,
                "camera_motion": scene.get("camera_motion"),
            }
            
            # First scene might have a start image
            if i == 0 and scene.get("start_image_url"):
                kwargs["start_image_url"] = scene["start_image_url"]
            
            # Subsequent scenes continue from previous
            elif previous_id:
                kwargs["continue_from"] = previous_id
            
            result = await self.generate(
                prompt=scene["prompt"],
                duration=scene.get("duration", 5.0),
                **kwargs
            )
            
            results.append(result)
            previous_id = result.video_id
        
        return results
    
    async def _wait_for_completion(
        self,
        generation_id: str,
        timeout: int = 300,
        poll_interval: int = 5
    ) -> str:
        """Poll until generation completes"""
        
        elapsed = 0
        
        while elapsed < timeout:
            generation = self.client.generations.get(generation_id)
            
            if generation.state == "completed":
                return generation.assets.video
            elif generation.state == "failed":
                raise Exception(f"Luma generation failed: {generation.failure_reason}")
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        raise TimeoutError(f"Luma generation timed out after {timeout}s")
    
    async def check_status(self, job_id: str) -> Dict[str, Any]:
        """Check generation status"""
        generation = self.client.generations.get(job_id)
        return {
            "id": generation.id,
            "status": generation.state,
            "video_url": generation.assets.video if generation.state == "completed" else None,
            "failure_reason": generation.failure_reason if generation.state == "failed" else None
        }
    
    async def download(self, video_url: str, local_path: str) -> str:
        """Download video to local path"""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            response.raise_for_status()
            
            with open(local_path, "wb") as f:
                f.write(response.content)
        
        return local_path
    
    async def list_camera_motions(self) -> List[str]:
        """Get available camera motion concepts"""
        concepts = self.client.generations.camera_motion.list()
        return [c.key for c in concepts]
    
    def _calculate_aspect_ratio(self, width: int, height: int) -> str:
        """Calculate closest supported aspect ratio"""
        ratio = width / height
        
        supported = {
            1.0: "1:1",
            16/9: "16:9",
            9/16: "9:16",
            4/3: "4:3",
            3/4: "3:4",
            21/9: "21:9",
            9/21: "9:21",
        }
        
        # Find closest
        closest = min(supported.keys(), key=lambda x: abs(x - ratio))
        return supported[closest]
```

## Summary - Why Luma is Perfect for Claude Studio Producer

| Feature | How We Use It |
|---------|---------------|
| **Text-to-Video** | Basic scene generation, no seed image needed |
| **Image-to-Video** | Animate seed assets (sketches, photos) |
| **Keyframes** | Scene continuity - end of scene A = start of scene B |
| **Generation Chaining** | Automatic continuity across multi-scene videos |
| **Character Reference** | Consistent character across all scenes |
| **Camera Concepts** | Professional camera movements from prompts |
| **Video Extension** | Extend scenes that need to be longer |
| **Ray3 Modify** | Transform real footage with AI |
| **Loop** | Create seamless looping backgrounds |

This makes Luma the ideal provider for our multi-scene, narrative-driven video production system!
