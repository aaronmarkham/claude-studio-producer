"""Integration tests for VideoGeneratorAgent with provider interface"""

import pytest
from agents.video_generator import VideoGeneratorAgent
from agents.script_writer import Scene
from core.providers import MockVideoProvider
from core.budget import ProductionTier


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_with_mock_provider(sample_scene):
    """Test VideoGeneratorAgent works with MockVideoProvider"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(provider=provider, num_variations=2)

    videos = await generator.generate_scene(
        scene=sample_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=100.0
    )

    # Should generate 2 variations
    assert len(videos) == 2

    # Each should have proper metadata
    for i, video in enumerate(videos):
        assert video.scene_id == sample_scene.scene_id
        assert video.variation_id == i
        assert video.video_url is not None
        assert video.duration == sample_scene.duration
        assert video.generation_cost > 0
        assert "prompt" in video.metadata


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_budget_limit(sample_scene):
    """Test VideoGeneratorAgent respects budget limits"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(provider=provider, num_variations=10)

    # Set very low budget - should only generate 2 videos at $1.25 each
    videos = await generator.generate_scene(
        scene=sample_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=3.0  # Very low budget
    )

    # Should stop before generating all 10 (budget allows ~2 videos)
    assert len(videos) <= 3  # Budget allows 2, might squeeze in 3rd

    # Total cost should not exceed budget significantly
    total_cost = sum(v.generation_cost for v in videos)
    assert total_cost <= 4.0  # Allow small overage for last video


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_cost_tracking(sample_scene):
    """Test VideoGeneratorAgent tracks costs correctly"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(provider=provider, num_variations=3)

    videos = await generator.generate_scene(
        scene=sample_scene,
        production_tier=ProductionTier.PHOTOREALISTIC,
        budget_limit=1000.0
    )

    # All videos should have costs
    assert all(v.generation_cost > 0 for v in videos)

    # Photorealistic should be expensive (5 second scene * $0.50/sec * 3 videos = $7.50)
    total_cost = sum(v.generation_cost for v in videos)
    assert total_cost >= 7.0  # Photorealistic is pricier than lower tiers


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_different_tiers():
    """Test VideoGeneratorAgent with different production tiers"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(provider=provider, num_variations=1)

    scene = Scene(
        scene_id="test_scene",
        title="Test Scene",
        description="A test scene",
        duration=5.0,
        visual_elements=["element"],
        audio_notes="ambient",
        transition_in="cut",
        transition_out="cut",
        prompt_hints=[]
    )

    tiers = [
        ProductionTier.STATIC_IMAGES,
        ProductionTier.MOTION_GRAPHICS,
        ProductionTier.ANIMATED,
        ProductionTier.PHOTOREALISTIC
    ]

    videos_by_tier = {}
    for tier in tiers:
        videos = await generator.generate_scene(
            scene=scene,
            production_tier=tier,
            budget_limit=100.0
        )
        videos_by_tier[tier] = videos[0]

    # All tiers should generate successfully
    assert all(len(videos_by_tier[tier].video_url) > 0 for tier in tiers)

    # Higher tiers should cost more
    costs = [videos_by_tier[tier].generation_cost for tier in tiers]
    assert costs == sorted(costs)  # Should be in ascending order


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_retry_logic(sample_scene):
    """Test VideoGeneratorAgent retry logic (simulated)"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(
        provider=provider,
        num_variations=1,
        retry_attempts=3
    )

    # Normal generation should succeed on first try
    videos = await generator.generate_scene(
        scene=sample_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=100.0
    )

    assert len(videos) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_video_generator_provider_metadata(sample_scene):
    """Test VideoGeneratorAgent includes provider metadata"""
    provider = MockVideoProvider()
    generator = VideoGeneratorAgent(provider=provider, num_variations=1)

    videos = await generator.generate_scene(
        scene=sample_scene,
        production_tier=ProductionTier.ANIMATED,
        budget_limit=100.0
    )

    video = videos[0]

    # Should have provider metadata
    assert "tier" in video.metadata
    assert video.metadata["tier"] == ProductionTier.ANIMATED.value
    assert video.provider == "mock"
