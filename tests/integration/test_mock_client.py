"""Integration test for MockClaudeClient with agents"""

import pytest
from agents.producer import ProducerAgent
from agents.script_writer import ScriptWriterAgent
from core.budget import ProductionTier


@pytest.mark.integration
@pytest.mark.asyncio
async def test_producer_with_mock_client(mock_claude_client):
    """Test ProducerAgent works with MockClaudeClient"""

    producer = ProducerAgent(claude_client=mock_claude_client)

    pilots = await producer.analyze_and_plan(
        user_request="Create a 60-second video about AI",
        total_budget=100.0
    )

    # Should have generated pilots
    assert len(pilots) == 2
    assert pilots[0].pilot_id == "pilot_budget"
    assert pilots[1].pilot_id == "pilot_quality"

    # Should have made exactly one call
    assert mock_claude_client.get_call_count() == 1

    # Call should have contained relevant keywords
    mock_claude_client.assert_called_with_prompt_containing("pilot strategies")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_script_writer_with_mock_client(mock_claude_client):
    """Test ScriptWriterAgent works with MockClaudeClient"""

    script_writer = ScriptWriterAgent(claude_client=mock_claude_client)

    scenes = await script_writer.create_script(
        video_concept="Developer workflow",
        target_duration=10.0,
        production_tier=ProductionTier.ANIMATED,
        num_scenes=2
    )

    # Should have generated scenes
    assert len(scenes) == 2
    assert scenes[0].scene_id == "scene_1"
    assert scenes[1].scene_id == "scene_2"

    # Should have made exactly one call
    assert mock_claude_client.get_call_count() == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_client_call_tracking(mock_claude_client):
    """Test MockClaudeClient tracks calls correctly"""

    # Make multiple calls
    await mock_claude_client.query("pilot strategies test")
    await mock_claude_client.query("another query")

    assert mock_claude_client.get_call_count() == 2
    assert len(mock_claude_client.calls) == 2

    # Reset should clear tracking
    mock_claude_client.reset()
    assert mock_claude_client.get_call_count() == 0
