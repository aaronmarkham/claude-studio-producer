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
cli/              # CLI commands (produce, produce-video, training, kb, memory, provider)
core/
  ├── providers/  # Video/audio/image/music/storage providers
  │   ├── video/  # luma.py, runway.py, pika.py (stub), etc.
  │   └── audio/  # elevenlabs.py, openai_tts.py, etc.
  ├── memory/     # MemoryManager, bootstrap
  ├── models/     # Data models (memory.py, knowledge.py, document.py, video_production.py)
  ├── training/   # Podcast training pipeline (transcription, classification, profiles)
  └── *.py        # claude_client, budget, renderer, orchestrator, video_production
server/           # FastAPI dashboard
docs/specs/       # Design specs (read these for feature details)
artifacts/        # Run outputs, memory.json, training_output/
.claude/          # Claude Code skills and agent configs
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
claude-studio kb inspect "Project" --quality          # Show atom/topic/entity distribution
claude-studio kb inspect --file path/to/kg.json --topics  # Inspect any KG file

# Training pipeline (ML-style podcast improvement)
claude-studio training run my-project --reference-audio podcast.mp3
claude-studio training list
claude-studio training show trial_000_20260205

# Video production from training (budget-aware, scene-by-scene audio)
claude-studio produce-video -t trial_000 --show-tiers          # Show costs per tier
claude-studio produce-video -t trial_000 --budget low --mock   # Hero images only
claude-studio produce-video -t trial_000 --budget medium --kb my-project --live
claude-studio produce-video -t trial_000 --budget medium --live --voice lily  # With audio

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

### ElevenLabs Voice IDs

Common voice name → ID mappings (used in `cli/test_provider.py`):
- `lily` → `pFZP5JQG7iQjIQuC4Bku`
- `rachel` → `21m00Tcm4TlvDq8ikWAM`
- `adam` → `pNInz6obpgDQGcFmaJgB`

### Budget Tiers (Video Production)

Tiers use **proportional ratios** to ensure consistent quality across different scene counts:

| Tier | Image Ratio | Luma Ratio | Description |
|------|-------------|------------|-------------|
| `micro` | 0% | 0% | Text overlays only |
| `low` | 10% | 0% | Hero images for key moments |
| `medium` | 27% | 0% | Consolidated images with Ken Burns |
| `high` | 55% | 3% | Full images, selective animation |
| `full` | 100% | 100% | All scenes get unique visuals |

Example: For 100 scenes, medium tier produces ~27 images shared across all scenes.
For 10 scenes, medium tier produces ~3 images.

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

### FFmpeg Patterns

```bash
# Merge audio into video (copy video, encode audio)
ffmpeg -i video.mp4 -i audio.mp3 -map 0:v -map 1:a -c:v copy -c:a aac -shortest output.mp4

# Speed-match audio to video duration
ffmpeg -i video.mp4 -i audio.mp3 -filter_complex "[1:a]atempo=1.2[a]" -map 0:v -map "[a]" output.mp4
```

### Documentation Structure

- `docs/dev_notes.md` — Internal dev notes (excluded from Jekyll build)
- `docs/dev-journal.md` — Public-facing journal (in `_config.yml` header_pages)
- `docs/_config.yml` — Jekyll config, controls what appears on GitHub Pages
- When adding dev entries, update **both** files (dev_notes for detail, dev-journal for public)

## Active Specs (read before implementing)

- [PODCAST_TRAINING_PIPELINE.md](docs/specs/PODCAST_TRAINING_PIPELINE.md) — ML-style podcast quality training
- [TRANSCRIPT_LED_VIDEO_PRODUCTION.md](docs/specs/TRANSCRIPT_LED_VIDEO_PRODUCTION.md) — Budget-aware visual generation from scripts
- [MULTI_PROVIDER_ORCHESTRATION.md](docs/specs/MULTI_PROVIDER_ORCHESTRATION.md) — Provider system architecture
- [AUDIO_VIDEO_ORCHESTRATION_PATCH.md](docs/specs/AUDIO_VIDEO_ORCHESTRATION_PATCH.md) — Wire audio into EDL + mixing

## Working Style

- Use the codebase-scout subagent to find files before modifying them
- Use the test-runner subagent after making changes
- Read only the specific section of a spec needed for the current task
- Do not read entire files when Grep can find the relevant lines
- After implementing, always run: `python -m py_compile <file>` then `pytest`

## Current State (Feb 2026)

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
- Audio-video synchronization and mixing
- Podcast training pipeline (ML-style iterative improvement)
- Transcript-led video production with budget tiers
- Scene importance scoring for image allocation
- KB figure integration in video production
- Figure-aware script generation (scripts reference figures explicitly)
- KB inspect command with quality reports (atom/topic/entity distribution)
- Scene-by-scene audio generation (avoids ElevenLabs limits, per-scene .mp3)
- Proportional budget tiers (consistent quality across different scene counts)
- Audio from generated script (not original transcription)
- Claude Code skills (`/produce`, `/train`)
- StructuredScript and ContentLibrary data models (Phase 1 of UNIFIED_PRODUCTION_ARCHITECTURE.md)
- ContentLibrarian module with assembly manifest builder (Phase 2 of UNIFIED_PRODUCTION_ARCHITECTURE.md)

In progress:
- Additional video providers (Pika, Kling stubbed)
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
