# Testing and Providers Architecture Specification

## Overview

This document defines a **pragmatic, incremental approach** to establishing clean testing patterns and provider interfaces. We maintain the working v0.5.0 integration while establishing the right patterns for future work.

## Design Principles

1. **Don't Break What Works**: Keep the v0.5.0 agent integration functional
2. **Establish Patterns for New Work**: Use proper abstractions for new providers
3. **Progressive Migration**: Move mocks to tests/ as we add real providers
4. **Clean Production Code**: No test logic in core/ or agents/ (eventually)
5. **Pytest-First**: All new tests use proper pytest structure

## Current State (v0.5.0)

### What We Have (Keep As-Is For Now)

- **Working agent pipeline**: ScriptWriter → VideoGenerator → QA → Critic
- **Mock mode in agents**: `VideoGeneratorAgent(mock_mode=True)`, `QAVerifierAgent(mock_mode=True)`
- **Mock responses in ClaudeClient**: `_generate_mock_response()` for testing without API keys
- **Examples in examples/**: Test scripts that demonstrate functionality

### What Needs Cleaning

- Mock logic embedded in production code (`claude_client.py`)
- No proper `tests/` directory with pytest structure
- No test fixtures or factories
- Provider interfaces not formalized

## Incremental Migration Plan

### Phase 1: Establish Testing Infrastructure (Now)

**Goal**: Create proper test structure without breaking existing code

1. Create `tests/` directory structure:
   ```
   tests/
   ├── __init__.py
   ├── conftest.py           # Pytest fixtures
   ├── mocks/
   │   ├── __init__.py
   │   ├── claude_client.py  # MockClaudeClient
   │   └── fixtures.py       # Test data factories
   ├── unit/
   │   ├── __init__.py
   │   └── test_budget.py    # Start with simple tests
   └── integration/
       ├── __init__.py
       └── test_pipeline.py  # End-to-end tests
   ```

2. Create `MockClaudeClient` in `tests/mocks/`:
   - Move `_generate_mock_response()` logic here
   - Keep the real `ClaudeClient` clean
   - Examples can import from `tests.mocks` temporarily

3. Add `pytest.ini` for proper test configuration

4. Create test data factories in `tests/mocks/fixtures.py`:
   - `make_scene()`, `make_pilot_strategy()`, etc.
   - Consistent test data generation

### Phase 2: Provider Interfaces (When Adding First Real Provider)

**Goal**: Establish provider pattern when implementing Runway/Pika

When we implement the **first real video provider** (e.g., Runway):

1. Create `core/providers/base.py`:
   ```python
   from abc import ABC, abstractmethod

   class VideoProvider(ABC):
       @abstractmethod
       async def generate(self, prompt: str, duration: float) -> GeneratedVideo:
           pass

       @property
       @abstractmethod
       def cost_per_second(self) -> float:
           pass
   ```

2. Create real provider: `core/providers/video/runway.py`:
   ```python
   class RunwayProvider(VideoProvider):
       async def generate(self, prompt: str, duration: float) -> GeneratedVideo:
           # Real Runway API implementation
           pass
   ```

3. Create mock provider in tests: `tests/mocks/providers.py`:
   ```python
   class MockVideoProvider(VideoProvider):
       async def generate(self, prompt: str, duration: float) -> GeneratedVideo:
           # Mock implementation for testing
           pass
   ```

4. Refactor `VideoGeneratorAgent`:
   ```python
   # Old (v0.5.0)
   class VideoGeneratorAgent:
       def __init__(self, mock_mode=True):
           self.mock_mode = mock_mode

   # New (with provider injection)
   class VideoGeneratorAgent:
       def __init__(self, video_provider: VideoProvider):
           self.video_provider = video_provider
   ```

5. Update orchestrator to use provider registry or direct injection

### Phase 3: Cleanup (After Provider Migration)

**Goal**: Remove mock logic from production code

1. Remove `_generate_mock_response()` from `claude_client.py`
2. Remove `mock_mode` parameters from agents
3. Move all test examples to `tests/`
4. Keep `examples/` for real demonstrations only

## Directory Structure (Target State)

```
claude-studio-producer/
├── core/
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract interfaces (Phase 2)
│   │   └── video/
│   │       ├── __init__.py
│   │       ├── runway.py         # Real provider (Phase 2)
│   │       └── pika.py           # Real provider (Phase 2)
│   ├── orchestrator.py           # Clean, no mock logic
│   ├── budget.py
│   └── claude_client.py          # Clean, no mock responses (Phase 3)
│
├── agents/
│   ├── video_generator.py        # Accepts VideoProvider (Phase 2)
│   ├── qa_verifier.py            # Clean, no mock_mode (Phase 3)
│   └── ...
│
├── tests/                        # NEW (Phase 1)
│   ├── conftest.py               # Pytest fixtures
│   ├── mocks/
│   │   ├── __init__.py
│   │   ├── claude_client.py      # MockClaudeClient
│   │   ├── providers.py          # Mock providers (Phase 2)
│   │   └── fixtures.py           # Test data factories
│   ├── unit/
│   │   ├── test_budget.py
│   │   ├── test_producer.py
│   │   └── test_script_writer.py
│   └── integration/
│       └── test_full_pipeline.py
│
├── examples/
│   ├── full_production.py        # Real demo (uses mocks for now)
│   └── live/                     # NEW (Phase 2)
│       └── runway_demo.py        # Real API demo
```

## Phase 1 Implementation Details

### tests/conftest.py

```python
"""Shared pytest fixtures"""

import pytest
import asyncio

# Event loop
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Test data fixtures (use factories from fixtures.py)
@pytest.fixture
def sample_scene():
    from tests.mocks.fixtures import make_scene
    return make_scene()

@pytest.fixture
def sample_pilot():
    from tests.mocks.fixtures import make_pilot_strategy
    return make_pilot_strategy()

# Mock Claude client
@pytest.fixture
def mock_claude_client():
    from tests.mocks.claude_client import MockClaudeClient
    return MockClaudeClient()
```

### tests/mocks/claude_client.py

```python
"""Mock Claude client for testing"""

import json
import random
from typing import Optional

class MockClaudeClient:
    """
    Mock ClaudeClient that returns realistic responses without hitting API
    This replaces the _generate_mock_response logic in production code
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.calls = []  # Track calls for test assertions

    async def query(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate mock response based on prompt patterns"""

        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})

        # Producer: planning pilots
        if "pilot strategies" in prompt.lower() and "total_scenes_estimated" in prompt:
            return json.dumps({
                "total_scenes_estimated": 10,
                "pilots": [
                    {
                        "pilot_id": "pilot_budget",
                        "tier": "motion_graphics",
                        "allocated_budget": 60.0,
                        "test_scene_count": 2,
                        "rationale": "Cost-effective approach"
                    },
                    {
                        "pilot_id": "pilot_quality",
                        "tier": "animated",
                        "allocated_budget": 90.0,
                        "test_scene_count": 2,
                        "rationale": "Higher quality approach"
                    }
                ]
            })

        # ScriptWriter: creating scenes
        elif "ESTIMATED SCENES" in prompt or "scene_id" in prompt:
            num_scenes = 2
            scenes = []
            for i in range(num_scenes):
                scenes.append({
                    "scene_id": f"scene_{i+1}",
                    "title": f"Scene {i+1}",
                    "description": "Compelling visual sequence",
                    "duration": 5.0,
                    "visual_elements": ["element1", "element2"],
                    "audio_notes": "Background music",
                    "transition_in": "fade_in" if i == 0 else "cut",
                    "transition_out": "cut" if i < num_scenes-1 else "fade_out",
                    "prompt_hints": ["professional", "engaging"]
                })
            return json.dumps({"scenes": scenes})

        # Critic: evaluating pilots
        elif "gap analysis" in prompt.lower():
            score = random.randint(75, 95)
            return json.dumps({
                "overall_score": score,
                "gap_analysis": {
                    "matched_elements": ["visual style", "pacing"],
                    "missing_elements": [],
                    "quality_issues": ["minor adjustments needed"]
                },
                "decision": "continue",
                "budget_multiplier": 0.75 if score < 85 else 1.0,
                "reasoning": f"Score: {score}/100. Proceeding.",
                "adjustments_needed": ["Fine-tune color grading"]
            })

        # Default
        return json.dumps({"status": "mock_response"})

    def reset(self):
        """Reset call tracking (for test cleanup)"""
        self.calls.clear()
```

### tests/mocks/fixtures.py

```python
"""Test data factories for consistent test setup"""

from dataclasses import dataclass
from typing import List
from agents.script_writer import Scene
from agents.producer import PilotStrategy
from core.budget import ProductionTier


def make_scene(
    scene_id: str = "scene_1",
    title: str = "Test Scene",
    description: str = "A test scene",
    duration: float = 5.0,
    **kwargs
) -> Scene:
    """Factory for Scene objects"""
    defaults = {
        "scene_id": scene_id,
        "title": title,
        "description": description,
        "duration": duration,
        "visual_elements": ["element1", "element2"],
        "audio_notes": "ambient",
        "transition_in": "cut",
        "transition_out": "cut",
        "prompt_hints": ["professional"]
    }
    defaults.update(kwargs)
    return Scene(**defaults)


def make_scene_list(count: int = 3, **kwargs) -> List[Scene]:
    """Factory for list of scenes"""
    return [
        make_scene(
            scene_id=f"scene_{i+1}",
            title=f"Scene {i+1}",
            duration=5.0,
            **kwargs
        )
        for i in range(count)
    ]


def make_pilot_strategy(
    pilot_id: str = "pilot_test",
    tier: ProductionTier = ProductionTier.ANIMATED,
    allocated_budget: float = 50.0,
    **kwargs
) -> PilotStrategy:
    """Factory for PilotStrategy objects"""
    defaults = {
        "pilot_id": pilot_id,
        "tier": tier,
        "allocated_budget": allocated_budget,
        "test_scene_count": 2,
        "full_scene_count": 10,
        "rationale": "Test pilot"
    }
    defaults.update(kwargs)
    return PilotStrategy(**defaults)
```

### pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short

markers =
    slow: marks tests as slow
    integration: marks integration tests
    live_api: marks tests requiring real API keys
```

### tests/unit/test_budget.py (Example)

```python
"""Unit tests for budget tracking"""

import pytest
from core.budget import BudgetTracker, ProductionTier


def test_budget_initialization():
    """Test budget tracker initialization"""
    tracker = BudgetTracker(total_budget=100.0)

    assert tracker.total_budget == 100.0
    assert tracker.get_remaining_budget() == 100.0
    assert tracker.get_total_spent() == 0.0


def test_record_spend():
    """Test recording spend reduces budget"""
    tracker = BudgetTracker(total_budget=100.0)

    tracker.record_spend("pilot_a", 30.0)

    assert tracker.get_remaining_budget() == 70.0
    assert tracker.get_total_spent() == 30.0


def test_multiple_pilots_tracking():
    """Test tracking multiple pilot spends"""
    tracker = BudgetTracker(total_budget=100.0)

    tracker.record_spend("pilot_a", 30.0)
    tracker.record_spend("pilot_b", 25.0)
    tracker.record_spend("pilot_a", 10.0)  # Additional spend

    assert tracker.get_remaining_budget() == 35.0
    assert tracker.get_total_spent() == 65.0
```

## Phase 2: Provider Pattern (Future)

When implementing the first real provider, we'll:

1. Define abstract `VideoProvider` interface in `core/providers/base.py`
2. Implement real provider (e.g., `RunwayProvider`)
3. Create corresponding mock in `tests/mocks/providers.py`
4. Refactor `VideoGeneratorAgent` to accept provider via dependency injection
5. Update orchestrator to instantiate and pass providers

This keeps production code clean while maintaining testability.

## Phase 3: Final Cleanup (Future)

After all providers are migrated:

1. Remove `_generate_mock_response()` from `core/claude_client.py`
2. All tests import from `tests.mocks`
3. Examples use real providers or mock providers from tests
4. Production code has zero test logic

## Summary

**Pragmatic Approach**:
- ✅ Keep v0.5.0 working as-is
- ✅ Build proper test structure in parallel (Phase 1)
- ✅ Adopt provider pattern when adding real APIs (Phase 2)
- ✅ Clean up mock logic after migration (Phase 3)

**Benefits**:
- No breaking changes to working code
- Establishes right patterns for future work
- Incremental, low-risk migration
- Clean separation of concerns over time
