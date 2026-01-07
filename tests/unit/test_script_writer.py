"""Unit tests for ScriptWriterAgent"""

import pytest
from unittest.mock import AsyncMock
from agents.script_writer import ScriptWriterAgent, Scene
from core.budget import ProductionTier
from core.models.audio import SyncPoint
from tests.mocks import MockClaudeClient


class TestScriptWriterAgent:
    """Test ScriptWriterAgent initialization and basic functionality"""

    def test_initialization(self):
        """Test agent initializes with provided client"""
        mock_client = MockClaudeClient()
        agent = ScriptWriterAgent(claude_client=mock_client)
        assert agent.claude == mock_client

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = ScriptWriterAgent()
        assert agent.claude is not None

    def test_is_stub_attribute(self):
        """Test that _is_stub attribute is set correctly"""
        assert hasattr(ScriptWriterAgent, "_is_stub")
        assert ScriptWriterAgent._is_stub == False

    @pytest.mark.asyncio
    async def test_create_script(self):
        """Test create_script generates scenes"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "scenes": [
                {
                    "scene_id": "scene_001",
                    "title": "Opening Shot",
                    "description": "Camera pans across city skyline",
                    "duration": 5.0,
                    "visual_elements": ["skyline", "sunrise", "buildings"],
                    "audio_notes": "Upbeat music",
                    "transition_in": "fade_in",
                    "transition_out": "cut",
                    "prompt_hints": ["cinematic", "morning light"],
                    "voiceover_text": "Welcome to the future of AI",
                    "sync_points": [],
                    "music_transition": "continue",
                    "sfx_cues": [],
                    "vo_start_offset": 0.5,
                    "vo_end_buffer": 0.5
                },
                {
                    "scene_id": "scene_002",
                    "title": "Product Demo",
                    "description": "Close-up of app interface",
                    "duration": 7.0,
                    "visual_elements": ["UI", "animations", "transitions"],
                    "audio_notes": "Softer music",
                    "transition_in": "cut",
                    "transition_out": "fade_out",
                    "prompt_hints": ["modern", "clean"],
                    "voiceover_text": "Our platform makes AI accessible",
                    "sync_points": [
                        {
                            "timestamp": 2.0,
                            "word_or_phrase": "accessible",
                            "visual_cue": "button click",
                            "tolerance": 0.3
                        }
                    ],
                    "music_transition": "fade",
                    "sfx_cues": ["click"],
                    "vo_start_offset": 0.0,
                    "vo_end_buffer": 0.5
                }
            ]
        }""")

        agent = ScriptWriterAgent(claude_client=mock_client)
        scenes = await agent.create_script(
            video_concept="AI platform demo",
            target_duration=12.0,
            production_tier=ProductionTier.ANIMATED
        )

        assert len(scenes) == 2

        # Check first scene
        assert scenes[0].scene_id == "scene_001"
        assert scenes[0].title == "Opening Shot"
        assert scenes[0].duration == 5.0
        assert len(scenes[0].visual_elements) == 3
        assert scenes[0].voiceover_text == "Welcome to the future of AI"
        assert scenes[0].transition_in == "fade_in"

        # Check second scene with sync point
        assert scenes[1].scene_id == "scene_002"
        assert scenes[1].duration == 7.0
        assert len(scenes[1].sync_points) == 1
        assert scenes[1].sync_points[0].word_or_phrase == "accessible"
        assert scenes[1].sync_points[0].timestamp == 2.0
        assert len(scenes[1].sfx_cues) == 1

    @pytest.mark.asyncio
    async def test_create_script_with_num_scenes(self):
        """Test create_script with explicit scene count"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "scenes": [
                {
                    "scene_id": "scene_1",
                    "title": "Scene 1",
                    "description": "First scene",
                    "duration": 4.0,
                    "visual_elements": ["element1"],
                    "audio_notes": "Music",
                    "transition_in": "fade_in",
                    "transition_out": "cut",
                    "prompt_hints": ["professional"]
                },
                {
                    "scene_id": "scene_2",
                    "title": "Scene 2",
                    "description": "Second scene",
                    "duration": 4.0,
                    "visual_elements": ["element2"],
                    "audio_notes": "Music",
                    "transition_in": "cut",
                    "transition_out": "cut",
                    "prompt_hints": ["professional"]
                },
                {
                    "scene_id": "scene_3",
                    "title": "Scene 3",
                    "description": "Third scene",
                    "duration": 4.0,
                    "visual_elements": ["element3"],
                    "audio_notes": "Music",
                    "transition_in": "cut",
                    "transition_out": "fade_out",
                    "prompt_hints": ["professional"]
                }
            ]
        }""")

        agent = ScriptWriterAgent(claude_client=mock_client)
        scenes = await agent.create_script(
            video_concept="Test concept",
            target_duration=12.0,
            num_scenes=3
        )

        assert len(scenes) == 3

    @pytest.mark.asyncio
    async def test_create_script_different_tiers(self):
        """Test that different tiers are passed to prompt"""
        mock_client = MockClaudeClient()

        # Response for any tier
        mock_client.add_response("""{
            "scenes": [
                {
                    "scene_id": "scene_1",
                    "title": "Test",
                    "description": "Test scene",
                    "duration": 5.0,
                    "visual_elements": ["test"],
                    "audio_notes": "Music",
                    "transition_in": "fade_in",
                    "transition_out": "fade_out",
                    "prompt_hints": ["test"]
                }
            ]
        }""")

        agent = ScriptWriterAgent(claude_client=mock_client)
        scenes = await agent.create_script(
            video_concept="Test",
            production_tier=ProductionTier.PHOTOREALISTIC
        )

        assert len(scenes) == 1
        # Verify the tier was included in the prompt
        assert mock_client.get_call_count() == 1
        prompt = mock_client.calls[0]["prompt"]
        assert "photorealistic" in prompt.lower()

    def test_get_tier_guidance(self):
        """Test tier-specific guidance generation"""
        agent = ScriptWriterAgent()

        guidance_static = agent._get_tier_guidance(ProductionTier.STATIC_IMAGES)
        guidance_motion = agent._get_tier_guidance(ProductionTier.MOTION_GRAPHICS)
        guidance_animated = agent._get_tier_guidance(ProductionTier.ANIMATED)
        guidance_photo = agent._get_tier_guidance(ProductionTier.PHOTOREALISTIC)

        # Each tier should have unique guidance
        assert "Static Images" in guidance_static
        assert "Motion Graphics" in guidance_motion
        assert "Animated" in guidance_animated
        assert "Photorealistic" in guidance_photo

        # Check content differences
        assert "infographic" in guidance_motion.lower()
        assert "character" in guidance_animated.lower()
        assert "cinematic" in guidance_photo.lower()

    def test_get_total_duration(self):
        """Test calculating total script duration"""
        agent = ScriptWriterAgent()

        scenes = [
            Scene(
                scene_id="s1",
                title="Scene 1",
                description="Test",
                duration=5.0,
                visual_elements=[],
                audio_notes="",
                transition_in="fade_in",
                transition_out="cut",
                prompt_hints=[]
            ),
            Scene(
                scene_id="s2",
                title="Scene 2",
                description="Test",
                duration=7.5,
                visual_elements=[],
                audio_notes="",
                transition_in="cut",
                transition_out="fade_out",
                prompt_hints=[]
            )
        ]

        total = agent.get_total_duration(scenes)
        assert total == 12.5

    def test_get_total_duration_empty(self):
        """Test total duration with no scenes"""
        agent = ScriptWriterAgent()
        total = agent.get_total_duration([])
        assert total == 0.0


class TestScene:
    """Test Scene dataclass"""

    def test_scene_creation(self):
        """Test creating basic scene"""
        scene = Scene(
            scene_id="test_scene",
            title="Test Scene",
            description="A test scene",
            duration=5.0,
            visual_elements=["element1", "element2"],
            audio_notes="Background music",
            transition_in="fade_in",
            transition_out="cut",
            prompt_hints=["cinematic", "dramatic"]
        )

        assert scene.scene_id == "test_scene"
        assert scene.title == "Test Scene"
        assert scene.duration == 5.0
        assert len(scene.visual_elements) == 2
        assert scene.voiceover_text is None  # Default

    def test_scene_with_voiceover(self):
        """Test scene with voiceover and sync points"""
        sync_point = SyncPoint(
            timestamp=2.0,
            word_or_phrase="action",
            visual_cue="button appears",
            tolerance=0.5
        )

        scene = Scene(
            scene_id="vo_scene",
            title="Voiceover Scene",
            description="Scene with VO",
            duration=6.0,
            visual_elements=["UI"],
            audio_notes="Music + VO",
            transition_in="cut",
            transition_out="cut",
            prompt_hints=["professional"],
            voiceover_text="Click the action button",
            sync_points=[sync_point],
            music_transition="continue",
            sfx_cues=["click"],
            vo_start_offset=0.5,
            vo_end_buffer=0.5
        )

        assert scene.voiceover_text == "Click the action button"
        assert len(scene.sync_points) == 1
        assert scene.sync_points[0].word_or_phrase == "action"
        assert scene.music_transition == "continue"
        assert len(scene.sfx_cues) == 1
        assert scene.vo_start_offset == 0.5

    def test_scene_defaults(self):
        """Test scene default values"""
        scene = Scene(
            scene_id="defaults",
            title="Default Scene",
            description="Testing defaults",
            duration=5.0,
            visual_elements=[],
            audio_notes="",
            transition_in="cut",
            transition_out="cut",
            prompt_hints=[]
        )

        # Check defaults
        assert scene.voiceover_text is None
        assert scene.sync_points == []
        assert scene.music_transition == "continue"
        assert scene.sfx_cues == []
        assert scene.vo_start_offset == 0.0
        assert scene.vo_end_buffer == 0.5
        assert scene.seed_asset_refs == []


class TestScriptWriterIntegration:
    """Integration tests for ScriptWriterAgent"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import ScriptWriterAgent as ImportedAgent
        assert ImportedAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "script_writer" in AGENT_REGISTRY
        assert AGENT_REGISTRY["script_writer"]["status"] == "implemented"
        assert AGENT_REGISTRY["script_writer"]["class"] == "ScriptWriterAgent"

    def test_scene_can_be_imported(self):
        """Test that Scene model can be imported"""
        from agents.script_writer import Scene as ImportedScene
        assert ImportedScene is not None
