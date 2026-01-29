# Claude Studio Producer - AI Context

> This file helps AI assistants understand the project quickly after restarts.

## What This Is

A multi-agent video production system using Claude + Strands SDK. Takes a concept + budget, orchestrates agents to plan, script, generate video/audio, QA with vision, critique, and edit into final output. Features a learning system that improves prompts over time.

## Tech Stack

- **Claude** - LLM for all agents
- **Strands SDK** - Agent orchestration
- **Click + Rich** - CLI
- **Luma AI** - Video generation (primary)
- **ElevenLabs / OpenAI** - TTS audio
- **FFmpeg** - Video rendering
- **PyMuPDF** - PDF ingestion (optional)

## Agent Pipeline

```
User Request → Producer → ScriptWriter → VideoGenerator → QAVerifier → Critic → Editor → Renderer
                  ↑                                           ↓
                  └──────── Memory (learnings) ←──────────────┘
```

| Agent | Role |
|-------|------|
| **ProducerAgent** | Budget planning, pilot strategies |
| **ScriptWriterAgent** | Scene breakdown with provider guidelines |
| **VideoGeneratorAgent** | Calls video providers (Luma, Runway) |
| **AudioGeneratorAgent** | TTS with ElevenLabs/OpenAI |
| **QAVerifierAgent** | Claude Vision analysis of frames |
| **CriticAgent** | Scores results, extracts learnings |
| **EditorAgent** | Creates EDL (edit decision list) |
| **ProviderOnboardingAgent** | Onboards new providers from docs |

## Key Directories

```
agents/           # Agent implementations
cli/              # CLI commands (produce, kb, luma, memory, provider)
core/
  ├── providers/  # Video/audio/image/music/storage providers
  │   ├── video/  # luma.py, runway.py, pika.py (stub), etc.
  │   └── audio/  # elevenlabs.py, openai_tts.py, etc.
  ├── memory/     # MemoryManager, bootstrap
  ├── models/     # Data models (memory.py, knowledge.py, document.py)
  └── *.py        # claude_client, budget, renderer, orchestrator
server/           # FastAPI dashboard
docs/specs/       # Design specs (read these for feature details)
artifacts/        # Run outputs, memory.json
```

## Common Commands

```bash
# Production (mock mode - no API costs)
python -m cli.produce "concept" --budget 5

# Live mode with real generation
python -m cli.produce "concept" --budget 5 --live --provider luma

# With narrative style
python -m cli.produce "concept" --style podcast  # or: educational, documentary, visual_storyboard

# Knowledge base
claude-studio kb create "Project" -d "Description"
claude-studio kb add "Project" --paper doc.pdf
claude-studio kb produce "Project" -p "prompt" --style podcast

# Memory/learnings
claude-studio memory list luma
claude-studio memory add luma tip "Use detailed physical descriptions"

# Provider management
claude-studio provider list
claude-studio provider test luma --live
claude-studio provider onboard -n newprovider -t video --docs-url https://...

# Combine scenes from a run
python -m cli.combine <run_id> --scenes 1,3,5

# Run tests
pytest
```

## Provider System

Providers implement a common interface. Status:
- **Video**: Luma (ready), Runway (ready), Pika/Kling/Stability (stubs)
- **Audio**: ElevenLabs (ready), OpenAI TTS (ready), Google TTS (ready), Inworld (stub)
- **Image**: DALL-E (ready), Stability (stub)
- **Music/Storage**: All stubs

Onboard new providers: `claude-studio provider onboard -n name -t type --docs-url URL`

## Memory/Learning System

Multi-tenant namespace hierarchy: `SESSION → USER → ORG → PLATFORM`

- Learnings stored per provider (tips, gotchas, avoid patterns, preferences)
- ScriptWriter uses learnings to improve prompts
- Critic extracts new learnings after each run
- Learnings can be promoted up the hierarchy based on validation

Storage: `artifacts/memory.json` (local) or Bedrock AgentCore (production)

## Development Patterns

1. **API drift is common** - Always validate API signatures against current docs
2. **Test providers first** - Use `provider test` before running full pipeline
3. **Mock mode by default** - Use `--live` only when ready for real API calls
4. **Checkpointing** - Provider onboarding has resume capability (`--resume`)
5. **Parallelism consideration** - For narrative consistency, video scenes often need sequential generation with keyframe passing

## Current State (Jan 2026)

Working:
- Full agent pipeline with Luma + ElevenLabs
- Vision-based QA with Claude
- Provider learning/memory system
- Knowledge base with PDF ingestion
- Narrative styles (podcast, educational, documentary)
- Provider onboarding agent
- DALL-E image generation
- Google Cloud TTS (Neural2, WaveNet, Studio voices)
- Runway ML video (image-to-video)
- Multi-provider pipeline (DALL-E → Runway chaining)

In progress:
- Additional video providers (Pika, Kling stubbed)
- Audio-video synchronization
- Multi-pilot competitive generation

## Useful Files to Read

- [README.md](README.md) - Full overview
- [docs/dev_notes.md](docs/dev_notes.md) - Developer journal with lessons learned
- [docs/specs/ARCHITECTURE.md](docs/specs/ARCHITECTURE.md) - System architecture
- [docs/specs/MULTI_TENANT_MEMORY_ARCHITECTURE.md](docs/specs/MULTI_TENANT_MEMORY_ARCHITECTURE.md) - Memory system
- [docs/specs/KNOWLEDGE_TO_VIDEO.md](docs/specs/KNOWLEDGE_TO_VIDEO.md) - KB pipeline
- [docs/providers.md](docs/providers.md) - Provider details

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...  # Required
LUMA_API_KEY=luma-...         # For live video
ELEVENLABS_API_KEY=...        # For TTS
OPENAI_API_KEY=...            # Alternative TTS
RUNWAY_API_KEY=...            # Alternative video
```
