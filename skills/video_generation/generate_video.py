"""
Video Generation Skill - Claude Agent SDK Skill

This skill enables agents to generate videos using various providers.
It's discoverable by agents through progressive disclosure.
"""

import asyncio
from typing import Dict, Any, Optional
from dataclasses import asdict

# Import from parent modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agents.video_generator import VideoGeneratorAgent, VideoProvider
from agents.script_writer import Scene
from core.budget import ProductionTier


async def generate_video(
    scene_data: Dict[str, Any],
    production_tier: str,
    budget_limit: float,
    num_variations: int = 3,
    provider: Optional[str] = None,
    mock_mode: bool = True
) -> Dict[str, Any]:
    """
    Generate video for a scene using specified provider

    Args:
        scene_data: Dictionary containing scene information (from Scene dataclass)
        production_tier: Production quality tier ("static_images", "motion_graphics", etc.)
        budget_limit: Maximum budget for generation
        num_variations: Number of variations to generate
        provider: Optional provider name ("runway_gen3", "pika", etc.)
        mock_mode: Use mock generation for testing

    Returns:
        Dictionary containing:
        - videos: List of generated video dictionaries
        - total_cost: Total generation cost
        - variations_generated: Number of variations created

    Example:
        ```python
        scene_dict = {
            "scene_id": "scene_1",
            "title": "Opening Scene",
            "description": "Developer at computer",
            "duration": 5.0,
            "visual_elements": ["laptop", "coffee"],
            "audio_notes": "ambient music",
            "transition_in": "fade_in",
            "transition_out": "cut",
            "prompt_hints": ["morning light", "focused expression"]
        }

        result = await generate_video(
            scene_data=scene_dict,
            production_tier="animated",
            budget_limit=10.0,
            num_variations=3
        )

        print(f"Generated {result['variations_generated']} videos")
        print(f"Total cost: ${result['total_cost']:.2f}")
        ```
    """

    # Convert scene data to Scene object
    scene = Scene(**scene_data)

    # Convert tier string to enum
    tier = ProductionTier(production_tier)

    # Convert provider string to enum if provided
    provider_enum = VideoProvider(provider) if provider else None

    # Create generator
    generator = VideoGeneratorAgent(
        provider=provider_enum,
        num_variations=num_variations,
        mock_mode=mock_mode
    )

    # Generate videos
    videos = await generator.generate_scene(
        scene=scene,
        production_tier=tier,
        budget_limit=budget_limit,
        num_variations=num_variations
    )

    # Convert to dictionaries for serialization
    video_dicts = [
        {
            "scene_id": v.scene_id,
            "variation_id": v.variation_id,
            "video_url": v.video_url,
            "thumbnail_url": v.thumbnail_url,
            "duration": v.duration,
            "generation_cost": v.generation_cost,
            "provider": v.provider,
            "metadata": v.metadata,
            "quality_score": v.quality_score
        }
        for v in videos
    ]

    total_cost = sum(v.generation_cost for v in videos)

    return {
        "videos": video_dicts,
        "total_cost": total_cost,
        "variations_generated": len(videos),
        "budget_remaining": budget_limit - total_cost
    }


# Skill metadata for Claude Agent SDK discovery
SKILL_METADATA = {
    "name": "generate_video",
    "description": "Generate video content for a scene using AI video generation providers",
    "category": "video-generation",
    "parameters": {
        "scene_data": {
            "type": "object",
            "description": "Scene information including description, duration, visual elements"
        },
        "production_tier": {
            "type": "string",
            "enum": ["static_images", "motion_graphics", "animated", "photorealistic"],
            "description": "Quality tier for video generation"
        },
        "budget_limit": {
            "type": "number",
            "description": "Maximum budget in USD for generation"
        },
        "num_variations": {
            "type": "integer",
            "default": 3,
            "description": "Number of video variations to generate"
        },
        "provider": {
            "type": "string",
            "enum": ["runway_gen3", "pika", "stability", "dalle", "mock"],
            "description": "Video provider to use (auto-selected if not specified)"
        },
        "mock_mode": {
            "type": "boolean",
            "default": True,
            "description": "Use simulated generation for testing without API keys"
        }
    },
    "returns": {
        "type": "object",
        "properties": {
            "videos": {
                "type": "array",
                "description": "List of generated video objects"
            },
            "total_cost": {
                "type": "number",
                "description": "Total generation cost in USD"
            },
            "variations_generated": {
                "type": "integer",
                "description": "Number of variations successfully created"
            }
        }
    }
}
