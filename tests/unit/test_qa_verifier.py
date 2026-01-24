"""Unit tests for QAVerifierAgent"""

import pytest
from unittest.mock import AsyncMock
from agents.qa_verifier import QAVerifierAgent, QAResult, QA_THRESHOLDS
from agents.script_writer import Scene
from agents.video_generator import GeneratedVideo
from core.budget import ProductionTier
from tests.mocks import MockClaudeClient


@pytest.fixture
def sample_scene():
    """Create a sample scene for testing"""
    return Scene(
        scene_id="test_scene",
        title="Test Scene",
        description="A beautiful landscape with mountains",
        duration=5.0,
        visual_elements=["mountains", "lake", "sunset"],
        audio_notes="Calm music",
        transition_in="fade_in",
        transition_out="fade_out",
        prompt_hints=["cinematic", "wide shot"]
    )


@pytest.fixture
def sample_video():
    """Create a sample generated video for testing"""
    return GeneratedVideo(
        scene_id="test_scene",
        variation_id=0,
        video_url="https://example.com/video.mp4",
        thumbnail_url="https://example.com/thumb.jpg",
        duration=5.0,
        generation_cost=0.75,
        provider="mock",
        metadata={"resolution": "1920x1080"}
    )


class TestQAVerifierAgent:
    """Test QAVerifierAgent initialization and basic functionality"""

    def test_initialization(self):
        """Test agent initializes with provided client"""
        mock_client = MockClaudeClient()
        agent = QAVerifierAgent(claude_client=mock_client, mock_mode=True)
        assert agent.claude == mock_client
        assert agent.mock_mode == True

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = QAVerifierAgent()
        assert agent.claude is not None

    def test_initialization_defaults(self):
        """Test default initialization parameters"""
        agent = QAVerifierAgent()
        assert agent.mock_mode == True  # Default to mock mode
        assert agent.num_frames == 5
        assert agent.use_vision == True

    def test_is_stub_attribute(self):
        """Test that _is_stub attribute is set correctly"""
        assert hasattr(QAVerifierAgent, "_is_stub")
        assert QAVerifierAgent._is_stub == False

    @pytest.mark.asyncio
    async def test_verify_video_mock_mode(self, sample_scene, sample_video):
        """Test video verification in mock mode"""
        agent = QAVerifierAgent(mock_mode=True)

        result = await agent.verify_video(
            scene=sample_scene,
            generated_video=sample_video,
            original_request="Create a nature video",
            production_tier=ProductionTier.ANIMATED
        )

        assert isinstance(result, QAResult)
        assert result.scene_id == "test_scene"
        assert result.video_url == sample_video.video_url
        assert 0 <= result.overall_score <= 100
        assert 0 <= result.visual_accuracy <= 100
        assert 0 <= result.style_consistency <= 100
        assert 0 <= result.technical_quality <= 100
        assert 0 <= result.narrative_fit <= 100
        assert isinstance(result.issues, list)
        assert isinstance(result.suggestions, list)
        assert isinstance(result.passed, bool)
        assert result.threshold == QA_THRESHOLDS[ProductionTier.ANIMATED]

        # Enriched visual analysis should be populated in mock mode
        assert result.visual_analysis is not None
        assert result.visual_analysis.frames_analyzed == agent.num_frames
        assert len(result.visual_analysis.frame_analyses) == agent.num_frames
        assert result.visual_analysis.primary_subject != ""
        assert isinstance(result.visual_analysis.matched_elements, list)
        assert isinstance(result.visual_analysis.missing_elements, list)
        assert result.visual_analysis.provider_observations is not None
        assert "strengths" in result.visual_analysis.provider_observations
        assert "weaknesses" in result.visual_analysis.provider_observations

        # Frame timestamps should be populated
        assert len(result.frame_timestamps) == agent.num_frames
        assert all(t > 0 for t in result.frame_timestamps)

    @pytest.mark.asyncio
    async def test_verify_video_quality_varies_by_tier(self, sample_scene, sample_video):
        """Test that quality scores respect tier ceilings"""
        agent = QAVerifierAgent(mock_mode=True)

        # Test multiple runs to check score distribution
        scores_static = []
        scores_photo = []

        for _ in range(5):
            result_static = await agent.verify_video(
                scene=sample_scene,
                generated_video=sample_video,
                original_request="Test",
                production_tier=ProductionTier.STATIC_IMAGES
            )
            scores_static.append(result_static.overall_score)

            result_photo = await agent.verify_video(
                scene=sample_scene,
                generated_video=sample_video,
                original_request="Test",
                production_tier=ProductionTier.PHOTOREALISTIC
            )
            scores_photo.append(result_photo.overall_score)

        # Photorealistic should generally score higher
        avg_static = sum(scores_static) / len(scores_static)
        avg_photo = sum(scores_photo) / len(scores_photo)

        # Static images ceiling is 75, photorealistic is 95
        assert avg_static < 75
        assert avg_photo > avg_static

    @pytest.mark.asyncio
    async def test_verify_video_threshold_enforcement(self, sample_scene, sample_video):
        """Test that pass/fail respects tier thresholds"""
        agent = QAVerifierAgent(mock_mode=True)

        # Animated tier threshold is 80
        result = await agent.verify_video(
            scene=sample_scene,
            generated_video=sample_video,
            original_request="Test",
            production_tier=ProductionTier.ANIMATED
        )

        if result.overall_score >= 80:
            assert result.passed == True
        else:
            assert result.passed == False

    @pytest.mark.asyncio
    async def test_verify_batch(self, sample_scene, sample_video):
        """Test batch verification of multiple videos"""
        agent = QAVerifierAgent(mock_mode=True)

        scenes = [sample_scene, sample_scene]
        videos = [sample_video, sample_video]

        results = await agent.verify_batch(
            scenes=scenes,
            videos=videos,
            original_request="Test batch",
            production_tier=ProductionTier.MOTION_GRAPHICS
        )

        assert len(results) == 2
        assert all(isinstance(r, QAResult) for r in results)

    def test_get_quality_gate(self):
        """Test quality gate classification"""
        agent = QAVerifierAgent()

        assert agent.get_quality_gate(95) == "excellent"
        assert agent.get_quality_gate(90) == "excellent"
        assert agent.get_quality_gate(85) == "pass"
        assert agent.get_quality_gate(80) == "pass"
        assert agent.get_quality_gate(70) == "soft_fail"
        assert agent.get_quality_gate(50) == "soft_fail"
        assert agent.get_quality_gate(40) == "hard_fail"

    def test_should_regenerate_hard_fail(self):
        """Test regeneration decision for hard fail"""
        agent = QAVerifierAgent()

        result = QAResult(
            scene_id="test",
            video_url="url",
            overall_score=40.0,  # Hard fail
            visual_accuracy=45.0,
            style_consistency=40.0,
            technical_quality=35.0,
            narrative_fit=40.0,
            issues=["Poor quality"],
            suggestions=["Regenerate"],
            passed=False,
            threshold=70.0
        )

        # Should regenerate if budget allows
        assert agent.should_regenerate(result, budget_available=10.0, regeneration_cost=5.0) == True

        # Should not regenerate if insufficient budget
        assert agent.should_regenerate(result, budget_available=3.0, regeneration_cost=5.0) == False

    def test_should_regenerate_soft_fail(self):
        """Test regeneration decision for soft fail"""
        agent = QAVerifierAgent()

        result = QAResult(
            scene_id="test",
            video_url="url",
            overall_score=75.0,  # Soft fail (below 80 for animated)
            visual_accuracy=78.0,
            style_consistency=75.0,
            technical_quality=72.0,
            narrative_fit=75.0,
            issues=["Minor issues"],
            suggestions=["Could improve"],
            passed=False,
            threshold=80.0
        )

        # Should regenerate with comfortable budget (1.5x cost)
        assert agent.should_regenerate(result, budget_available=15.0, regeneration_cost=5.0) == True

        # Should not regenerate with tight budget
        assert agent.should_regenerate(result, budget_available=6.0, regeneration_cost=5.0) == False

    def test_should_regenerate_pass(self):
        """Test regeneration decision for passing video"""
        agent = QAVerifierAgent()

        result = QAResult(
            scene_id="test",
            video_url="url",
            overall_score=85.0,  # Pass but not excellent
            visual_accuracy=87.0,
            style_consistency=83.0,
            technical_quality=85.0,
            narrative_fit=85.0,
            issues=[],
            suggestions=[],
            passed=True,
            threshold=80.0
        )

        # Should only regenerate with ample budget (2.5x cost)
        assert agent.should_regenerate(result, budget_available=20.0, regeneration_cost=5.0) == True
        assert agent.should_regenerate(result, budget_available=10.0, regeneration_cost=5.0) == False

    def test_should_regenerate_excellent(self):
        """Test regeneration decision for excellent video"""
        agent = QAVerifierAgent()

        result = QAResult(
            scene_id="test",
            video_url="url",
            overall_score=92.0,  # Excellent
            visual_accuracy=93.0,
            style_consistency=91.0,
            technical_quality=92.0,
            narrative_fit=92.0,
            issues=[],
            suggestions=[],
            passed=True,
            threshold=80.0
        )

        # Should never regenerate excellent results
        assert agent.should_regenerate(result, budget_available=100.0, regeneration_cost=5.0) == False


class TestQAResult:
    """Test QAResult dataclass"""

    def test_qa_result_creation(self):
        """Test creating QAResult"""
        result = QAResult(
            scene_id="scene_001",
            video_url="https://example.com/video.mp4",
            overall_score=85.5,
            visual_accuracy=87.0,
            style_consistency=84.0,
            technical_quality=86.0,
            narrative_fit=85.0,
            issues=["Minor color grading issue"],
            suggestions=["Adjust contrast slightly"],
            passed=True,
            threshold=80.0
        )

        assert result.scene_id == "scene_001"
        assert result.overall_score == 85.5
        assert result.visual_accuracy == 87.0
        assert result.passed == True
        assert len(result.issues) == 1
        assert len(result.suggestions) == 1


class TestQAThresholds:
    """Test QA threshold constants"""

    def test_thresholds_exist(self):
        """Test that thresholds are defined for all tiers"""
        assert ProductionTier.STATIC_IMAGES in QA_THRESHOLDS
        assert ProductionTier.MOTION_GRAPHICS in QA_THRESHOLDS
        assert ProductionTier.ANIMATED in QA_THRESHOLDS
        assert ProductionTier.PHOTOREALISTIC in QA_THRESHOLDS

    def test_thresholds_increase_with_tier(self):
        """Test that thresholds increase for higher quality tiers"""
        assert QA_THRESHOLDS[ProductionTier.STATIC_IMAGES] < QA_THRESHOLDS[ProductionTier.MOTION_GRAPHICS]
        assert QA_THRESHOLDS[ProductionTier.MOTION_GRAPHICS] < QA_THRESHOLDS[ProductionTier.ANIMATED]
        assert QA_THRESHOLDS[ProductionTier.ANIMATED] < QA_THRESHOLDS[ProductionTier.PHOTOREALISTIC]


class TestQAVerifierIntegration:
    """Integration tests for QAVerifierAgent"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import QAVerifierAgent as ImportedAgent
        assert ImportedAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "qa_verifier" in AGENT_REGISTRY
        assert AGENT_REGISTRY["qa_verifier"]["status"] == "implemented"
        assert AGENT_REGISTRY["qa_verifier"]["class"] == "QAVerifierAgent"

    def test_qa_result_can_be_imported(self):
        """Test that QAResult model can be imported"""
        from agents.qa_verifier import QAResult as ImportedQAResult
        assert ImportedQAResult is not None
