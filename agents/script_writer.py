"""Script Writer Agent - Breaks video concepts into detailed scenes"""

from dataclasses import dataclass, field
from typing import List, Optional
from strands import tool
from core.budget import ProductionTier
from core.claude_client import ClaudeClient, JSONExtractor
from core.models.audio import SyncPoint
from core.models.seed_assets import SeedAssetRef
from .base import StudioAgent


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

    # Audio elements (NEW)
    voiceover_text: Optional[str] = None           # What to say during this scene
    sync_points: List[SyncPoint] = field(default_factory=list)  # Critical timing points
    music_transition: str = "continue"             # "continue", "fade", "change", "stop"
    sfx_cues: List[str] = field(default_factory=list)  # Sound effects needed ["notification", "whoosh"]
    vo_start_offset: float = 0.0                   # Delay before VO starts (seconds)
    vo_end_buffer: float = 0.5                    # Buffer after VO ends (seconds)

    # Seed asset references (NEW)
    seed_asset_refs: List[SeedAssetRef] = field(default_factory=list)  # References to brand assets

    # Text overlay (for post-production - AI video can't render readable text)
    text_overlay: Optional[str] = None       # Text to display on screen
    text_position: str = "center"            # "center", "lower_third", "upper_third", "top", "bottom"
    text_style: str = "title"                # "title", "subtitle", "caption", "watermark"
    text_start_time: Optional[float] = None  # When text appears (None = start of scene)
    text_duration: Optional[float] = None    # How long text shows (None = whole scene)


class ScriptWriterAgent(StudioAgent):
    """
    Takes a high-level video concept and breaks it down into
    individual scenes with detailed descriptions and timing
    """

    _is_stub = False

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        """
        Args:
            claude_client: Optional ClaudeClient instance (creates one if not provided)
        """
        super().__init__(claude_client=claude_client)

    @tool
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
- Include audio specifications (voiceover text, sync points, music, sound effects)

CRITICAL - TEXT IN VISUALS:
AI video models CANNOT render readable text - any text, words, letters, or writing will appear garbled/illegible.
- Do NOT include specific text, words, logos with text, or readable writing in visual descriptions or prompt_hints
- Instead describe abstract shapes, movements, colors, patterns, and visual effects
- If text/titles/captions are needed on screen, put them in the "text_overlay" field - these will be added in post-production with crisp rendering
- Examples:
  - BAD: "Screen shows 'Welcome to CodeCraft' text"
  - GOOD: "Glowing interface elements animate into view" + text_overlay: "Welcome to CodeCraft"
  - BAD: "Terminal displays 'npm install' command"
  - GOOD: "Terminal window with scrolling code-like patterns" + text_overlay: "npm install"

AUDIO GUIDELINES:
- Voiceover should be concise (roughly 150 words per minute = 2.5 words/second)
- Leave 0.5s buffer at scene start/end for transitions
- Mark sync points for critical visual moments (when specific words must match actions)
- Consider pacing - not every scene needs narration
- Specify music transitions between scenes ("continue", "fade", "change", "stop")
- List sound effects with their purpose (e.g., "notification_sound", "whoosh_transition")

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scenes": [
    {{
      "scene_id": "scene_1",
      "title": "Opening Scene Title",
      "description": "Detailed description of what happens in this scene (NO readable text!)",
      "duration": 5.0,
      "visual_elements": ["element1", "element2", "element3"],
      "audio_notes": "Background music style, sound effects, voiceover notes",
      "transition_in": "fade_in",
      "transition_out": "cut",
      "prompt_hints": ["specific visual style", "lighting notes", "camera angle"],
      "voiceover_text": "The exact words to be spoken during this scene (or null if no voiceover)",
      "sync_points": [
        {{"timestamp": 2.0, "word_or_phrase": "deploy", "visual_cue": "button click animation", "tolerance": 0.3}}
      ],
      "music_transition": "continue",
      "sfx_cues": ["notification_sound"],
      "vo_start_offset": 0.5,
      "vo_end_buffer": 0.5,
      "text_overlay": "Text to display on screen (or null if no text needed)",
      "text_position": "center",
      "text_style": "title"
    }}
  ]
}}

Valid transitions: fade_in, fade_out, cut, dissolve, wipe, zoom_in, zoom_out, slide_left, slide_right
Valid music_transitions: continue, fade, change, stop
Valid text_position: center, lower_third, upper_third, top, bottom
Valid text_style: title (large centered), subtitle (medium lower), caption (small with background), watermark (corner)

Make the scenes compelling, well-paced, and optimized for AI video generation with synchronized audio.
Remember: NO readable text in visual descriptions - use text_overlay for any on-screen text."""

        response = await self.claude.query(prompt)
        script_data = JSONExtractor.extract(response)

        # Convert to Scene objects
        scenes = []
        for scene_dict in script_data["scenes"]:
            # Parse sync points if present
            sync_points = []
            if "sync_points" in scene_dict and scene_dict["sync_points"]:
                for sp_dict in scene_dict["sync_points"]:
                    sync_points.append(SyncPoint(
                        timestamp=float(sp_dict.get("timestamp", 0)),
                        word_or_phrase=sp_dict.get("word_or_phrase", ""),
                        visual_cue=sp_dict.get("visual_cue", ""),
                        tolerance=float(sp_dict.get("tolerance", 0.5))
                    ))

            # Handle optional float fields that might be None
            vo_start = scene_dict.get("vo_start_offset")
            vo_end = scene_dict.get("vo_end_buffer")

            # Handle optional text timing fields
            text_start = scene_dict.get("text_start_time")
            text_dur = scene_dict.get("text_duration")

            scenes.append(Scene(
                scene_id=scene_dict["scene_id"],
                title=scene_dict["title"],
                description=scene_dict["description"],
                duration=float(scene_dict["duration"]),
                visual_elements=scene_dict.get("visual_elements", []),
                audio_notes=scene_dict.get("audio_notes", ""),
                transition_in=scene_dict.get("transition_in", "cut"),
                transition_out=scene_dict.get("transition_out", "cut"),
                prompt_hints=scene_dict.get("prompt_hints", []),
                # Audio fields (optional, with defaults)
                voiceover_text=scene_dict.get("voiceover_text"),
                sync_points=sync_points,
                music_transition=scene_dict.get("music_transition", "continue"),
                sfx_cues=scene_dict.get("sfx_cues", []),
                vo_start_offset=float(vo_start) if vo_start is not None else 0.0,
                vo_end_buffer=float(vo_end) if vo_end is not None else 0.5,
                # Text overlay fields (for post-production)
                text_overlay=scene_dict.get("text_overlay"),
                text_position=scene_dict.get("text_position", "center"),
                text_style=scene_dict.get("text_style", "title"),
                text_start_time=float(text_start) if text_start is not None else None,
                text_duration=float(text_dur) if text_dur is not None else None
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
