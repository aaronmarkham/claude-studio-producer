# Claude Studio Producer — CLI Reference

Complete CLI reference for the AI video production pipeline.

## Quick Start

```bash
# Quick demo with mock providers
cs produce -c "Logo reveal for TechCorp" -d 5 --mock

# Live production with Luma
cs produce -c "Product demo" -b 15 -d 30 --live -p luma

# Generate video from transcript
cs produce-video --script script.txt --live --kb my-project
```

## Command Reference

### Content & Knowledge

| Command | Description | Docs |
|---------|-------------|------|
| `document` | Ingest PDFs into knowledge graphs | [document.md](document.md) |
| `kb` | Multi-source knowledge base management | [kb.md](kb.md) |
| `training` | Podcast calibration from reference pairs | [training.md](training.md) |

### Production

| Command | Description | Docs |
|---------|-------------|------|
| `produce` | Full video production pipeline | [produce.md](produce.md) |
| `produce-video` | Explainer video from scripts/training | [produce-video.md](produce-video.md) |
| `assemble` | Rough cut assembly from production assets | [assemble.md](assemble.md) |
| `assets` | Asset tracking and approval workflow | [assets.md](assets.md) |
| `render` | Render EDLs, mix video+audio | [render.md](render.md) |
| `resume` | Resume interrupted productions | [resume.md](resume.md) |

### Publishing

| Command | Description | Docs |
|---------|-------------|------|
| `upload` | YouTube upload, metadata updates, auth | [upload.md](upload.md) |

### System & Providers

| Command | Description | Docs |
|---------|-------------|------|
| `agents` | List and inspect agents | [utilities.md](utilities.md#agents) |
| `config` | Configuration management | [utilities.md](utilities.md#config) |
| `luma` | Luma API management (list, download, recover) | [utilities.md](utilities.md#luma) |
| `memory` | Memory and learnings management | [utilities.md](utilities.md#memory) |
| `providers` | Provider listing, checking, testing | [providers.md](providers.md) |
| `qa` | QA inspection of production quality | [utilities.md](utilities.md#qa) |
| `secrets` | API key management (OS keychain) | [utilities.md](utilities.md#secrets) |
| `status` | System status | [utilities.md](utilities.md#status) |
| `test-provider` | Quick single-provider validation | [providers.md](providers.md) |
| `themes` | Color theme selection | [utilities.md](utilities.md#themes) |

## Typical Workflow

```
document/kb → training (optional) → produce-video → assemble → upload
```

1. **Ingest** — `cs kb create` + `cs kb add --paper` to build a knowledge base
2. **Script** — `cs kb script` to generate a podcast script from KB content
3. **Produce** — `cs produce-video --script` to generate video assets
4. **Assemble** — `cs assemble` to create rough cut
5. **Upload** — `cs upload youtube` to publish

## Setup

```bash
# Set API keys via OS keychain
cs secrets set ANTHROPIC_API_KEY
cs secrets set OPENAI_API_KEY
cs secrets set ELEVENLABS_API_KEY  # optional, OpenAI TTS is fallback
cs secrets set LUMA_API_KEY        # for video generation

# Check everything
cs status
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API (content analysis, scripting) |
| `OPENAI_API_KEY` | DALL-E images + TTS fallback |
| `ELEVENLABS_API_KEY` | Primary TTS provider |
| `LUMA_API_KEY` | Luma AI video generation |
| `RUNWAY_API_KEY` | Runway ML video generation |
| `TTS_PROVIDER` | Force TTS provider (`openai` to skip ElevenLabs) |
