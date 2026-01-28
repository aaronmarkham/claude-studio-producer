# Claude Studio Producer

> Budget-aware multi-agent video production with AI orchestration. Manages competitive pilots, real video generation with Luma AI, text to audio generation with ElevenLabs, vision-based QA analysis, and self-improving provider learnings.

## Tech stack
1. Claude (obviously)
2. Strands SDK (for agent workflows)
3. Click and Rich (for the CLI)

**Optional**
a. lumaai (you can use other [providers](docs/providers.md))
b. pymupdf (if you want pdf source material)
c. jinja2 (if you want to use the dashboard)

## Vision
I wanted to make a demo project that 1) shows off what you can do pretty quickly with Claude; 2) how to design and implement a working multi-agent workflow; 3) use learning/memory; 4) use rewards; and 5) have fun.

If you're curious about the design aspect, there are a bunch of [spec docs](docs/specs) and you can look at their timestamps to get a rough idea of the layering of the features. Well, I/we (me & the Claudes) did a lot in two days, let's just say that.

[Read more about the project in my developer notes](docs/dev_notes.md)

## Quick Start

```bash
# Clone and install
git clone https://github.com/aaronmarkham/claude-studio-producer.git
cd claude-studio-producer
pip install -e ".[server]"

# Set up API keys
cp .env.example .env
# Add ANTHROPIC_API_KEY and LUMA_API_KEY

# Run a production (mock mode - no API costs)
python -m cli.produce "A serene mountain lake at sunset" --budget 5

# Run with real video generation
python -m cli.produce "A serene mountain lake at sunset" --budget 5 --live
```

## Architecture

```mermaid
flowchart TB
    subgraph Input["Input"]
        Request["Production Request<br/>concept + budget + seed assets"]
    end

    subgraph Memory["Memory System"]
        LTM["Long-Term Memory<br/>Multi-tenant namespace hierarchy<br/>Platform → Org → User → Session"]
    end

    subgraph Planning["Planning Stage"]
        Producer["ProducerAgent<br/>Creates pilot strategies"]
        ScriptWriter["ScriptWriterAgent<br/>Generates scenes"]
    end

    subgraph Generation["Parallel Generation"]
        Video["VideoGenerator<br/>Luma / Runway"]
        Audio["AudioGenerator<br/>OpenAI TTS"]
    end

    subgraph Evaluation["Real Evaluation Pipeline"]
        QA["QAVerifier<br/>Claude Vision<br/>Frame extraction + analysis"]
        Critic["CriticAgent<br/>Scores + decisions +<br/>provider analysis"]
    end

    subgraph Output["Output Stage"]
        Editor["EditorAgent<br/>Edit candidates"]
        Renderer["FFmpegRenderer<br/>Final video + text overlays"]
    end

    Request --> Producer
    Producer --> ScriptWriter
    ScriptWriter --> Video
    ScriptWriter --> Audio
    Video --> QA
    Audio --> QA
    QA --> Critic
    Critic --> Editor
    Editor --> Renderer

    LTM -.->|"provider guidelines<br/>avoid patterns"| Producer
    LTM -.->|"prompt tips<br/>what works"| ScriptWriter
    Critic -.->|"new learnings<br/>what worked/failed"| LTM
```

### Multi-Tenant Memory System

The memory system uses a hierarchical namespace structure for learnings:

```
PROVIDER LEARNING LIFECYCLE
============================

1. ONBOARDING (one-time per provider)
   ┌─────────────────┐
   │  API Docs       │──► Onboarding ──► tips, gotchas, limitations
   │  Stub File      │    Agent          │
   └─────────────────┘                   │
                                         ▼
2. STORAGE (namespace hierarchy)      ┌─────────┐
                                      │  USER   │ ◄── initial home
   ┌──────────────────────────────────┴─────────┴──────────────────┐
   │                                                               │
   │   SESSION (0.5)  ──►  USER (0.65)  ──►  ORG (0.8)  ──►  PLATFORM (1.0)
   │   experimental       validated         team-wide       curated
   │                          ▲                 ▲
   │                          │                 │
   │                     promote if         promote if
   │                     works well        cross-team value
   └───────────────────────────────────────────────────────────────┘

3. PRODUCTION (ongoing)
   ┌─────────────────┐      ┌─────────────┐      ┌─────────────┐
   │  ScriptWriter   │◄─────│   merged    │◄─────│  all tiers  │
   │  (uses tips)    │      │  learnings  │      │  by priority│
   └────────┬────────┘      └─────────────┘      └─────────────┘
            │
            ▼
   ┌─────────────────┐
   │  Video/Audio    │──► actual generation
   │  Generation     │
   └────────┬────────┘
            │
            ▼
   ┌─────────────────┐      ┌─────────────┐
   │  Critic Agent   │──────│   SESSION   │──► new learnings
   │  (evaluates)    │      │   memory    │    (what worked/failed)
   └─────────────────┘      └─────────────┘
```

**Key Features:**
- **Priority-based retrieval**: Platform learnings override org, org overrides user
- **Automatic promotion**: Learnings can be promoted up the hierarchy based on validation count
- **CLI management**: `claude-studio memory` commands for viewing, adding, and managing learnings
- **Categories**: avoid, prefer, tip, pattern - for different types of provider knowledge

## Features

### CLI with Live Progress

```bash
# Basic production
python -m cli.produce "Product demo for mobile app" --budget 10

# With seed image (image-to-video)
python -m cli.produce "Animate this logo" --budget 5 --seed logo.png

# Live mode with real generation
python -m cli.produce "Tech startup intro" --budget 15 --live --provider luma
```

The CLI shows:
- Real-time agent progress
- QA scores per scene (Visual, Style, Technical, Narrative)
- Issues found and suggestions
- Provider learnings extracted

### Custom Scene Combinations

After a production run, create custom edits by combining specific scenes:

```bash
# List available scenes from a run
python -m cli.combine 20260109_080534 --list

# Combine scenes 1 and 3 (skipping scene 2)
python -m cli.combine 20260109_080534 --scenes 1,3

# Combine with custom output name
python -m cli.combine 20260109_080534 --scenes 1,3,5 -o highlight_reel.mp4
```

This is useful when:
- Some scenes have different actors/styles you want to exclude
- Creating alternate cuts or highlight reels
- Manual override of the automated EDL

### Knowledge Base (Multi-Source Document Production)

Create videos from research papers, documents, and notes with automatic knowledge extraction:

```bash
# Create a knowledge project
claude-studio kb create "AI Research" -d "Papers on neural networks"

# Add a PDF paper (uses Claude for intelligent atom extraction)
claude-studio kb add "AI Research" --paper paper.pdf

# Add with mock mode (faster, no LLM costs)
claude-studio kb add "AI Research" --paper paper.pdf --mock

# View project summary
claude-studio kb show "AI Research" --graph

# Produce video from knowledge base
claude-studio kb produce "AI Research" \
  -p "Explain the key findings and methodology" \
  --style podcast \
  --duration 120 \
  --mock
```

**Features:**
- **Document ingestion**: Extracts atoms (paragraphs, figures, tables, equations) with PyMuPDF
- **LLM classification**: Claude categorizes atoms by type and extracts topics/entities
- **Knowledge graph**: Builds cross-document connections via shared entities
- **Rich concept generation**: Assembles KB content into detailed prompts for ScriptWriter

```mermaid
flowchart LR
    subgraph Sources["Source Documents"]
        PDF1["PDF Paper 1"]
        PDF2["PDF Paper 2"]
        Note["Text Notes"]
    end

    subgraph Ingestion["Document Ingestion"]
        PyMuPDF["PyMuPDF<br/>Text + Figure Extraction"]
        Claude["Claude LLM<br/>Atom Classification<br/>Topic/Entity Extraction"]
    end

    subgraph KB["Knowledge Project"]
        DG1["DocumentGraph 1<br/>atoms, hierarchy"]
        DG2["DocumentGraph 2<br/>atoms, hierarchy"]
        KG["KnowledgeGraph<br/>cross-links, themes,<br/>entity index"]
    end

    subgraph Production["Video Production"]
        Concept["Rich Concept<br/>abstracts + quotes +<br/>figures + entities"]
        Pipeline["Production Pipeline<br/>ScriptWriter → Video →<br/>Audio → QA → Edit"]
    end

    PDF1 --> PyMuPDF
    PDF2 --> PyMuPDF
    Note --> KG
    PyMuPDF --> Claude
    Claude --> DG1
    Claude --> DG2
    DG1 --> KG
    DG2 --> KG
    KG --> Concept
    Concept --> Pipeline
```

### Narrative Styles

Control how verbose and conversational your scripts are:

```bash
# Brief visual storyboard (default) - ~20-30 words per scene
claude-studio produce -c "Product demo" --style visual_storyboard

# Rich podcast narrative (NotebookLM-style) - ~100 words per scene
claude-studio produce -c "Explain quantum computing" --style podcast

# Educational lecture format - ~80-120 words per scene
claude-studio produce -c "Tutorial on React hooks" --style educational

# Documentary with gravitas - ~60-100 words per scene
claude-studio produce -c "History of the internet" --style documentary
```

| Style | Words/Scene | Best For |
|-------|-------------|----------|
| `visual_storyboard` | ~20-30 | Product demos, ads, visual-first content |
| `podcast` | ~85-100 | Explainers, research summaries, educational deep-dives |
| `educational` | ~80-120 | Tutorials, lectures, learning content |
| `documentary` | ~60-100 | Narratives, historical content, storytelling |

### Web Dashboard

```bash
# Start the server
python -m server.main

# Open http://localhost:8000
```

View all runs, preview generated videos, and inspect QA scores.

### Real QA with Claude Vision

When using `--live` mode, the QA system:
1. Extracts frames from generated videos using ffmpeg
2. Sends frames to Claude Vision for analysis
3. Scores on 4 dimensions (0-100 each):
   - **Visual Accuracy**: Do visuals match the scene description?
   - **Style Consistency**: Does it match the production tier?
   - **Technical Quality**: Any artifacts, blur, or issues?
   - **Narrative Fit**: Does it work in the overall story?
4. Records issues and improvement suggestions

### Provider Learning (Self-Improving)

The system learns from every run:

```
Run 1: "magical transformation effect" -> Score: 45
  -> Learning: "Luma struggles with VFX transformations"
  -> Added to avoid_list

Run 2: System avoids VFX, uses "slow camera pan" -> Score: 88
  -> Learning: "Detailed physical descriptions work well"
  -> Added to prompt_guidelines

Run 3+: Better prompts, higher scores
```

Learnings are stored in the multi-tenant memory system (`artifacts/memory/`) and used to improve future runs. Use `claude-studio memory list luma` to see current learnings.

## Screenshots

### CLI Production Stages

The CLI shows real-time progress through each stage of production:

**Stage 1: Planning** - Producer creates pilot strategy, ScriptWriter generates scenes

![Planning Stage](docs/screenshots/luma-gen1-stage1.png)

**Stage 2: Generation** - Video generation with Luma AI

![Generation Stage](docs/screenshots/luma-gen1-stage2.png)

**Stage 3: QA & Evaluation** - Claude Vision analyzes frames, Critic extracts learnings

![QA Stage](docs/screenshots/luma-gen1-stage3.png)

**Stage 4: Output** - Editor creates EDL, Renderer produces final video

![Output Stage](docs/screenshots/luma-gen1-stage4.png)

### Generated Videos

Example outputs from Luma AI image-to-video generation:

| Pencil Animation | Keyboard Animation |
|------------------|-------------------|
| ![Pencil Video](docs/screenshots/luma-gen1-pencil-video.png) | ![Keyboard Video](docs/screenshots/luma-gen2-keyboard-video.png) |

### Provider Learnings

The system accumulates learnings from each run to improve future prompts:

![Recent Learnings](docs/screenshots/recent-learnings.png)

## Agents

| Agent | Status | Description |
|-------|--------|-------------|
| **ProducerAgent** | Implemented | Analyzes requests, creates pilot strategies using provider knowledge |
| **ScriptWriterAgent** | Implemented | Breaks concepts into scenes, applies learned prompt guidelines |
| **VideoGeneratorAgent** | Implemented | Generates video with Luma AI (real) or mock providers |
| **QAVerifierAgent** | Implemented | Vision-based quality analysis with Claude |
| **CriticAgent** | Implemented | Evaluates results, extracts provider learnings |
| **ProviderOnboardingAgent** | Implemented | Analyzes API docs, generates provider implementations, validates with tests |
| **EditorAgent** | Implemented | Creates EDL candidates for final assembly |
| **AudioGeneratorAgent** | Implemented | TTS voiceover generation with ElevenLabs/OpenAI |
| **DocumentIngestorAgent** | Implemented | PDF ingestion, atom extraction, LLM classification |
| **AssetAnalyzerAgent** | Stub | Seed asset analysis with Claude Vision |

## Providers

### Video Providers

| Provider | Status | Notes |
|----------|--------|-------|
| **Luma AI** | Implemented | Image-to-video, text-to-video, scene chaining |
| Runway ML | Stub | Interface + cost model ready |
| Pika Labs | Stub | Interface + cost model ready |
| Kling AI | Stub | Interface + cost model ready |

### Audio Providers (TTS)

| Provider | Status | Notes |
|----------|--------|-------|
| **ElevenLabs** | Implemented | High-quality TTS, 29 languages, voice cloning |
| **OpenAI TTS** | Implemented | 6 voices, fast generation |
| Google TTS | Stub | Interface ready |
| Inworld | Stub | Interface ready |

[Read more about providers](docs/providers.md)

## Project Structure

```
claude-studio-producer/
├── agents/                 # Agent implementations
│   ├── producer.py         # Pilot strategy creation
│   ├── script_writer.py    # Scene generation with provider guidelines
│   ├── video_generator.py  # Video generation orchestration
│   ├── qa_verifier.py      # Real vision-based QA
│   ├── critic.py           # Evaluation + provider learning extraction
│   └── editor.py           # EDL generation
│
├── cli/
│   ├── produce.py          # Main CLI with --live mode and --style
│   ├── kb.py               # Knowledge base management CLI
│   └── luma.py             # Luma testing CLI
│
├── core/
│   ├── claude_client.py    # Claude SDK wrapper with vision support
│   ├── budget.py           # Cost models and tracking
│   ├── renderer.py         # FFmpeg video rendering
│   ├── memory/             # Memory system
│   │   ├── manager.py      # MemoryManager (STM + LTM)
│   │   └── bootstrap.py    # Provider knowledge seeding
│   ├── models/
│   │   ├── memory.py       # ProviderKnowledge, ProviderLearning, etc.
│   │   ├── knowledge.py    # KnowledgeProject, KnowledgeGraph, KnowledgeSource
│   │   └── document.py     # DocumentGraph, DocumentAtom, AtomType
│   └── providers/
│       └── video/
│           ├── luma.py     # Real Luma AI integration
│           └── ...         # Other provider stubs
│
├── server/
│   ├── main.py             # FastAPI server
│   ├── routes/
│   │   ├── runs.py         # Run list and preview API
│   │   └── memory.py       # Memory/LTM API
│   └── templates/          # Dashboard HTML templates
│
├── docs/
│   └── specs/              # Detailed specifications
│       ├── MULTI_TENANT_MEMORY_ARCHITECTURE.md  # Memory system design
│       └── ...             # Other specs
│
└── artifacts/              # Run outputs
    ├── memory.json         # LTM with provider learnings
    └── runs/               # Per-run data and videos
```

## Configuration

```bash
# .env file
ANTHROPIC_API_KEY=sk-ant-...    # Required
LUMA_API_KEY=luma-...           # For live video generation
RUNWAY_API_KEY=...              # For Runway provider (optional)
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,server]"

# Run tests
pytest

# Start server with auto-reload
uvicorn server.main:app --reload
```

## Roadmap

### Completed
- [x] Multi-agent orchestration with Strands
- [x] Real video generation (Luma AI)
- [x] Vision-based QA with Claude
- [x] Provider learning system (LTM)
- [x] Web dashboard
- [x] CLI with live progress
- [x] FFmpeg rendering
- [x] Multi-tenant memory system with namespace hierarchy
- [x] Memory CLI (`claude-studio memory` commands)
- [x] Learning promotion system (session → user → org → platform)
- [x] Provider onboarding agent with auto-test and session resume
- [x] ElevenLabs TTS integration (voice selection, streaming, voice settings)
- [x] OpenAI TTS integration
- [x] Knowledge base system (`kb` CLI for multi-source document management)
- [x] Document ingestion with figure extraction (PyMuPDF + Claude)
- [x] Configurable narrative styles (podcast, educational, documentary)

### In Progress
- [ ] Additional video providers (Runway, Pika)
- [ ] Additional audio providers (Google TTS, Inworld)

### Future
- [ ] AWS AgentCore memory backend (production)
- [ ] Multi-pilot competitive generation
- [ ] Audio-video synchronization
- [ ] S3 storage integration

## License

MIT-0 (MIT No Attribution) - see [LICENSE](LICENSE)

## Links

- [GitHub Issues](https://github.com/aaronmarkham/claude-studio-producer/issues)
- [Architecture Docs](docs/specs)
- [Developer log](docs/dev_notes.md)
- [Providers](docs/providers.md)
