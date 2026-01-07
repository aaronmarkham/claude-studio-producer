"""Unit tests for CriticAgent"""

import pytest
from unittest.mock import AsyncMock
from agents.critic import CriticAgent, SceneResult, PilotResults
from agents.producer import PilotStrategy
from core.budget import ProductionTier
from tests.mocks import MockClaudeClient


@pytest.fixture
def sample_pilot():
    """Create a sample pilot strategy for testing"""
    return PilotStrategy(
        pilot_id="test_pilot",
        tier=ProductionTier.ANIMATED,
        allocated_budget=100.0,
        test_scene_count=3,
        full_scene_count=12,
        rationale="Test pilot for animated tier"
    )


@pytest.fixture
def sample_scene_results():
    """Create sample scene results for testing"""
    return [
        SceneResult(
            scene_id="scene_001",
            description="Opening shot with city skyline",
            video_url="https://example.com/scene_001.mp4",
            qa_score=85.0,
            generation_cost=1.50
        ),
        SceneResult(
            scene_id="scene_002",
            description="Product demo interface",
            video_url="https://example.com/scene_002.mp4",
            qa_score=82.0,
            generation_cost=1.75
        ),
        SceneResult(
            scene_id="scene_003",
            description="Closing call to action",
            video_url="https://example.com/scene_003.mp4",
            qa_score=88.0,
            generation_cost=1.25
        )
    ]


class TestCriticAgent:
    """Test CriticAgent initialization and basic functionality"""

    def test_initialization(self):
        """Test agent initializes with provided client"""
        mock_client = MockClaudeClient()
        agent = CriticAgent(claude_client=mock_client)
        assert agent.claude == mock_client

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = CriticAgent()
        assert agent.claude is not None

    def test_initialization_defaults(self):
        """Test default initialization parameters"""
        agent = CriticAgent()
        assert agent.quality_threshold == 65

    def test_is_stub_attribute(self):
        """Test that _is_stub attribute is set correctly"""
        assert hasattr(CriticAgent, "_is_stub")
        assert CriticAgent._is_stub == False

    @pytest.mark.asyncio
    async def test_evaluate_pilot_approved(self, sample_pilot, sample_scene_results):
        """Test pilot evaluation with approval"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "overall_score": 85,
            "gap_analysis": {
                "matched_elements": ["visual style", "pacing", "quality"],
                "missing_elements": [],
                "quality_issues": ["minor color adjustments needed"]
            },
            "decision": "continue",
            "budget_multiplier": 1.0,
            "reasoning": "Strong execution matching the creative brief",
            "adjustments_needed": ["Fine-tune color grading"]
        }""")

        agent = CriticAgent(claude_client=mock_client)
        result = await agent.evaluate_pilot(
            original_request="Create an engaging product demo",
            pilot=sample_pilot,
            scene_results=sample_scene_results,
            budget_spent=4.50,
            budget_allocated=100.0
        )

        assert isinstance(result, PilotResults)
        assert result.pilot_id == "test_pilot"
        assert result.tier == "animated"
        assert len(result.scenes_generated) == 3
        assert result.total_cost == 4.50
        assert result.avg_qa_score == 85.0  # (85 + 82 + 88) / 3
        assert result.critic_score == 85
        assert result.approved == True
        assert result.budget_remaining > 0
        assert "matched_elements" in result.gap_analysis
        assert len(result.adjustments_needed) > 0

    @pytest.mark.asyncio
    async def test_evaluate_pilot_rejected(self, sample_pilot, sample_scene_results):
        """Test pilot evaluation with rejection"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "overall_score": 60,
            "gap_analysis": {
                "matched_elements": ["basic structure"],
                "missing_elements": ["key visual elements", "proper pacing"],
                "quality_issues": ["poor execution", "off-brand"]
            },
            "decision": "cancel",
            "budget_multiplier": 0.0,
            "reasoning": "Does not match creative brief, quality below threshold",
            "adjustments_needed": ["Complete rework needed"]
        }""")

        agent = CriticAgent(claude_client=mock_client)
        result = await agent.evaluate_pilot(
            original_request="Create an engaging product demo",
            pilot=sample_pilot,
            scene_results=sample_scene_results,
            budget_spent=4.50,
            budget_allocated=100.0
        )

        assert result.critic_score == 60
        assert result.approved == False
        assert result.budget_remaining == 0  # Canceled, no more budget

    @pytest.mark.asyncio
    async def test_evaluate_pilot_partial_budget(self, sample_pilot, sample_scene_results):
        """Test pilot evaluation with reduced budget allocation"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "overall_score": 75,
            "gap_analysis": {
                "matched_elements": ["visual style"],
                "missing_elements": ["some details"],
                "quality_issues": ["needs refinement"]
            },
            "decision": "continue",
            "budget_multiplier": 0.5,
            "reasoning": "Acceptable but needs improvement",
            "adjustments_needed": ["Improve detail", "Refine pacing"]
        }""")

        agent = CriticAgent(claude_client=mock_client)
        result = await agent.evaluate_pilot(
            original_request="Test",
            pilot=sample_pilot,
            scene_results=sample_scene_results,
            budget_spent=10.0,
            budget_allocated=100.0
        )

        assert result.approved == True
        # Remaining: 100 - 10 = 90, multiplied by 0.5 = 45
        assert result.budget_remaining == 45.0

    def test_format_scene_results(self, sample_scene_results):
        """Test formatting scene results for prompt"""
        agent = CriticAgent()

        scene_dicts = [
            {
                "scene_id": r.scene_id,
                "description": r.description,
                "qa_score": r.qa_score,
                "cost": r.generation_cost
            }
            for r in sample_scene_results
        ]

        formatted = agent._format_scene_results(scene_dicts)

        assert "Scene 1:" in formatted
        assert "scene_001" in formatted
        assert "QA Score: 85.0/100" in formatted
        assert "Cost: $1.50" in formatted

    def test_compare_pilots_single_approved(self):
        """Test comparing pilots when only one is approved"""
        agent = CriticAgent()

        pilots = [
            PilotResults(
                pilot_id="pilot_a",
                tier="motion_graphics",
                scenes_generated=[],
                total_cost=10.0,
                avg_qa_score=70.0,
                critic_score=65,
                approved=False
            ),
            PilotResults(
                pilot_id="pilot_b",
                tier="animated",
                scenes_generated=[],
                total_cost=15.0,
                avg_qa_score=85.0,
                critic_score=80,
                approved=True
            )
        ]

        best = agent.compare_pilots(pilots)
        assert best.pilot_id == "pilot_b"

    def test_compare_pilots_multiple_approved(self):
        """Test comparing multiple approved pilots"""
        agent = CriticAgent()

        pilots = [
            PilotResults(
                pilot_id="pilot_a",
                tier="motion_graphics",
                scenes_generated=[],
                total_cost=10.0,
                avg_qa_score=80.0,
                critic_score=75,
                approved=True
            ),
            PilotResults(
                pilot_id="pilot_b",
                tier="animated",
                scenes_generated=[],
                total_cost=15.0,
                avg_qa_score=85.0,
                critic_score=85,
                approved=True
            ),
            PilotResults(
                pilot_id="pilot_c",
                tier="photorealistic",
                scenes_generated=[],
                total_cost=25.0,
                avg_qa_score=90.0,
                critic_score=80,
                approved=True
            )
        ]

        best = agent.compare_pilots(pilots)
        # Should pick pilot_b (highest critic_score among approved)
        assert best.pilot_id == "pilot_b"

    def test_compare_pilots_none_approved(self):
        """Test comparing pilots when none are approved"""
        agent = CriticAgent()

        pilots = [
            PilotResults(
                pilot_id="pilot_a",
                tier="motion_graphics",
                scenes_generated=[],
                total_cost=10.0,
                avg_qa_score=60.0,
                critic_score=55,
                approved=False
            ),
            PilotResults(
                pilot_id="pilot_b",
                tier="animated",
                scenes_generated=[],
                total_cost=15.0,
                avg_qa_score=65.0,
                critic_score=60,
                approved=False
            )
        ]

        best = agent.compare_pilots(pilots)
        assert best is None

    def test_compare_pilots_cost_efficiency(self):
        """Test that cost efficiency is considered as tiebreaker"""
        agent = CriticAgent()

        pilots = [
            PilotResults(
                pilot_id="pilot_expensive",
                tier="photorealistic",
                scenes_generated=[],
                total_cost=50.0,
                avg_qa_score=80.0,
                critic_score=85,
                approved=True
            ),
            PilotResults(
                pilot_id="pilot_efficient",
                tier="animated",
                scenes_generated=[],
                total_cost=15.0,
                avg_qa_score=80.0,
                critic_score=85,
                approved=True
            )
        ]

        best = agent.compare_pilots(pilots)
        # Same critic score, but pilot_efficient has better QA/cost ratio
        # 80/15 = 5.33 vs 80/50 = 1.6
        assert best.pilot_id == "pilot_efficient"


class TestSceneResult:
    """Test SceneResult dataclass"""

    def test_scene_result_creation(self):
        """Test creating SceneResult"""
        result = SceneResult(
            scene_id="scene_test",
            description="Test scene description",
            video_url="https://example.com/video.mp4",
            qa_score=87.5,
            generation_cost=2.50
        )

        assert result.scene_id == "scene_test"
        assert result.description == "Test scene description"
        assert result.qa_score == 87.5
        assert result.generation_cost == 2.50


class TestPilotResults:
    """Test PilotResults dataclass"""

    def test_pilot_results_creation(self):
        """Test creating PilotResults"""
        scene_result = SceneResult(
            scene_id="s1",
            description="Scene 1",
            video_url="url",
            qa_score=85.0,
            generation_cost=1.0
        )

        result = PilotResults(
            pilot_id="test_pilot",
            tier="animated",
            scenes_generated=[scene_result],
            total_cost=5.0,
            avg_qa_score=85.0,
            critic_score=80,
            approved=True,
            budget_remaining=50.0,
            gap_analysis={"matched": [], "missing": []},
            critic_reasoning="Good work",
            adjustments_needed=["Minor tweaks"]
        )

        assert result.pilot_id == "test_pilot"
        assert result.tier == "animated"
        assert len(result.scenes_generated) == 1
        assert result.approved == True
        assert result.critic_score == 80

    def test_pilot_results_defaults(self):
        """Test PilotResults default values"""
        result = PilotResults(
            pilot_id="test",
            tier="motion_graphics",
            scenes_generated=[],
            total_cost=0.0,
            avg_qa_score=0.0
        )

        assert result.critic_score == 0
        assert result.approved == False
        assert result.budget_remaining == 0
        assert result.gap_analysis is None
        assert result.critic_reasoning == ""
        assert result.adjustments_needed is None


class TestCriticIntegration:
    """Integration tests for CriticAgent"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import CriticAgent as ImportedAgent
        assert ImportedAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "critic" in AGENT_REGISTRY
        assert AGENT_REGISTRY["critic"]["status"] == "implemented"
        assert AGENT_REGISTRY["critic"]["class"] == "CriticAgent"

    def test_models_can_be_imported(self):
        """Test that models can be imported"""
        from agents.critic import SceneResult, PilotResults
        assert SceneResult is not None
        assert PilotResults is not None
