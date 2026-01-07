"""Unit tests for ProducerAgent"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from agents.producer import ProducerAgent, PilotStrategy
from core.budget import ProductionTier
from tests.mocks import MockClaudeClient


class TestProducerAgent:
    """Test ProducerAgent initialization and basic functionality"""

    def test_initialization(self):
        """Test agent initializes with provided client"""
        mock_client = MockClaudeClient()
        agent = ProducerAgent(claude_client=mock_client)
        assert agent.claude == mock_client

    def test_initialization_without_client(self):
        """Test agent creates its own client if none provided"""
        agent = ProducerAgent()
        assert agent.claude is not None

    def test_is_stub_attribute(self):
        """Test that _is_stub attribute is set correctly"""
        assert hasattr(ProducerAgent, "_is_stub")
        assert ProducerAgent._is_stub == False

    @pytest.mark.asyncio
    async def test_analyze_and_plan(self):
        """Test analyze_and_plan creates pilot strategies"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "total_scenes_estimated": 12,
            "pilots": [
                {
                    "pilot_id": "pilot_a",
                    "tier": "motion_graphics",
                    "rationale": "Cost-effective baseline",
                    "allocated_budget": 60.0,
                    "test_scene_count": 3
                },
                {
                    "pilot_id": "pilot_b",
                    "tier": "animated",
                    "rationale": "Higher quality option",
                    "allocated_budget": 80.0,
                    "test_scene_count": 3
                }
            ]
        }""")

        agent = ProducerAgent(claude_client=mock_client)
        pilots = await agent.analyze_and_plan(
            user_request="Create a 30 second video about AI",
            total_budget=150.0
        )

        assert len(pilots) == 2
        assert pilots[0].pilot_id == "pilot_a"
        assert pilots[0].tier == ProductionTier.MOTION_GRAPHICS
        assert pilots[0].allocated_budget == 60.0
        assert pilots[0].test_scene_count == 3
        assert pilots[0].full_scene_count == 12

        assert pilots[1].pilot_id == "pilot_b"
        assert pilots[1].tier == ProductionTier.ANIMATED
        assert pilots[1].allocated_budget == 80.0

    @pytest.mark.asyncio
    async def test_analyze_and_plan_single_pilot(self):
        """Test analyze_and_plan with single pilot"""
        mock_client = MockClaudeClient()
        mock_client.add_response("""{
            "total_scenes_estimated": 10,
            "pilots": [
                {
                    "pilot_id": "pilot_only",
                    "tier": "photorealistic",
                    "rationale": "Premium quality",
                    "allocated_budget": 200.0,
                    "test_scene_count": 4
                }
            ]
        }""")

        agent = ProducerAgent(claude_client=mock_client)
        pilots = await agent.analyze_and_plan(
            user_request="Create a product demo",
            total_budget=200.0
        )

        assert len(pilots) == 1
        assert pilots[0].tier == ProductionTier.PHOTOREALISTIC

    def test_estimate_pilot_cost(self):
        """Test cost estimation for pilot test phase"""
        agent = ProducerAgent()

        pilot = PilotStrategy(
            pilot_id="test_pilot",
            tier=ProductionTier.ANIMATED,
            allocated_budget=100.0,
            test_scene_count=3,
            full_scene_count=12,
            rationale="Test"
        )

        # Estimate: 3 scenes * 5s * 3 variations * $0.15/s = $6.75 video
        # Plus Claude costs (~$0.01)
        cost = agent.estimate_pilot_cost(
            pilot=pilot,
            num_variations=3,
            avg_duration_per_scene=5.0
        )

        assert cost > 0
        assert cost < pilot.allocated_budget
        # Should be around $6.75-$12.00 (varies by Claude token estimate)
        assert 6.0 < cost < 15.0

    def test_estimate_pilot_cost_different_tiers(self):
        """Test cost varies by tier"""
        agent = ProducerAgent()

        pilot_static = PilotStrategy(
            pilot_id="static",
            tier=ProductionTier.STATIC_IMAGES,
            allocated_budget=50.0,
            test_scene_count=3,
            full_scene_count=10,
            rationale="Low cost"
        )

        pilot_photorealistic = PilotStrategy(
            pilot_id="photo",
            tier=ProductionTier.PHOTOREALISTIC,
            allocated_budget=200.0,
            test_scene_count=3,
            full_scene_count=10,
            rationale="High quality"
        )

        cost_static = agent.estimate_pilot_cost(pilot_static)
        cost_photo = agent.estimate_pilot_cost(pilot_photorealistic)

        # Photorealistic should cost significantly more
        assert cost_photo > cost_static
        assert cost_photo > cost_static * 5  # At least 5x more

    def test_estimate_pilot_cost_with_more_variations(self):
        """Test cost scales with variation count"""
        agent = ProducerAgent()

        pilot = PilotStrategy(
            pilot_id="test",
            tier=ProductionTier.MOTION_GRAPHICS,
            allocated_budget=100.0,
            test_scene_count=2,
            full_scene_count=10,
            rationale="Test"
        )

        cost_2_vars = agent.estimate_pilot_cost(pilot, num_variations=2)
        cost_5_vars = agent.estimate_pilot_cost(pilot, num_variations=5)

        # 5 variations should cost more than double 2 variations
        assert cost_5_vars > cost_2_vars * 2


class TestPilotStrategy:
    """Test PilotStrategy dataclass"""

    def test_pilot_strategy_creation(self):
        """Test creating PilotStrategy"""
        pilot = PilotStrategy(
            pilot_id="test_pilot",
            tier=ProductionTier.ANIMATED,
            allocated_budget=100.0,
            test_scene_count=3,
            full_scene_count=12,
            rationale="Testing"
        )

        assert pilot.pilot_id == "test_pilot"
        assert pilot.tier == ProductionTier.ANIMATED
        assert pilot.allocated_budget == 100.0
        assert pilot.test_scene_count == 3
        assert pilot.full_scene_count == 12
        assert pilot.rationale == "Testing"


class TestProducerIntegration:
    """Integration tests for ProducerAgent"""

    def test_agent_can_be_imported(self):
        """Test that agent can be imported from agents package"""
        from agents import ProducerAgent as ImportedAgent
        assert ImportedAgent is not None

    def test_agent_in_registry(self):
        """Test that agent is registered in AGENT_REGISTRY"""
        from agents import AGENT_REGISTRY
        assert "producer" in AGENT_REGISTRY
        assert AGENT_REGISTRY["producer"]["status"] == "implemented"
        assert AGENT_REGISTRY["producer"]["class"] == "ProducerAgent"
