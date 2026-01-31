---
layout: default
title: Strands SDK Integration Specification
---
# Strands SDK Integration Specification

## Overview

This document outlines how to integrate Strands SDK into Claude Studio Producer for parallel execution, agent orchestration, and workflow management. Since you're already using Strands on another project, this leverages that familiarity.

## Why Strands

1. **Familiar**: You already know it
2. **Battle-tested**: Proven patterns for agent orchestration
3. **Built-in**: Retry, timeout, concurrency, circuit breaker
4. **Composable**: Easy to build complex workflows
5. **Observable**: Built-in tracing and debugging

## Installation

```bash
pip install strands-agents
```

Add to requirements.txt:
```
strands-agents>=0.1.0
anthropic>=0.34.0
python-dotenv>=1.0.0
```

## Architecture Changes

### Before (Current)

```
core/
├── orchestrator.py      # Custom asyncio orchestration
├── budget.py
└── claude_client.py

agents/
├── producer.py          # Plain Python classes
├── critic.py
├── script_writer.py
└── video_generator.py
```

### After (Strands)

```
core/
├── budget.py            # Unchanged
├── claude_client.py     # Unchanged (or use Strands' Claude integration)
└── providers/
    └── base.py          # Provider interfaces (unchanged)

agents/
├── base.py              # Strands Agent base class
├── producer.py          # Strands Agent
├── critic.py            # Strands Agent
├── script_writer.py     # Strands Agent
├── video_generator.py   # Strands Agent
├── audio_generator.py   # Strands Agent
└── editor.py            # Strands Agent

workflows/
├── __init__.py
├── orchestrator.py      # Main Strands workflow
├── pilot_workflow.py    # Pilot execution workflow
└── production_workflow.py  # Full production workflow
```

## Agent Conversion

### Base Agent Class

```python
# agents/base.py
from strands import Agent, tool
from core.claude_client import ClaudeClient


class StudioAgent(Agent):
    """Base class for all Claude Studio agents"""
    
    def __init__(self, name: str, claude_client: ClaudeClient = None):
        super().__init__(
            name=name,
            model="claude-sonnet-4-20250514"  # Or configure per agent
        )
        self.claude = claude_client or ClaudeClient()
```

### Producer Agent (Converted)

```python
# agents/producer.py
from strands import Agent, tool
from typing import List
from dataclasses import dataclass

from .base import StudioAgent
from core.budget import ProductionTier, COST_MODELS
from core.claude_client import JSONExtractor


@dataclass
class PilotStrategy:
    pilot_id: str
    tier: ProductionTier
    allocated_budget: float
    test_scene_count: int
    full_scene_count: int
    rationale: str


class ProducerAgent(StudioAgent):
    """
    Analyzes requests and budgets, creates multi-pilot strategies.
    Strands-compatible agent.
    """
    
    def __init__(self, claude_client=None):
        super().__init__(name="producer", claude_client=claude_client)
    
    @tool
    async def analyze_request(self, user_request: str, total_budget: float) -> dict:
        """
        Analyze video request and budget constraints.
        Returns analysis of complexity, recommended tiers, and scene estimates.
        """
        prompt = f"""Analyze this video request:

REQUEST: {user_request}
BUDGET: ${total_budget}

Return JSON with:
- complexity: "simple", "medium", "complex"
- recommended_tiers: list of viable production tiers
- estimated_scenes: number of scenes needed
- estimated_duration: total seconds
"""
        response = await self.claude.query(prompt)
        return JSONExtractor.extract(response)
    
    @tool
    async def create_pilot_strategies(
        self, 
        analysis: dict, 
        total_budget: float
    ) -> List[PilotStrategy]:
        """
        Create 2-3 competitive pilot strategies based on analysis.
        """
        prompt = f"""Based on this analysis, create pilot strategies:

ANALYSIS: {analysis}
BUDGET: ${total_budget}

Available tiers:
- static_images: $0.04/sec (quality ceiling: 75)
- motion_graphics: $0.15/sec (quality ceiling: 85)
- animated: $0.25/sec (quality ceiling: 90)
- photorealistic: $0.50/sec (quality ceiling: 95)

Return JSON:
{{
  "pilots": [
    {{
      "pilot_id": "pilot_a",
      "tier": "motion_graphics",
      "allocated_budget": 50.0,
      "test_scene_count": 3,
      "rationale": "Cost-effective baseline"
    }}
  ],
  "total_scenes_estimated": 12
}}
"""
        response = await self.claude.query(prompt)
        data = JSONExtractor.extract(response)
        
        return [
            PilotStrategy(
                pilot_id=p["pilot_id"],
                tier=ProductionTier(p["tier"]),
                allocated_budget=p["allocated_budget"],
                test_scene_count=p["test_scene_count"],
                full_scene_count=data["total_scenes_estimated"],
                rationale=p["rationale"]
            )
            for p in data["pilots"]
        ]
    
    async def run(self, user_request: str, total_budget: float) -> List[PilotStrategy]:
        """Main entry point - analyze and create strategies"""
        analysis = await self.analyze_request(user_request, total_budget)
        return await self.create_pilot_strategies(analysis, total_budget)
```

### Video Generator Agent (Converted)

```python
# agents/video_generator.py
from strands import Agent, tool
from typing import List, Optional
from dataclasses import dataclass

from .base import StudioAgent
from core.providers.base import VideoProvider, GeneratedVideo


class VideoGeneratorAgent(StudioAgent):
    """
    Generates video content for scenes.
    Strands-compatible with provider injection.
    """
    
    def __init__(
        self, 
        claude_client=None,
        video_provider: VideoProvider = None
    ):
        super().__init__(name="video_generator", claude_client=claude_client)
        self.video_provider = video_provider
    
    @tool
    async def build_prompt(self, scene) -> str:
        """Build optimized prompt for video generation"""
        parts = [scene.description]
        
        if scene.visual_elements:
            parts.append(f"Visual elements: {', '.join(scene.visual_elements)}")
        
        if scene.prompt_hints:
            parts.append(f"Style: {', '.join(scene.prompt_hints)}")
        
        return ". ".join(parts)
    
    @tool
    async def generate_single(self, scene, prompt: str) -> GeneratedVideo:
        """Generate video for a single scene"""
        return await self.video_provider.generate(
            prompt=prompt,
            duration=scene.duration
        )
    
    async def run(
        self, 
        scenes: List, 
        budget_limit: float = float('inf')
    ) -> List[GeneratedVideo]:
        """Generate videos for multiple scenes within budget"""
        results = []
        total_cost = 0
        
        for scene in scenes:
            estimated_cost = scene.duration * self.video_provider.cost_per_second
            if total_cost + estimated_cost > budget_limit:
                break
            
            prompt = await self.build_prompt(scene)
            video = await self.generate_single(scene, prompt)
            results.append(video)
            total_cost += video.generation_cost
        
        return results
```

## Workflow Layer

### Main Orchestrator Workflow

```python
# workflows/orchestrator.py
from strands import Workflow, parallel, sequential, map_reduce
from strands.utils import retry, timeout, circuit_breaker
from typing import List, Optional
from dataclasses import dataclass

from agents.producer import ProducerAgent, PilotStrategy
from agents.critic import CriticAgent, PilotResults
from agents.script_writer import ScriptWriterAgent
from agents.video_generator import VideoGeneratorAgent
from agents.audio_generator import AudioGeneratorAgent
from core.budget import BudgetTracker


@dataclass
class ProductionResult:
    status: str
    best_pilot: Optional[PilotResults]
    all_pilots: List[PilotResults]
    budget_used: float
    budget_remaining: float
    total_scenes: int


class StudioOrchestrator(Workflow):
    """
    Main production orchestrator using Strands workflow patterns.
    
    Pipeline:
    1. Producer plans pilots (sequential)
    2. Pilots execute test scenes (parallel)
    3. Critic evaluates pilots (parallel)
    4. Approved pilots complete production (parallel, budget-limited)
    5. Editor creates final cuts (sequential)
    """
    
    def __init__(
        self,
        num_variations: int = 3,
        max_concurrent_pilots: int = 3,
        max_concurrent_scenes: int = 5,
        debug: bool = False
    ):
        super().__init__(name="studio_orchestrator")
        
        self.num_variations = num_variations
        self.max_concurrent_pilots = max_concurrent_pilots
        self.max_concurrent_scenes = max_concurrent_scenes
        self.debug = debug
        
        # Initialize agents
        self.producer = ProducerAgent()
        self.critic = CriticAgent()
        self.script_writer = ScriptWriterAgent()
        self.video_generator = VideoGeneratorAgent()
        self.audio_generator = AudioGeneratorAgent()
    
    async def run(
        self, 
        user_request: str, 
        total_budget: float
    ) -> ProductionResult:
        """Execute full production pipeline"""
        
        budget_tracker = BudgetTracker(total_budget)
        
        # Stage 1: Planning (sequential)
        print("📋 Stage 1: Producer planning pilots...")
        pilots = await self.producer.run(user_request, total_budget)
        
        # Stage 2: Parallel pilot test execution
        print(f"🎥 Stage 2: Running {len(pilots)} pilots in parallel...")
        test_results = await self._run_pilots_parallel(
            user_request=user_request,
            pilots=pilots,
            budget_tracker=budget_tracker
        )
        
        # Stage 3: Parallel evaluation
        print("🔍 Stage 3: Critic evaluating pilots...")
        evaluations = await self._evaluate_pilots_parallel(
            user_request=user_request,
            pilots=pilots,
            test_results=test_results,
            budget_tracker=budget_tracker
        )
        
        # Stage 4: Continue approved pilots
        approved = [(pilots[i], evaluations[i]) 
                    for i in range(len(pilots)) 
                    if evaluations[i].approved]
        
        if not approved:
            return ProductionResult(
                status="failed",
                best_pilot=None,
                all_pilots=evaluations,
                budget_used=budget_tracker.get_total_spent(),
                budget_remaining=budget_tracker.get_remaining_budget(),
                total_scenes=0
            )
        
        print(f"✅ Stage 4: Completing {len(approved)} approved pilots...")
        final_results = await self._complete_pilots_parallel(
            approved_pilots=approved,
            budget_tracker=budget_tracker
        )
        
        # Stage 5: Select best
        best = self.critic.compare_pilots(final_results)
        
        return ProductionResult(
            status="success",
            best_pilot=best,
            all_pilots=final_results,
            budget_used=budget_tracker.get_total_spent(),
            budget_remaining=budget_tracker.get_remaining_budget(),
            total_scenes=len(best.scenes_generated) if best else 0
        )
    
    async def _run_pilots_parallel(
        self,
        user_request: str,
        pilots: List[PilotStrategy],
        budget_tracker: BudgetTracker
    ) -> List[dict]:
        """Run pilot test phases in parallel using Strands"""
        
        async def run_single_pilot(pilot: PilotStrategy) -> dict:
            """Execute a single pilot's test phase"""
            
            # Generate script for test scenes
            scenes = await self.script_writer.run(
                video_concept=user_request,
                target_duration=60,
                num_scenes=pilot.test_scene_count
            )
            
            # Generate videos for test scenes
            videos = await self.video_generator.run(
                scenes=scenes,
                budget_limit=pilot.allocated_budget * 0.3  # 30% for test
            )
            
            # Calculate cost
            total_cost = sum(v.generation_cost for v in videos)
            budget_tracker.record_spend(pilot.pilot_id, total_cost)
            
            return {
                "pilot_id": pilot.pilot_id,
                "scenes": scenes,
                "videos": videos,
                "budget_spent": total_cost
            }
        
        # Strands parallel execution with concurrency limit
        results = await parallel(
            *[run_single_pilot(p) for p in pilots],
            max_concurrency=self.max_concurrent_pilots,
            return_exceptions=True
        )
        
        # Filter out failures
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"⚠️ Pilot {pilots[i].pilot_id} failed: {result}")
            else:
                valid_results.append(result)
        
        return valid_results
    
    async def _evaluate_pilots_parallel(
        self,
        user_request: str,
        pilots: List[PilotStrategy],
        test_results: List[dict],
        budget_tracker: BudgetTracker
    ) -> List[PilotResults]:
        """Evaluate all pilots in parallel"""
        
        # Match results to pilots
        result_map = {r["pilot_id"]: r for r in test_results}
        
        async def evaluate_single(pilot: PilotStrategy) -> PilotResults:
            result = result_map.get(pilot.pilot_id)
            if not result:
                return PilotResults(
                    pilot_id=pilot.pilot_id,
                    tier=pilot.tier.value,
                    scenes_generated=[],
                    total_cost=0,
                    avg_qa_score=0,
                    approved=False,
                    critic_reasoning="No test results available"
                )
            
            return await self.critic.run(
                original_request=user_request,
                pilot=pilot,
                scene_results=result["videos"],
                budget_spent=result["budget_spent"],
                budget_allocated=pilot.allocated_budget
            )
        
        return await parallel(
            *[evaluate_single(p) for p in pilots],
            max_concurrency=self.max_concurrent_pilots
        )
    
    async def _complete_pilots_parallel(
        self,
        approved_pilots: List[tuple],
        budget_tracker: BudgetTracker
    ) -> List[PilotResults]:
        """Complete production for approved pilots"""
        
        async def complete_single(pilot: PilotStrategy, evaluation: PilotResults):
            remaining_budget = min(
                evaluation.budget_remaining,
                budget_tracker.get_remaining_budget() / len(approved_pilots)
            )
            
            # Generate remaining scenes
            remaining_count = pilot.full_scene_count - pilot.test_scene_count
            
            additional_scenes = await self.script_writer.run(
                video_concept="continuation",  # Would use actual context
                num_scenes=remaining_count
            )
            
            additional_videos = await self.video_generator.run(
                scenes=additional_scenes,
                budget_limit=remaining_budget
            )
            
            # Update evaluation
            evaluation.scenes_generated.extend(additional_videos)
            additional_cost = sum(v.generation_cost for v in additional_videos)
            evaluation.total_cost += additional_cost
            budget_tracker.record_spend(pilot.pilot_id, additional_cost)
            
            return evaluation
        
        return await parallel(
            *[complete_single(p, e) for p, e in approved_pilots],
            max_concurrency=2  # Limit to avoid budget overrun
        )
```

### Pilot Workflow (Reusable)

```python
# workflows/pilot_workflow.py
from strands import Workflow, parallel, sequential, map_reduce
from strands.utils import retry, timeout


class PilotWorkflow(Workflow):
    """
    Reusable workflow for running a single pilot.
    Can be composed into larger workflows.
    """
    
    def __init__(
        self,
        script_writer,
        video_generator,
        audio_generator,
        qa_verifier
    ):
        super().__init__(name="pilot_workflow")
        self.script_writer = script_writer
        self.video_generator = video_generator
        self.audio_generator = audio_generator
        self.qa_verifier = qa_verifier
    
    async def run(
        self,
        concept: str,
        pilot_strategy,
        budget_limit: float
    ):
        """Execute pilot workflow"""
        
        # Step 1: Generate script
        scenes = await self.script_writer.run(
            video_concept=concept,
            target_duration=60,
            num_scenes=pilot_strategy.test_scene_count
        )
        
        # Step 2: Generate video and audio in parallel for each scene
        scene_results = await map_reduce(
            func=self._generate_scene_assets,
            items=scenes,
            max_concurrency=5,
            on_error="continue"
        )
        
        # Step 3: QA verification in parallel
        qa_results = await map_reduce(
            func=self.qa_verifier.run,
            items=scene_results,
            max_concurrency=10
        )
        
        return {
            "scenes": scenes,
            "assets": scene_results,
            "qa": qa_results,
            "total_cost": sum(r.get("cost", 0) for r in scene_results)
        }
    
    @retry(max_attempts=3, backoff=2.0)
    @timeout(seconds=60)
    async def _generate_scene_assets(self, scene):
        """Generate video and audio for a single scene"""
        
        # Parallel video + audio generation
        video_task = self.video_generator.generate_single(scene)
        audio_task = self.audio_generator.generate_scene_audio(scene)
        
        video, audio = await parallel(video_task, audio_task)
        
        return {
            "scene_id": scene.scene_id,
            "video": video,
            "audio": audio,
            "cost": video.generation_cost + audio.generation_cost
        }
```

## Strands Utilities

### Retry and Timeout Decorators

```python
# Already built into Strands, use like:

from strands.utils import retry, timeout, circuit_breaker

class VideoGeneratorAgent(StudioAgent):
    
    @retry(max_attempts=3, backoff=2.0, exceptions=[APIError, TimeoutError])
    @timeout(seconds=120)
    @circuit_breaker(failure_threshold=5, recovery_time=60)
    async def generate_single(self, scene, prompt: str) -> GeneratedVideo:
        """Generate video with retry, timeout, and circuit breaker"""
        return await self.video_provider.generate(
            prompt=prompt,
            duration=scene.duration
        )
```

### Concurrency Control

```python
from strands import parallel, map_reduce

# Run with concurrency limit
results = await parallel(
    *tasks,
    max_concurrency=5,       # Max 5 at a time
    return_exceptions=True,  # Don't fail on single error
    timeout=120.0            # Per-task timeout
)

# Map with concurrency
videos = await map_reduce(
    func=generate_video,
    items=scenes,
    max_concurrency=10,
    on_error="continue"      # Skip failures, continue others
)
```

## Migration Path

### Phase 1: Add Strands Dependency
```bash
pip install strands-agents
# Update requirements.txt
```

### Phase 2: Create Base Agent Class
```python
# agents/base.py - StudioAgent extending Strands Agent
```

### Phase 3: Convert Agents One by One
Start with simplest (Producer), end with most complex (VideoGenerator)

1. `producer.py` - Add @tool decorators, implement run()
2. `critic.py` - Same pattern
3. `script_writer.py` - Same pattern
4. `video_generator.py` - Add retry/timeout decorators
5. `audio_generator.py` - Add retry/timeout decorators
6. `qa_verifier.py` - Same pattern
7. `editor.py` - Same pattern

### Phase 4: Create Workflow Layer
```python
# workflows/orchestrator.py - New Strands workflow
```

### Phase 5: Update Examples
```python
# examples/ - Use new workflow API
```

### Phase 6: Deprecate Old Orchestrator
```python
# Remove core/orchestrator.py once workflows/ is stable
```

## Testing with Strands

```python
# tests/test_workflows.py
import pytest
from strands.testing import MockAgent, WorkflowTestHarness

@pytest.fixture
def mock_producer():
    return MockAgent(
        name="producer",
        responses={
            "analyze_request": {"complexity": "medium"},
            "create_pilot_strategies": [mock_pilot_strategy()]
        }
    )

@pytest.mark.asyncio
async def test_orchestrator_workflow(mock_producer, mock_video_generator):
    harness = WorkflowTestHarness(StudioOrchestrator)
    harness.inject(producer=mock_producer)
    harness.inject(video_generator=mock_video_generator)
    
    result = await harness.run(
        user_request="Test video",
        total_budget=100.0
    )
    
    assert result.status == "success"
    assert mock_producer.was_called("analyze_request")
```

## Observability

Strands provides built-in tracing:

```python
from strands import enable_tracing

# Enable tracing
enable_tracing(
    backend="console",  # or "jaeger", "datadog", etc.
    service_name="claude-studio"
)

# Traces automatically capture:
# - Agent invocations
# - Tool calls
# - Parallel execution timing
# - Errors and retries
```

## Summary

### What Changes
- Agents get `@tool` decorators and `run()` methods
- New `workflows/` directory for orchestration
- Parallel execution uses Strands patterns
- Built-in retry, timeout, circuit breaker

### What Stays the Same
- `core/budget.py` - Unchanged
- `core/providers/` - Unchanged
- `tests/mocks/` - Unchanged (Strands has its own mock utilities)
- Provider injection pattern - Unchanged

### Benefits
- Cleaner parallel execution
- Built-in error handling
- Observable/traceable
- Familiar patterns (for you)
- Composable workflows
