"""Tests for Luma video provider"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional

from core.providers.video.luma import LumaProvider
from core.providers.base import VideoProviderConfig, ProviderType, GenerationResult


# ============================================================
# Mock Luma API Objects
# ============================================================

@dataclass
class MockAssets:
    """Mock Luma assets object"""
    video: str = "https://storage.luma.ai/video123.mp4"
    image: Optional[str] = None


@dataclass
class MockRequest:
    """Mock Luma request object"""
    prompt: str = "A beautiful sunset over the ocean"


@dataclass
class MockGeneration:
    """Mock Luma generation object"""
    id: str = "gen-123"
    state: str = "completed"
    created_at: str = "2024-01-15T10:30:00Z"
    assets: Optional[MockAssets] = None
    request: Optional[MockRequest] = None
    failure_reason: Optional[str] = None

    def __post_init__(self):
        if self.assets is None and self.state == "completed":
            self.assets = MockAssets()
        if self.request is None:
            self.request = MockRequest()


class MockGenerationListResponse:
    """Mock Luma GenerationListResponse"""
    def __init__(self, generations: list):
        self.generations = generations
        self.count = len(generations)
        self.has_more = False


class MockGenerations:
    """Mock Luma generations API"""
    def __init__(self):
        self._generations = []
        self.camera_motion = MockCameraMotion()

    def create(self, **kwargs):
        gen = MockGeneration(id="gen-new-123", state="pending")
        self._generations.append(gen)
        return gen

    def get(self, generation_id: str):
        for g in self._generations:
            if g.id == generation_id:
                return g
        return MockGeneration(id=generation_id)

    def list(self, limit: int = 100):
        return MockGenerationListResponse(self._generations[:limit])


class MockCameraMotion:
    """Mock camera motion API"""
    def list(self):
        return [
            Mock(key="orbit"),
            Mock(key="pan_left"),
            Mock(key="zoom_in"),
        ]


class MockLumaClient:
    """Mock Luma AI client"""
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.generations = MockGenerations()


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def luma_config():
    """Create test Luma config"""
    return VideoProviderConfig(
        provider_type=ProviderType.LUMA,
        api_key="test-api-key",
        timeout=60
    )


@pytest.fixture
def mock_luma_client():
    """Create mock Luma client"""
    return MockLumaClient(auth_token="test-key")


@pytest.fixture
def luma_provider(luma_config, mock_luma_client):
    """Create LumaProvider with mocked client"""
    with patch('core.providers.video.luma.LumaAI', return_value=mock_luma_client):
        provider = LumaProvider(config=luma_config)
        provider.client = mock_luma_client
        return provider


# ============================================================
# Tests: list_generations
# ============================================================

class TestListGenerations:
    """Tests for list_generations method"""

    @pytest.mark.asyncio
    async def test_list_generations_empty(self, luma_provider):
        """Test listing with no generations"""
        result = await luma_provider.list_generations(limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_generations_with_completed(self, luma_provider):
        """Test listing completed generations"""
        # Add some mock generations
        luma_provider.client.generations._generations = [
            MockGeneration(id="gen-1", state="completed"),
            MockGeneration(id="gen-2", state="completed"),
        ]

        result = await luma_provider.list_generations(limit=10)

        assert len(result) == 2
        assert result[0]["id"] == "gen-1"
        assert result[0]["state"] == "completed"
        assert result[0]["video_url"] is not None
        assert result[1]["id"] == "gen-2"

    @pytest.mark.asyncio
    async def test_list_generations_mixed_states(self, luma_provider):
        """Test listing generations with different states"""
        luma_provider.client.generations._generations = [
            MockGeneration(id="gen-1", state="completed"),
            MockGeneration(id="gen-2", state="failed", failure_reason="Content policy", assets=None),
            MockGeneration(id="gen-3", state="dreaming", assets=None),
        ]

        result = await luma_provider.list_generations(limit=10)

        assert len(result) == 3

        # Completed should have video_url
        assert result[0]["state"] == "completed"
        assert result[0]["video_url"] is not None

        # Failed should have failure_reason
        assert result[1]["state"] == "failed"
        assert result[1]["failure_reason"] == "Content policy"
        assert result[1]["video_url"] is None

        # Dreaming should have no video_url
        assert result[2]["state"] == "dreaming"
        assert result[2]["video_url"] is None

    @pytest.mark.asyncio
    async def test_list_generations_respects_limit(self, luma_provider):
        """Test that limit is respected"""
        luma_provider.client.generations._generations = [
            MockGeneration(id=f"gen-{i}", state="completed")
            for i in range(20)
        ]

        result = await luma_provider.list_generations(limit=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_list_generations_extracts_prompt(self, luma_provider):
        """Test that prompt is correctly extracted"""
        luma_provider.client.generations._generations = [
            MockGeneration(
                id="gen-1",
                state="completed",
                request=MockRequest(prompt="A cat playing piano in a jazz club")
            ),
        ]

        result = await luma_provider.list_generations(limit=10)

        assert result[0]["prompt"] == "A cat playing piano in a jazz club"

    @pytest.mark.asyncio
    async def test_list_generations_truncates_long_prompt(self, luma_provider):
        """Test that long prompts are truncated"""
        long_prompt = "A" * 100

        luma_provider.client.generations._generations = [
            MockGeneration(
                id="gen-1",
                state="completed",
                request=MockRequest(prompt=long_prompt)
            ),
        ]

        result = await luma_provider.list_generations(limit=10)

        assert len(result[0]["prompt"]) == 50  # Should be truncated to 50 chars


# ============================================================
# Tests: download_generation
# ============================================================

class TestDownloadGeneration:
    """Tests for download_generation method"""

    @pytest.mark.asyncio
    async def test_download_completed_generation(self, luma_provider):
        """Test downloading a completed generation"""
        gen = MockGeneration(id="gen-123", state="completed")
        luma_provider.client.generations._generations = [gen]

        # Mock the download_video method
        luma_provider.download_video = AsyncMock(return_value=True)

        result = await luma_provider.download_generation("gen-123", "/tmp/video.mp4")

        assert result == "/tmp/video.mp4"
        luma_provider.download_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_not_completed_raises(self, luma_provider):
        """Test that downloading non-completed generation raises"""
        gen = MockGeneration(id="gen-123", state="dreaming", assets=None)
        luma_provider.client.generations._generations = [gen]

        with pytest.raises(Exception) as exc_info:
            await luma_provider.download_generation("gen-123", "/tmp/video.mp4")

        assert "not completed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_failed_raises(self, luma_provider):
        """Test that downloading failed generation raises"""
        gen = MockGeneration(id="gen-123", state="failed", assets=None)
        luma_provider.client.generations._generations = [gen]

        with pytest.raises(Exception) as exc_info:
            await luma_provider.download_generation("gen-123", "/tmp/video.mp4")

        assert "not completed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_download_failure_raises(self, luma_provider):
        """Test that download failure raises exception"""
        gen = MockGeneration(id="gen-123", state="completed")
        luma_provider.client.generations._generations = [gen]

        # Mock download to fail
        luma_provider.download_video = AsyncMock(return_value=False)

        with pytest.raises(Exception) as exc_info:
            await luma_provider.download_generation("gen-123", "/tmp/video.mp4")

        assert "Failed to download" in str(exc_info.value)


# ============================================================
# Tests: check_status
# ============================================================

class TestCheckStatus:
    """Tests for check_status method"""

    @pytest.mark.asyncio
    async def test_check_status_completed(self, luma_provider):
        """Test checking status of completed generation"""
        gen = MockGeneration(id="gen-123", state="completed")
        luma_provider.client.generations._generations = [gen]

        result = await luma_provider.check_status("gen-123")

        assert result["id"] == "gen-123"
        assert result["status"] == "completed"
        assert result["video_url"] is not None

    @pytest.mark.asyncio
    async def test_check_status_failed(self, luma_provider):
        """Test checking status of failed generation"""
        gen = MockGeneration(
            id="gen-123",
            state="failed",
            failure_reason="Content policy violation",
            assets=None
        )
        luma_provider.client.generations._generations = [gen]

        result = await luma_provider.check_status("gen-123")

        assert result["id"] == "gen-123"
        assert result["status"] == "failed"
        assert result["failure_reason"] == "Content policy violation"

    @pytest.mark.asyncio
    async def test_check_status_pending(self, luma_provider):
        """Test checking status of pending generation"""
        gen = MockGeneration(id="gen-123", state="dreaming", assets=None)
        luma_provider.client.generations._generations = [gen]

        result = await luma_provider.check_status("gen-123")

        assert result["id"] == "gen-123"
        assert result["status"] == "dreaming"
        assert result["video_url"] is None


# ============================================================
# Tests: list_camera_motions
# ============================================================

class TestListCameraMotions:
    """Tests for list_camera_motions method"""

    @pytest.mark.asyncio
    async def test_list_camera_motions(self, luma_provider):
        """Test listing camera motions"""
        result = await luma_provider.list_camera_motions()

        assert "orbit" in result
        assert "pan_left" in result
        assert "zoom_in" in result


# ============================================================
# Tests: estimate_cost
# ============================================================

class TestEstimateCost:
    """Tests for estimate_cost method"""

    def test_estimate_cost_5s_720p(self, luma_provider):
        """Test cost estimation for 5s 720p video"""
        cost = luma_provider.estimate_cost(5.0, resolution="720p")
        assert cost == 0.40

    def test_estimate_cost_9s_720p(self, luma_provider):
        """Test cost estimation for 9s 720p video"""
        cost = luma_provider.estimate_cost(9.0, resolution="720p")
        assert cost == 0.72

    def test_estimate_cost_5s_1080p(self, luma_provider):
        """Test cost estimation for 5s 1080p video"""
        cost = luma_provider.estimate_cost(5.0, resolution="1080p")
        assert cost == 0.80

    def test_estimate_cost_default_resolution(self, luma_provider):
        """Test cost estimation with default resolution"""
        cost = luma_provider.estimate_cost(5.0)
        assert cost == 0.40  # Default is 720p
