"""Shared pytest fixtures"""

import pytest
import asyncio
from typing import Generator

from tests.mocks.claude_client import MockClaudeClient
from tests.mocks.fixtures import (
    make_scene,
    make_scene_list,
    make_pilot_strategy,
    make_video_request
)


# ============================================================
# Event Loop
# ============================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================
# Mock Claude Client
# ============================================================

@pytest.fixture
def mock_claude_client():
    """Fresh mock Claude client for each test"""
    client = MockClaudeClient(debug=False)
    yield client
    client.reset()


@pytest.fixture
def mock_claude_client_debug():
    """Mock Claude client with debug output"""
    client = MockClaudeClient(debug=True)
    yield client
    client.reset()


# ============================================================
# Test Data Fixtures
# ============================================================

@pytest.fixture
def sample_scene():
    """Single sample scene"""
    return make_scene()


@pytest.fixture
def sample_scenes():
    """List of 3 sample scenes"""
    return make_scene_list(3)


@pytest.fixture
def sample_pilot():
    """Sample pilot strategy"""
    return make_pilot_strategy()


@pytest.fixture
def sample_request():
    """Sample video request"""
    return make_video_request()


# ============================================================
# Markers Configuration
# ============================================================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks integration tests"
    )
    config.addinivalue_line(
        "markers", "live_api: marks tests that hit real APIs (requires keys)"
    )
