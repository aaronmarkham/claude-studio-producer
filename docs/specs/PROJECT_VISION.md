# Claude Studio Producer - Project Vision

## Overview

A budget-aware multi-agent video production system that uses competitive pilots to optimize quality and cost. The system was inspired by a real video production workflow where:

1. A **Producer** plans multiple competing pilot strategies based on budget
2. **Pilots** generate test scenes in parallel at different quality tiers
3. A **Critic** evaluates results and decides which pilots continue
4. Winners get more budget, losers are cancelled
5. An **Editor** creates final video from best scenes

## The "Inception" Use Case

The original prototype demonstrated this with a meta use case:
> "A day in the life of a writer making a document about how to use a multi-agent system"

The workflow:
1. First agent creates script of different scenes
2. Second agent (parallel) generates video variations for each scene
3. Video describer checks if generated video matches intent
4. Editor picks best matching sequences
5. Creates EDL (Edit Decision List) candidates
6. Human reviews final candidates and provides feedback

## Core Innovation

**Competitive Pilot System**: Instead of generating one video, we generate multiple competing versions at different quality/cost tiers, then let AI evaluate and reallocate budget dynamically.

## Current State (v0.3.0)

### Implemented ✅
- `ProducerAgent` - Budget analysis and pilot strategy planning
- `CriticAgent` - Quality evaluation and budget reallocation
- `ScriptWriterAgent` - Breaks video concepts into detailed scene-by-scene scripts
- `VideoGeneratorAgent` - Video generation with pluggable providers (mock mode + API-ready)
- `StudioOrchestrator` - Full pipeline coordination
- `BudgetTracker` - Real-time cost monitoring
- Skills system - Progressive disclosure with `video_generation` skill
- Cost models for 4 production tiers (2025 pricing)
- Budget enforcement (prevents overspending)
- Retry logic and error handling

### Simulated (Mock Mode) 🔶
- Video generation APIs (mock mode enabled by default for testing)
- QA verification (returns random scores within tier range)

### Not Yet Implemented ❌
- Real video API integration (Runway, Pika, Stability AI providers)
- QAVerifierAgent (vision-based quality analysis)
- EditorAgent (EDL generation and assembly)
- PromptVariationAgent
- Additional skills (scene-analysis, editing)
- Web UI dashboard
