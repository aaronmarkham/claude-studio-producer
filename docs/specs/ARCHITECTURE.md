# System Architecture

## Overview

Claude Studio Producer is a multi-agent orchestration system for budget-aware video production. It uses competitive pilot evaluation to optimize quality within budget constraints.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                               │
│              (Video concept + Budget + Preferences)              │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STUDIO ORCHESTRATOR                         │
│                   (Main pipeline coordinator)                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    PRODUCER     │    │  SCRIPT WRITER  │    │     CRITIC      │
│     AGENT       │    │     AGENT       │    │     AGENT       │
│                 │    │                 │    │                 │
│ • Budget plan   │    │ • Scene breakdown│   │ • Gap analysis  │
│ • Pilot strategies│  │ • Visual direction│  │ • Quality scoring│
│ • Tier selection │   │ • Prompt hints   │    │ • Budget decisions│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     VIDEO       │    │   QA VERIFIER   │    │     EDITOR      │
│   GENERATOR     │    │     AGENT       │    │     AGENT       │
│                 │    │                 │    │                 │
│ • API calls     │    │ • Vision analysis│   │ • EDL creation  │
│ • Multi-provider│    │ • Quality scoring│   │ • Candidate cuts│
│ • Cost tracking │    │ • Issue detection│   │ • Export formats│
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FINAL OUTPUT                              │
│              (EDL candidates for human selection)                │
└─────────────────────────────────────────────────────────────────┘
```

## Pipeline Flow

### Stage 1: Planning
```
User Request → Producer Agent → Pilot Strategies (2-3 tiers)
```

### Stage 2: Scripting
```
Pilot Strategy → Script Writer → Scene Breakdown (10-15 scenes)
```

### Stage 3: Parallel Pilot Execution
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PILOT A   │     │   PILOT B   │     │   PILOT C   │
│ (static)    │     │ (animated)  │     │ (photo)     │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
   Generate            Generate            Generate
   Test Scenes         Test Scenes         Test Scenes
       │                   │                   │
       ▼                   ▼                   ▼
      QA                  QA                  QA
   Scoring             Scoring             Scoring
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                    Critic Evaluation
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ✅ Continue   ✅ Continue   ❌ Cancel
         + Budget      + Budget      (reallocate)
```

### Stage 4: Production Completion
```
Approved Pilots → Full Scene Generation → Final QA
```

### Stage 5: Editorial
```
All Videos + QA Scores → Editor Agent → EDL Candidates → Human Selection
```

## Component Details

### Core Infrastructure (`core/`)

| Component | Purpose |
|-----------|---------|
| `orchestrator.py` | Main pipeline coordinator |
| `budget.py` | Cost models, tracking, enforcement |
| `claude_client.py` | Claude SDK abstraction layer |
| `provider_config.py` | Provider factory and configuration |

### Provider System (`core/providers/`)

The provider pattern enables clean separation between agents and external APIs:

| Provider | Purpose | Status |
|----------|---------|--------|
| `base.py` | Abstract `VideoProvider` interface | ✅ Complete |
| `mock.py` | `MockVideoProvider` for testing | ✅ Complete |
| `runway.py` | `RunwayProvider` for Runway Gen-3 | ✅ Complete |
| `pika.py` | `PikaProvider` for Pika Labs | ⏳ TODO |
| `stability.py` | `StabilityProvider` for Stability AI | ⏳ TODO |

**Provider Interface:**
```python
class VideoProvider(ABC):
    async def generate_video(prompt, duration, **kwargs) -> GenerationResult
    async def check_status(job_id) -> Dict[str, Any]
    async def download_video(url, path) -> bool
    def estimate_cost(duration, **kwargs) -> float
    async def validate_credentials() -> bool
```

**Dependency Injection:**
```python
# Default (mock mode)
orchestrator = StudioOrchestrator(mock_mode=True)

# With explicit provider
from core.providers import RunwayProvider
from core.provider_config import ProviderFactory

provider = ProviderFactory.create_runway(api_key="sk-...")
orchestrator = StudioOrchestrator(video_provider=provider)

# From environment
provider = ProviderFactory.create_from_env()  # Uses VIDEO_PROVIDER env var
orchestrator = StudioOrchestrator(video_provider=provider)
```

### Agents (`agents/`)

| Agent | Purpose | Inputs | Outputs |
|-------|---------|--------|---------|
| `producer.py` | Budget planning | Request, Budget | Pilot strategies |
| `critic.py` | Quality evaluation | Scenes, QA scores | Continue/cancel decisions |
| `script_writer.py` | Scene breakdown | Concept, Duration | Scene list |
| `video_generator.py` | Video creation | Scenes, Tier | Generated videos |
| `qa_verifier.py` | Quality scoring | Videos, Scenes | QA results |
| `editor.py` | Final assembly | All videos, QA | EDL candidates |

## Data Flow

```python
# Simplified data flow

# 1. User input
request = "A day in the life of a developer..."
budget = 150.00

# 2. Producer plans
pilots = await producer.analyze_and_plan(request, budget)
# → [PilotStrategy(tier=animated, budget=60), ...]

# 3. Script breakdown (per pilot)
scenes = await script_writer.create_script(request, pilot.tier)
# → [Scene(id="scene_1", description="...", duration=5), ...]

# 4. Video generation (parallel per scene)
videos = await video_generator.generate_batch(scenes, pilot.tier)
# → [GeneratedVideo(url="...", cost=3.50), ...]

# 5. QA verification (parallel)
qa_results = await qa_verifier.verify_batch(scenes, videos)
# → [QAResult(score=85, passed=True), ...]

# 6. Critic evaluation
evaluation = await critic.evaluate_pilot(pilot, qa_results)
# → PilotResults(approved=True, budget_remaining=25.00)

# 7. Editor assembly (after all pilots complete)
edl_candidates = await editor.create_edl_candidates(all_videos, qa_results)
# → [EDLCandidate(approach="balanced", quality=88), ...]

# 8. Human selection
final_video = human_selects(edl_candidates)
```

## Budget Management

### Allocation Strategy
```
Total Budget: $150
├── Pilot A (static):     $40 (27%)
├── Pilot B (animated):   $60 (40%)
├── Pilot C (photo):      $50 (33%)
└── Reserve:              $0
```

### Dynamic Reallocation
```
After Test Phase:
├── Pilot A: Score 72 → Continue with 50% ($15 remaining)
├── Pilot B: Score 85 → Continue with 100% ($40 remaining)
└── Pilot C: Score 58 → CANCELLED → Reallocate to B (+$35)
```

## Error Handling

| Error Type | Handling |
|------------|----------|
| API rate limit | Exponential backoff |
| Generation failure | Retry up to 3x |
| Budget exceeded | Stop + return partial |
| QA failure | Flag for regeneration |
| Provider down | Fallback to secondary |

## Scalability

### Parallelization Points
- Pilots run in parallel
- Scenes within a pilot run in parallel
- Video variations run in parallel
- QA verification runs in parallel

### Resource Limits
```python
MAX_CONCURRENT_PILOTS = 3
MAX_CONCURRENT_SCENES = 5
MAX_CONCURRENT_GENERATIONS = 10
MAX_CONCURRENT_QA = 10
```

## Extensibility

### Adding New Agents
1. Create agent in `agents/`
2. Define inputs/outputs as dataclasses
3. Implement async methods
4. Register with orchestrator

### Adding New Providers
1. Create new provider class in `core/providers/` implementing `VideoProvider` interface
2. Add provider to `ProviderFactory` in `provider_config.py`
3. Update cost estimation in provider's `estimate_cost()` method
4. Add API key environment variable support (e.g., `PIKA_API_KEY`)
5. Create integration tests in `tests/integration/`

**Example:**
```python
# core/providers/pika.py
class PikaProvider(VideoProvider):
    def __init__(self, config: VideoProviderConfig):
        super().__init__(config)
        # Initialize Pika API client

    async def generate_video(self, prompt, duration, **kwargs):
        # Call Pika API
        pass

# core/provider_config.py
elif provider_enum == ProviderType.PIKA:
    api_key = os.getenv("PIKA_API_KEY")
    return PikaProvider(VideoProviderConfig(...))
```

### Adding New Production Tiers
1. Add to `ProductionTier` enum
2. Define `CostModel` in `budget.py`
3. Map to providers in generator
4. Set QA thresholds
