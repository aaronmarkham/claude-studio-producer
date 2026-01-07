"""Script Writer Agent - Breaks video concepts into detailed scenes"""

from dataclasses import dataclass
from typing import List, Optional
from core.budget import ProductionTier
from core.claude_client import ClaudeClient, JSONExtractor


@dataclass
class Scene:
    """A single scene in the video script"""
    scene_id: str
    title: str
    description: str
    duration: float  # seconds
    visual_elements: List[str]
    audio_notes: str
    transition_in: str
    transition_out: str
    prompt_hints: List[str]  # Hints for video generation


class ScriptWriterAgent:
    """
    Takes a high-level video concept and breaks it down into
    individual scenes with detailed descriptions and timing
    """

    def __init__(self, claude_client: ClaudeClient = None):
        """
        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
        """
        self.claude = claude_client or ClaudeClient()

    async def create_script(
        self,
        video_concept: str,
        target_duration: float = 60.0,
        production_tier: ProductionTier = ProductionTier.ANIMATED,
        num_scenes: Optional[int] = None
    ) -> List[Scene]:
        """
        Break down video concept into detailed scenes

        Args:
            video_concept: High-level description of the video
            target_duration: Total video length in seconds
            production_tier: The quality tier (affects scene complexity)
            num_scenes: Optional override for number of scenes (auto-calculated if None)

        Returns:
            List of Scene objects with detailed breakdowns
        """

        # Auto-calculate num_scenes if not provided (roughly one scene per 5 seconds)
        if num_scenes is None:
            num_scenes = max(8, min(20, int(target_duration / 5)))

        # Adjust complexity based on production tier
        tier_guidance = self._get_tier_guidance(production_tier)

        prompt = f"""You are a professional video scriptwriter and production planner.

VIDEO CONCEPT: {video_concept}
TARGET DURATION: {target_duration} seconds
PRODUCTION TIER: {production_tier.value}
ESTIMATED SCENES: {num_scenes}

{tier_guidance}

Break this concept into individual scenes. Each scene should:
- Be 3-8 seconds long (total should sum to approximately {target_duration} seconds)
- Have a clear visual focus
- Flow naturally to the next scene
- Include specific visual elements for video generation
- Have actionable prompt hints that work well for AI video generation

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scenes": [
    {{
      "scene_id": "scene_1",
      "title": "Opening Scene Title",
      "description": "Detailed description of what happens in this scene",
      "duration": 5.0,
      "visual_elements": ["element1", "element2", "element3"],
      "audio_notes": "Background music style, sound effects, voiceover notes",
      "transition_in": "fade_in",
      "transition_out": "cut",
      "prompt_hints": ["specific visual style", "lighting notes", "camera angle"]
    }}
  ]
}}

Valid transitions: fade_in, fade_out, cut, dissolve, wipe, zoom_in, zoom_out, slide_left, slide_right

Make the scenes compelling, well-paced, and optimized for AI video generation."""

        response = await self.claude.query(prompt)
        script_data = JSONExtractor.extract(response)

        # Convert to Scene objects
        scenes = []
        for scene_dict in script_data["scenes"]:
            scenes.append(Scene(
                scene_id=scene_dict["scene_id"],
                title=scene_dict["title"],
                description=scene_dict["description"],
                duration=float(scene_dict["duration"]),
                visual_elements=scene_dict["visual_elements"],
                audio_notes=scene_dict["audio_notes"],
                transition_in=scene_dict["transition_in"],
                transition_out=scene_dict["transition_out"],
                prompt_hints=scene_dict["prompt_hints"]
            ))

        return scenes

    def _get_tier_guidance(self, tier: ProductionTier) -> str:
        """Get tier-specific guidance for scene creation"""

        guidance_map = {
            ProductionTier.STATIC_IMAGES: """
TIER GUIDANCE (Static Images):
- Focus on simple, clear compositions
- Each scene is essentially a still image with text/graphics overlay
- Minimize motion requirements
- Emphasize clarity and readability
- Use straightforward visual metaphors
""",
            ProductionTier.MOTION_GRAPHICS: """
TIER GUIDANCE (Motion Graphics):
- Focus on infographic-style visuals
- Emphasize clean, professional animations
- Use charts, diagrams, and text animations
- Keep visual complexity moderate
- Think template-based motion design
""",
            ProductionTier.ANIMATED: """
TIER GUIDANCE (Animated):
- Allow for character animation and storytelling
- Include dynamic camera movements
- Use varied visual styles (cartoon, illustrated, stylized)
- Can include multiple subjects interacting
- Think engaging, story-driven content
""",
            ProductionTier.PHOTOREALISTIC: """
TIER GUIDANCE (Photorealistic):
- Aim for cinematic, realistic visuals
- Include detailed environmental descriptions
- Use sophisticated camera work (tracking shots, depth of field)
- Describe realistic lighting conditions
- Think high-end commercial or film quality
"""
        }

        return guidance_map.get(tier, "")

    def get_total_duration(self, scenes: List[Scene]) -> float:
        """Calculate total duration of all scenes"""
        return sum(scene.duration for scene in scenes)

    def print_script_summary(self, scenes: List[Scene]):
        """Print a formatted summary of the script"""
        print("\n" + "="*60)
        print("SCRIPT BREAKDOWN")
        print("="*60)

        total_duration = self.get_total_duration(scenes)
        print(f"Total Scenes: {len(scenes)}")
        print(f"Total Duration: {total_duration:.1f} seconds\n")

        for i, scene in enumerate(scenes, 1):
            print(f"\n[{i}] {scene.scene_id.upper()}: {scene.title}")
            print(f"    Duration: {scene.duration}s")
            print(f"    Description: {scene.description}")
            print(f"    Visual Elements: {', '.join(scene.visual_elements)}")
            print(f"    Transitions: {scene.transition_in} → {scene.transition_out}")
            print(f"    Prompt Hints: {', '.join(scene.prompt_hints)}")

        print("\n" + "="*60 + "\n")
