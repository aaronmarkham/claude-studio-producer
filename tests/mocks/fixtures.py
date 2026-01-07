"""Test data factories for consistent test setup"""

from typing import List
from agents.script_writer import Scene
from agents.producer import PilotStrategy
from core.budget import ProductionTier


def make_scene(
    scene_id: str = "scene_1",
    title: str = "Test Scene",
    description: str = "A test scene",
    duration: float = 5.0,
    **kwargs
) -> Scene:
    """Factory for Scene objects"""
    defaults = {
        "scene_id": scene_id,
        "title": title,
        "description": description,
        "duration": duration,
        "visual_elements": ["element1", "element2"],
        "audio_notes": "ambient",
        "transition_in": "cut",
        "transition_out": "cut",
        "prompt_hints": ["professional"]
    }
    defaults.update(kwargs)
    return Scene(**defaults)


def make_scene_list(count: int = 3, **kwargs) -> List[Scene]:
    """Factory for list of scenes"""
    return [
        make_scene(
            scene_id=f"scene_{i+1}",
            title=f"Scene {i+1}",
            duration=5.0,
            **kwargs
        )
        for i in range(count)
    ]


def make_pilot_strategy(
    pilot_id: str = "pilot_test",
    tier: ProductionTier = ProductionTier.ANIMATED,
    allocated_budget: float = 50.0,
    **kwargs
) -> PilotStrategy:
    """Factory for PilotStrategy objects"""
    defaults = {
        "pilot_id": pilot_id,
        "tier": tier,
        "allocated_budget": allocated_budget,
        "test_scene_count": 2,
        "full_scene_count": 10,
        "rationale": "Test pilot"
    }
    defaults.update(kwargs)
    return PilotStrategy(**defaults)


def make_video_request(
    topic: str = "developer workflow",
    duration: int = 60,
    style: str = "professional"
) -> str:
    """Factory for video request strings"""
    return f"""
    Create a {duration}-second video about "{topic}".
    Style: {style}
    Show the complete workflow with engaging visuals.
    """.strip()
