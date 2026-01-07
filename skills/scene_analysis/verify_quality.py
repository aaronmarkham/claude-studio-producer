"""
Video Quality Verification Skill - Claude Agent SDK Skill

This skill enables agents to verify video quality against scene specifications.
"""

import asyncio
from typing import Dict, Any, List

# Import from parent modules
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from agents.qa_verifier import QAVerifierAgent, QAResult
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from core.budget import ProductionTier
from core.claude_client import ClaudeClient


async def verify_quality(
    scene_data: Dict[str, Any],
    video_data: Dict[str, Any],
    original_request: str,
    production_tier: str,
    mock_mode: bool = True,
    claude_api_key: str = None
) -> Dict[str, Any]:
    """
    Verify video quality against scene specification

    Args:
        scene_data: Dictionary containing scene information
        video_data: Dictionary containing generated video information
        original_request: High-level video concept for context
        production_tier: Production quality tier
        mock_mode: Use mock verification for testing
        claude_api_key: Optional API key for Claude

    Returns:
        Dictionary containing:
        - overall_score: Overall quality score (0-100)
        - visual_accuracy: Visual match score
        - style_consistency: Style match score
        - technical_quality: Technical quality score
        - narrative_fit: Narrative fit score
        - issues: List of issues found
        - suggestions: List of improvement suggestions
        - passed: Whether video passed QA threshold
        - threshold: The threshold used
        - quality_gate: Quality gate classification

    Example:
        ```python
        scene_dict = {
            "scene_id": "scene_1",
            "title": "Morning Standup",
            "description": "Developer joins team video call",
            "duration": 5.0,
            "visual_elements": ["laptop", "video call", "coffee"],
            "audio_notes": "ambient music",
            "transition_in": "fade_in",
            "transition_out": "cut",
            "prompt_hints": ["morning light"]
        }

        video_dict = {
            "scene_id": "scene_1",
            "variation_id": 0,
            "video_url": "https://cdn.example.com/video.mp4",
            "thumbnail_url": "https://cdn.example.com/thumb.jpg",
            "duration": 5.0,
            "generation_cost": 1.25,
            "provider": "pika",
            "metadata": {}
        }

        result = await verify_quality(
            scene_data=scene_dict,
            video_data=video_dict,
            original_request="A day in the life of a developer",
            production_tier="animated",
            mock_mode=True
        )

        print(f"Quality score: {result['overall_score']}/100")
        print(f"Passed: {result['passed']}")
        ```
    """

    # Convert dictionaries to objects
    scene = Scene(**scene_data)

    generated_video = GeneratedVideo(
        scene_id=video_data["scene_id"],
        variation_id=video_data["variation_id"],
        video_url=video_data["video_url"],
        thumbnail_url=video_data["thumbnail_url"],
        duration=video_data["duration"],
        generation_cost=video_data["generation_cost"],
        provider=video_data["provider"],
        metadata=video_data.get("metadata", {}),
        quality_score=video_data.get("quality_score")
    )

    # Convert tier string to enum
    tier = ProductionTier(production_tier)

    # Create QA verifier
    claude_client = ClaudeClient() if claude_api_key else None
    qa_verifier = QAVerifierAgent(
        claude_client=claude_client,
        mock_mode=mock_mode
    )

    # Verify video
    result = await qa_verifier.verify_video(
        scene=scene,
        generated_video=generated_video,
        original_request=original_request,
        production_tier=tier
    )

    # Get quality gate
    quality_gate = qa_verifier.get_quality_gate(result.overall_score)

    # Convert to dictionary for serialization
    return {
        "scene_id": result.scene_id,
        "video_url": result.video_url,
        "overall_score": result.overall_score,
        "visual_accuracy": result.visual_accuracy,
        "style_consistency": result.style_consistency,
        "technical_quality": result.technical_quality,
        "narrative_fit": result.narrative_fit,
        "issues": result.issues,
        "suggestions": result.suggestions,
        "passed": result.passed,
        "threshold": result.threshold,
        "quality_gate": quality_gate
    }


async def verify_batch(
    scenes_data: List[Dict[str, Any]],
    videos_data: List[Dict[str, Any]],
    original_request: str,
    production_tier: str,
    mock_mode: bool = True
) -> List[Dict[str, Any]]:
    """
    Verify multiple videos in parallel

    Args:
        scenes_data: List of scene dictionaries
        videos_data: List of video dictionaries
        original_request: High-level video concept
        production_tier: Production quality tier
        mock_mode: Use mock verification

    Returns:
        List of QA result dictionaries
    """

    tasks = [
        verify_quality(scene, video, original_request, production_tier, mock_mode)
        for scene, video in zip(scenes_data, videos_data)
    ]

    return await asyncio.gather(*tasks)


# Skill metadata for Claude Agent SDK discovery
SKILL_METADATA = {
    "name": "verify_quality",
    "description": "Verify video quality against scene specifications using vision analysis",
    "category": "scene-analysis",
    "parameters": {
        "scene_data": {
            "type": "object",
            "description": "Scene specification with description and visual elements"
        },
        "video_data": {
            "type": "object",
            "description": "Generated video information including URL"
        },
        "original_request": {
            "type": "string",
            "description": "High-level video concept for context"
        },
        "production_tier": {
            "type": "string",
            "enum": ["static_images", "motion_graphics", "animated", "photorealistic"],
            "description": "Expected production quality tier"
        },
        "mock_mode": {
            "type": "boolean",
            "default": True,
            "description": "Use simulated verification for testing"
        }
    },
    "returns": {
        "type": "object",
        "properties": {
            "overall_score": {
                "type": "number",
                "description": "Overall quality score (0-100)"
            },
            "visual_accuracy": {
                "type": "number",
                "description": "Visual match score"
            },
            "style_consistency": {
                "type": "number",
                "description": "Style consistency score"
            },
            "technical_quality": {
                "type": "number",
                "description": "Technical quality score"
            },
            "narrative_fit": {
                "type": "number",
                "description": "Narrative fit score"
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of issues found"
            },
            "suggestions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of improvement suggestions"
            },
            "passed": {
                "type": "boolean",
                "description": "Whether video passed QA threshold"
            },
            "quality_gate": {
                "type": "string",
                "enum": ["excellent", "pass", "soft_fail", "hard_fail"],
                "description": "Quality gate classification"
            }
        }
    }
}
