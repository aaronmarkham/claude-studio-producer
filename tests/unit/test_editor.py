"""Unit tests for EditorAgent"""

import pytest
import json
from unittest.mock import AsyncMock
from agents.editor import EditorAgent
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from agents.qa_verifier import QAResult
from core.models.edit_decision import (
    EditDecision,
    EditCandidate,
    EditDecisionList,
    ExportFormat,
    HumanFeedback,
)


@pytest.fixture
def mock_claude_client():
    """Create a mock Claude client"""
    client = AsyncMock()
    client.query = AsyncMock()
    return client


@pytest.fixture
def sample_scenes():
    """Create sample scenes"""
    return [
        Scene(
            scene_id="scene_001",
            title="Opening",
            description="Product reveal",
            duration=5.0,
            visual_elements=["product", "logo"],
            audio_notes="Upbeat music",
            transition_in="fade_in",
            transition_out="cut",
            prompt_hints=["professional", "modern"]
        ),
        Scene(
            scene_id="scene_002",
            title="Features",
            description="Show key features",
            duration=8.0,
            visual_elements=["features", "UI"],
            audio_notes="Voiceover",
            transition_in="cut",
            transition_out="dissolve",
            prompt_hints=["clean", "technical"]
        ),
        Scene(
            scene_id="scene_003",
            title="Call to Action",
            description="Visit website",
            duration=4.0,
            visual_elements=["CTA", "website"],
            audio_notes="Voiceover",
            transition_in="dissolve",
            transition_out="fade_out",
            prompt_hints=["engaging"]
        ),
    ]


@pytest.fixture
def sample_video_candidates():
    """Create sample video candidates"""
    return {
        "scene_001": [
            GeneratedVideo(
                scene_id="scene_001",
                variation_id=0,
                video_url="artifacts/scene_001_var0.mp4",
                thumbnail_url="artifacts/scene_001_var0_thumb.jpg",
                duration=5.0,
                generation_cost=0.50,
                provider="mock",
                metadata={"resolution": "1920x1080"}
            ),
            GeneratedVideo(
                scene_id="scene_001",
                variation_id=1,
                video_url="artifacts/scene_001_var1.mp4",
                thumbnail_url="artifacts/scene_001_var1_thumb.jpg",
                duration=5.0,
                generation_cost=0.50,
                provider="mock",
                metadata={"resolution": "1920x1080"}
            ),
        ],
        "scene_002": [
            GeneratedVideo(
                scene_id="scene_002",
                variation_id=0,
                video_url="artifacts/scene_002_var0.mp4",
                thumbnail_url="artifacts/scene_002_var0_thumb.jpg",
                duration=8.0,
                generation_cost=0.80,
                provider="mock",
                metadata={"resolution": "1920x1080"}
            ),
            GeneratedVideo(
                scene_id="scene_002",
                variation_id=1,
                video_url="artifacts/scene_002_var1.mp4",
                thumbnail_url="artifacts/scene_002_var1_thumb.jpg",
                duration=8.0,
                generation_cost=0.80,
                provider="mock",
                metadata={"resolution": "1920x1080"}
            ),
        ],
        "scene_003": [
            GeneratedVideo(
                scene_id="scene_003",
                variation_id=0,
                video_url="artifacts/scene_003_var0.mp4",
                thumbnail_url="artifacts/scene_003_var0_thumb.jpg",
                duration=4.0,
                generation_cost=0.40,
                provider="mock",
                metadata={"resolution": "1920x1080"}
            ),
        ],
    }


@pytest.fixture
def sample_qa_results():
    """Create sample QA results"""
    return {
        "scene_001": [
            QAResult(
                scene_id="scene_001",
                video_url="artifacts/scene_001_var0.mp4",
                overall_score=85.0,
                visual_accuracy=88.0,
                style_consistency=82.0,
                technical_quality=90.0,
                narrative_fit=80.0,
                issues=[],
                suggestions=["Could be more dynamic"],
                passed=True,
                threshold=75.0
            ),
            QAResult(
                scene_id="scene_001",
                video_url="artifacts/scene_001_var1.mp4",
                overall_score=78.0,
                visual_accuracy=75.0,
                style_consistency=80.0,
                technical_quality=85.0,
                narrative_fit=72.0,
                issues=["Slightly off-brand"],
                suggestions=[],
                passed=True,
                threshold=75.0
            ),
        ],
        "scene_002": [
            QAResult(
                scene_id="scene_002",
                video_url="artifacts/scene_002_var0.mp4",
                overall_score=92.0,
                visual_accuracy=95.0,
                style_consistency=90.0,
                technical_quality=92.0,
                narrative_fit=91.0,
                issues=[],
                suggestions=[],
                passed=True,
                threshold=75.0
            ),
            QAResult(
                scene_id="scene_002",
                video_url="artifacts/scene_002_var1.mp4",
                overall_score=88.0,
                visual_accuracy=90.0,
                style_consistency=85.0,
                technical_quality=90.0,
                narrative_fit=87.0,
                issues=[],
                suggestions=["Good pacing"],
                passed=True,
                threshold=75.0
            ),
        ],
        "scene_003": [
            QAResult(
                scene_id="scene_003",
                video_url="artifacts/scene_003_var0.mp4",
                overall_score=86.0,
                visual_accuracy=88.0,
                style_consistency=84.0,
                technical_quality=87.0,
                narrative_fit=85.0,
                issues=[],
                suggestions=[],
                passed=True,
                threshold=75.0
            ),
        ],
    }


class TestEditorAgent:
    """Test EditorAgent"""

    def test_initialization(self, mock_claude_client):
        """Test agent initialization"""
        agent = EditorAgent(claude_client=mock_claude_client)
        assert agent.claude == mock_claude_client

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = EditorAgent()
        assert agent.claude is not None

    def test_is_stub_attribute(self):
        """Test that agent has _is_stub attribute"""
        assert hasattr(EditorAgent, '_is_stub')
        assert EditorAgent._is_stub is False

    @pytest.mark.asyncio
    async def test_generate_candidates(self, mock_claude_client, sample_scenes, sample_video_candidates, sample_qa_results):
        """Test generating edit candidates"""
        agent = EditorAgent(claude_client=mock_claude_client)

        # Mock Claude response
        mock_response = json.dumps({
            "candidates": [
                {
                    "candidate_id": "safe_cut",
                    "name": "Safe Cut",
                    "editorial_approach": "safe",
                    "reasoning": "Highest QA scores",
                    "description": "Conservative edit",
                    "estimated_quality": 88.0,
                    "total_duration": 17.0,
                    "edits": [
                        {
                            "scene_id": "scene_001",
                            "selected_variation": 0,
                            "in_point": 0.0,
                            "out_point": 5.0,
                            "duration": 5.0,
                            "transition_in": "fade_in",
                            "transition_in_duration": 0.5,
                            "transition_out": "cut",
                            "transition_out_duration": 0.0,
                        },
                        {
                            "scene_id": "scene_002",
                            "selected_variation": 0,
                            "in_point": 0.0,
                            "out_point": 8.0,
                            "duration": 8.0,
                            "transition_in": "cut",
                            "transition_in_duration": 0.0,
                            "transition_out": "dissolve",
                            "transition_out_duration": 1.0,
                        },
                        {
                            "scene_id": "scene_003",
                            "selected_variation": 0,
                            "in_point": 0.0,
                            "out_point": 4.0,
                            "duration": 4.0,
                            "transition_in": "dissolve",
                            "transition_in_duration": 1.0,
                            "transition_out": "fade_out",
                            "transition_out_duration": 1.0,
                        },
                    ],
                }
            ]
        })
        mock_claude_client.query.return_value = mock_response

        # Generate candidates
        candidates = await agent.generate_candidates(
            scenes=sample_scenes,
            video_candidates=sample_video_candidates,
            qa_results=sample_qa_results,
            original_request="Create a product video",
            num_candidates=1
        )

        # Check results
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.candidate_id == "safe_cut"
        assert candidate.name == "Safe Cut"
        assert candidate.style == "safe"
        assert len(candidate.decisions) == 3
        assert candidate.total_duration == 17.0

        # Check decisions
        assert candidate.decisions[0].scene_id == "scene_001"
        assert candidate.decisions[0].selected_variation == 0
        assert candidate.decisions[0].video_url == "artifacts/scene_001_var0.mp4"

    @pytest.mark.asyncio
    async def test_generate_multiple_candidates(self, mock_claude_client, sample_scenes, sample_video_candidates, sample_qa_results):
        """Test generating multiple edit candidates"""
        agent = EditorAgent(claude_client=mock_claude_client)

        # Mock Claude response with 3 candidates
        mock_response = json.dumps({
            "candidates": [
                {
                    "candidate_id": "safe_cut",
                    "name": "Safe Cut",
                    "editorial_approach": "safe",
                    "reasoning": "Highest QA scores",
                    "description": "Conservative edit",
                    "estimated_quality": 88.0,
                    "total_duration": 17.0,
                    "edits": [
                        {"scene_id": "scene_001", "selected_variation": 0, "in_point": 0.0, "out_point": 5.0, "duration": 5.0, "transition_in": "fade_in", "transition_in_duration": 0.5, "transition_out": "cut", "transition_out_duration": 0.0},
                        {"scene_id": "scene_002", "selected_variation": 0, "in_point": 0.0, "out_point": 8.0, "duration": 8.0, "transition_in": "cut", "transition_in_duration": 0.0, "transition_out": "dissolve", "transition_out_duration": 1.0},
                        {"scene_id": "scene_003", "selected_variation": 0, "in_point": 0.0, "out_point": 4.0, "duration": 4.0, "transition_in": "dissolve", "transition_in_duration": 1.0, "transition_out": "fade_out", "transition_out_duration": 1.0},
                    ],
                },
                {
                    "candidate_id": "creative_cut",
                    "name": "Creative Cut",
                    "editorial_approach": "creative",
                    "reasoning": "Most interesting visuals",
                    "description": "Artistic edit",
                    "estimated_quality": 82.0,
                    "total_duration": 17.0,
                    "edits": [
                        {"scene_id": "scene_001", "selected_variation": 1, "in_point": 0.0, "out_point": 5.0, "duration": 5.0, "transition_in": "fade_in", "transition_in_duration": 0.5, "transition_out": "cut", "transition_out_duration": 0.0},
                        {"scene_id": "scene_002", "selected_variation": 1, "in_point": 0.0, "out_point": 8.0, "duration": 8.0, "transition_in": "cut", "transition_in_duration": 0.0, "transition_out": "dissolve", "transition_out_duration": 1.0},
                        {"scene_id": "scene_003", "selected_variation": 0, "in_point": 0.0, "out_point": 4.0, "duration": 4.0, "transition_in": "dissolve", "transition_in_duration": 1.0, "transition_out": "fade_out", "transition_out_duration": 1.0},
                    ],
                },
                {
                    "candidate_id": "balanced_cut",
                    "name": "Balanced Cut",
                    "editorial_approach": "balanced",
                    "reasoning": "Best overall flow",
                    "description": "Recommended edit",
                    "estimated_quality": 90.0,
                    "total_duration": 17.0,
                    "edits": [
                        {"scene_id": "scene_001", "selected_variation": 0, "in_point": 0.0, "out_point": 5.0, "duration": 5.0, "transition_in": "fade_in", "transition_in_duration": 0.5, "transition_out": "cut", "transition_out_duration": 0.0},
                        {"scene_id": "scene_002", "selected_variation": 0, "in_point": 0.0, "out_point": 8.0, "duration": 8.0, "transition_in": "cut", "transition_in_duration": 0.0, "transition_out": "dissolve", "transition_out_duration": 1.0},
                        {"scene_id": "scene_003", "selected_variation": 0, "in_point": 0.0, "out_point": 4.0, "duration": 4.0, "transition_in": "dissolve", "transition_in_duration": 1.0, "transition_out": "fade_out", "transition_out_duration": 1.0},
                    ],
                },
            ]
        })
        mock_claude_client.query.return_value = mock_response

        # Generate candidates
        candidates = await agent.generate_candidates(
            scenes=sample_scenes,
            video_candidates=sample_video_candidates,
            qa_results=sample_qa_results,
            original_request="Create a product video",
            num_candidates=3
        )

        # Check results
        assert len(candidates) == 3
        assert candidates[0].style == "safe"
        assert candidates[1].style == "creative"
        assert candidates[2].style == "balanced"

    def test_select_recommended_balanced(self):
        """Test selecting recommended candidate (prefers balanced)"""
        agent = EditorAgent()

        candidates = [
            EditCandidate(
                candidate_id="safe",
                name="Safe",
                style="safe",
                estimated_quality=85.0
            ),
            EditCandidate(
                candidate_id="balanced",
                name="Balanced",
                style="balanced",
                estimated_quality=88.0
            ),
            EditCandidate(
                candidate_id="creative",
                name="Creative",
                style="creative",
                estimated_quality=90.0
            ),
        ]

        recommended = agent.select_recommended(candidates)
        assert recommended == "balanced"

    def test_select_recommended_highest_quality(self):
        """Test selecting recommended candidate (falls back to highest quality)"""
        agent = EditorAgent()

        candidates = [
            EditCandidate(
                candidate_id="safe",
                name="Safe",
                style="safe",
                estimated_quality=85.0
            ),
            EditCandidate(
                candidate_id="creative",
                name="Creative",
                style="creative",
                estimated_quality=92.0
            ),
        ]

        recommended = agent.select_recommended(candidates)
        assert recommended == "creative"  # Highest quality when no balanced

    def test_select_recommended_empty(self):
        """Test selecting recommended with empty list"""
        agent = EditorAgent()
        recommended = agent.select_recommended([])
        assert recommended is None

    @pytest.mark.asyncio
    async def test_create_edl(self, mock_claude_client, sample_scenes, sample_video_candidates, sample_qa_results):
        """Test creating complete EDL"""
        agent = EditorAgent(claude_client=mock_claude_client)

        # Mock Claude response
        mock_response = json.dumps({
            "candidates": [
                {
                    "candidate_id": "balanced_cut",
                    "name": "Balanced Cut",
                    "editorial_approach": "balanced",
                    "reasoning": "Best overall",
                    "description": "Recommended",
                    "estimated_quality": 90.0,
                    "total_duration": 17.0,
                    "edits": [
                        {"scene_id": "scene_001", "selected_variation": 0, "in_point": 0.0, "out_point": 5.0, "duration": 5.0, "transition_in": "fade_in", "transition_in_duration": 0.5, "transition_out": "cut", "transition_out_duration": 0.0},
                        {"scene_id": "scene_002", "selected_variation": 0, "in_point": 0.0, "out_point": 8.0, "duration": 8.0, "transition_in": "cut", "transition_in_duration": 0.0, "transition_out": "dissolve", "transition_out_duration": 1.0},
                        {"scene_id": "scene_003", "selected_variation": 0, "in_point": 0.0, "out_point": 4.0, "duration": 4.0, "transition_in": "dissolve", "transition_in_duration": 1.0, "transition_out": "fade_out", "transition_out_duration": 1.0},
                    ],
                }
            ]
        })
        mock_claude_client.query.return_value = mock_response

        # Create EDL
        edl = await agent.create_edl(
            scenes=sample_scenes,
            video_candidates=sample_video_candidates,
            qa_results=sample_qa_results,
            original_request="Create a product video",
            num_candidates=1
        )

        # Check EDL structure
        assert edl.edl_id.startswith("edl_")
        assert len(edl.candidates) == 1
        assert edl.recommended_candidate_id == "balanced_cut"
        assert edl.total_scenes == 3
        assert edl.original_request == "Create a product video"
        assert ExportFormat.JSON in edl.export_formats

    @pytest.mark.asyncio
    async def test_run(self, mock_claude_client, sample_scenes, sample_video_candidates, sample_qa_results):
        """Test run method"""
        agent = EditorAgent(claude_client=mock_claude_client)

        # Mock Claude response
        mock_response = json.dumps({
            "candidates": [
                {
                    "candidate_id": "safe_cut",
                    "name": "Safe Cut",
                    "editorial_approach": "safe",
                    "reasoning": "Highest QA",
                    "description": "Safe",
                    "estimated_quality": 88.0,
                    "total_duration": 17.0,
                    "edits": [
                        {"scene_id": "scene_001", "selected_variation": 0, "in_point": 0.0, "out_point": 5.0, "duration": 5.0, "transition_in": "fade_in", "transition_in_duration": 0.5, "transition_out": "cut", "transition_out_duration": 0.0},
                    ],
                }
            ]
        })
        mock_claude_client.query.return_value = mock_response

        # Run
        edl = await agent.run(
            scenes=sample_scenes,
            video_candidates=sample_video_candidates,
            qa_results=sample_qa_results,
            original_request="Create a product video"
        )

        assert isinstance(edl, EditDecisionList)
        assert len(edl.candidates) > 0

    @pytest.mark.asyncio
    async def test_analyze_continuity(self, mock_claude_client):
        """Test continuity analysis"""
        agent = EditorAgent(claude_client=mock_claude_client)

        edit_sequence = [
            EditDecision(
                scene_id="scene_001",
                selected_variation=0,
                video_url="video1.mp4",
                transition_out="cut"
            ),
            EditDecision(
                scene_id="scene_002",
                selected_variation=0,
                video_url="video2.mp4",
                transition_in="cut"
            ),
        ]

        issues = await agent.analyze_continuity(edit_sequence)
        assert isinstance(issues, list)

    @pytest.mark.asyncio
    async def test_incorporate_feedback_approved(self, mock_claude_client):
        """Test incorporating feedback when approved"""
        agent = EditorAgent(claude_client=mock_claude_client)

        candidate = EditCandidate(
            candidate_id="test",
            name="Test",
            style="balanced"
        )

        feedback = HumanFeedback(
            candidate_id="test",
            approved=True,
            notes="Looks good!"
        )

        revised = await agent.incorporate_feedback(candidate, feedback)
        assert revised == candidate

    @pytest.mark.asyncio
    async def test_incorporate_feedback_not_approved(self, mock_claude_client):
        """Test incorporating feedback when not approved"""
        agent = EditorAgent(claude_client=mock_claude_client)

        candidate = EditCandidate(
            candidate_id="test",
            name="Test",
            style="balanced",
            reasoning="Original reasoning"
        )

        feedback = HumanFeedback(
            candidate_id="test",
            approved=False,
            notes="Needs work",
            requested_changes=["Change scene 2"],
            scenes_to_recut=["scene_002"]
        )

        # Should call Claude for revision
        mock_claude_client.query.return_value = "{}"

        revised = await agent.incorporate_feedback(candidate, feedback)
        assert isinstance(revised, EditCandidate)
        mock_claude_client.query.assert_called_once()

    def test_export_json(self):
        """Test exporting to JSON format"""
        agent = EditorAgent()

        candidate = EditCandidate(
            candidate_id="test",
            name="Test Edit",
            style="balanced",
            decisions=[
                EditDecision(
                    scene_id="scene_001",
                    selected_variation=0,
                    video_url="video.mp4"
                )
            ]
        )

        json_output = agent.export(candidate, ExportFormat.JSON)
        assert isinstance(json_output, str)

        # Verify it's valid JSON
        parsed = json.loads(json_output)
        assert parsed["candidate_id"] == "test"
        assert parsed["name"] == "Test Edit"

    def test_export_fcpxml(self):
        """Test exporting to Final Cut Pro XML"""
        agent = EditorAgent()

        candidate = EditCandidate(
            candidate_id="test",
            name="Test Edit",
            style="balanced",
            total_duration=10.0,
            decisions=[
                EditDecision(
                    scene_id="scene_001",
                    selected_variation=0,
                    video_url="video.mp4",
                    start_time=0.0,
                    duration=5.0,
                    in_point=0.0
                )
            ]
        )

        xml_output = agent.export(candidate, ExportFormat.FCPXML)
        assert isinstance(xml_output, str)
        assert '<?xml version="1.0"' in xml_output
        assert '<fcpxml' in xml_output
        assert 'scene_001' in xml_output

    def test_export_cmx3600(self):
        """Test exporting to CMX 3600 EDL format"""
        agent = EditorAgent()

        candidate = EditCandidate(
            candidate_id="test",
            name="Test Edit",
            style="balanced",
            decisions=[
                EditDecision(
                    scene_id="scene_001",
                    selected_variation=0,
                    video_url="video.mp4",
                    start_time=0.0,
                    duration=5.0,
                    in_point=0.0,
                    out_point=5.0
                )
            ]
        )

        edl_output = agent.export(candidate, ExportFormat.EDL_CMX3600)
        assert isinstance(edl_output, str)
        assert 'TITLE:' in edl_output
        assert 'FCM:' in edl_output
        assert '001' in edl_output

    def test_export_davinci(self):
        """Test exporting to DaVinci Resolve format"""
        agent = EditorAgent()

        candidate = EditCandidate(
            candidate_id="test",
            name="Test Edit",
            style="balanced",
            decisions=[
                EditDecision(
                    scene_id="scene_001",
                    selected_variation=0,
                    video_url="video.mp4",
                    start_time=0.0,
                    duration=5.0,
                    in_point=0.0,
                    out_point=5.0
                )
            ]
        )

        xml_output = agent.export(candidate, ExportFormat.DAVINCI)
        assert isinstance(xml_output, str)
        assert '<?xml version="1.0"' in xml_output
        assert '<xmeml' in xml_output

    def test_export_premiere(self):
        """Test exporting to Adobe Premiere format"""
        agent = EditorAgent()

        candidate = EditCandidate(
            candidate_id="test",
            name="Test Edit",
            style="balanced",
            decisions=[
                EditDecision(
                    scene_id="scene_001",
                    selected_variation=0,
                    video_url="video.mp4",
                    start_time=0.0,
                    duration=5.0,
                    in_point=0.0,
                    out_point=5.0
                )
            ]
        )

        xml_output = agent.export(candidate, ExportFormat.PREMIERE)
        assert isinstance(xml_output, str)
        assert '<?xml version="1.0"' in xml_output

    def test_seconds_to_timecode(self):
        """Test timecode conversion"""
        agent = EditorAgent()

        # Test various times
        assert agent._seconds_to_timecode(0.0) == "00:00:00:00"
        assert agent._seconds_to_timecode(1.0) == "00:00:01:00"
        assert agent._seconds_to_timecode(60.0) == "00:01:00:00"
        assert agent._seconds_to_timecode(3600.0) == "01:00:00:00"

        # Test with frames
        assert agent._seconds_to_timecode(1.5, fps=24) == "00:00:01:12"  # 0.5s * 24fps = 12 frames


class TestEditorIntegration:
    """Integration-style tests"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import EditorAgent
        assert EditorAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "editor" in AGENT_REGISTRY
        assert AGENT_REGISTRY["editor"]["class"] == "EditorAgent"
        assert AGENT_REGISTRY["editor"]["module"] == "agents.editor"
        assert AGENT_REGISTRY["editor"]["status"] == "implemented"

    def test_models_can_be_imported(self):
        """Test that edit decision models can be imported"""
        from core.models import (
            EditDecision,
            EditCandidate,
            EditDecisionList,
            ExportFormat,
            HumanFeedback,
        )
        assert EditDecision is not None
        assert EditCandidate is not None
        assert EditDecisionList is not None
        assert ExportFormat is not None
        assert HumanFeedback is not None
