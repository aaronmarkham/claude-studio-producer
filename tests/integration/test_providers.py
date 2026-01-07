"""Integration tests for video providers"""

import pytest
from core.providers import MockVideoProvider, VideoProviderConfig, ProviderType
from core.budget import ProductionTier


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_generate_video():
    """Test MockVideoProvider can generate videos"""
    provider = MockVideoProvider()

    result = await provider.generate_video(
        prompt="A developer coding at a computer",
        duration=5.0,
        aspect_ratio="16:9",
        tier=ProductionTier.ANIMATED
    )

    assert result.success is True
    assert result.video_url is not None
    assert "mock" in result.video_url
    assert result.duration == 5.0
    assert result.cost > 0
    assert result.provider_metadata["provider"] == "mock"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_cost_estimation():
    """Test MockVideoProvider cost estimation"""
    provider = MockVideoProvider()

    # Test different tiers have different costs
    static_cost = provider.estimate_cost(10.0, tier=ProductionTier.STATIC_IMAGES)
    animated_cost = provider.estimate_cost(10.0, tier=ProductionTier.ANIMATED)
    photo_cost = provider.estimate_cost(10.0, tier=ProductionTier.PHOTOREALISTIC)

    # Higher tiers should cost more
    assert static_cost < animated_cost < photo_cost


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_check_status():
    """Test MockVideoProvider job status checking"""
    provider = MockVideoProvider()

    # Generate a video first
    result = await provider.generate_video(
        prompt="Test prompt",
        duration=5.0,
        tier=ProductionTier.ANIMATED
    )

    job_id = result.provider_metadata["job_id"]

    # Check status
    status = await provider.check_status(job_id)
    assert status["status"] == "completed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_download_video():
    """Test MockVideoProvider video download"""
    provider = MockVideoProvider()

    # Mock download should succeed
    success = await provider.download_video(
        video_url="https://mock.example.com/video.mp4",
        output_path="/tmp/test_video.mp4"
    )

    assert success is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_validate_credentials():
    """Test MockVideoProvider credential validation"""
    provider = MockVideoProvider()

    # Mock provider always has valid credentials
    is_valid = await provider.validate_credentials()
    assert is_valid is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_reset():
    """Test MockVideoProvider state reset"""
    provider = MockVideoProvider()

    # Generate a couple videos
    await provider.generate_video("test 1", 5.0, tier=ProductionTier.ANIMATED)
    await provider.generate_video("test 2", 5.0, tier=ProductionTier.ANIMATED)

    assert provider.generation_count == 2
    assert len(provider.jobs) == 2

    # Reset
    provider.reset()

    assert provider.generation_count == 0
    assert len(provider.jobs) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_provider_multiple_generations():
    """Test generating multiple videos in sequence"""
    provider = MockVideoProvider()

    videos = []
    for i in range(3):
        result = await provider.generate_video(
            prompt=f"Video {i}",
            duration=5.0,
            tier=ProductionTier.ANIMATED
        )
        videos.append(result)

    # All should succeed
    assert all(v.success for v in videos)

    # Should have unique job IDs
    job_ids = [v.provider_metadata["job_id"] for v in videos]
    assert len(set(job_ids)) == 3

    # Generation count should track correctly
    assert provider.generation_count == 3
