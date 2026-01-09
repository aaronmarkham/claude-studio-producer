# Claude Studio Producer

> Budget-aware multi-agent video production with AI orchestration. Manages competitive pilots, real video generation with Luma AI, vision-based QA analysis, and self-improving provider learnings.

## What's Working Now

- **Real video generation** with Luma AI (image-to-video)
- **Vision-based QA** using Claude to analyze extracted video frames
- **Provider learning system** that improves prompts over time
- **Web dashboard** to view runs, preview videos, and see QA scores
- **CLI tool** with live progress and detailed feedback

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
        STM["Short-Term Memory<br/>Run state, progress, assets"]
        LTM["Long-Term Memory<br/>Patterns, preferences,<br/>provider learnings"]
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

    LTM -.->|"provider guidelines"| Producer
    LTM -.->|"prompt tips"| ScriptWriter
    Critic -.->|"provider learnings"| LTM
```

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

Learnings are stored in `artifacts/memory.json` and used to improve future runs.

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
| **EditorAgent** | Implemented | Creates EDL candidates for final assembly |
| **AudioGeneratorAgent** | Stub | Audio generation (interface ready) |
| **AssetAnalyzerAgent** | Stub | Seed asset analysis with Claude Vision |

## Providers

| Provider | Status | Notes |
|----------|--------|-------|
| **Luma AI** | Implemented | Image-to-video, real API integration |
| Runway ML | Stub | Interface + cost model ready |
| Pika Labs | Stub | Interface + cost model ready |
| Kling AI | Stub | Interface + cost model ready |

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
│   ├── produce.py          # Main CLI with --live mode
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
│   │   └── memory.py       # ProviderKnowledge, ProviderLearning, etc.
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
│   ├── architecture_current.md    # Current system diagram
│   ├── architecture_future_strands.md  # Future Strands memory integration
│   └── specs/              # Detailed specifications
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

### In Progress
- [ ] Strands native memory integration (currently custom JSON)
- [ ] Audio generation pipeline
- [ ] Additional video providers (Runway, Pika)

### Future
- [ ] Semantic search over memories
- [ ] Multi-pilot competitive generation
- [ ] Audio-video synchronization
- [ ] S3 storage integration

## License

MIT-0 (MIT No Attribution) - see [LICENSE](LICENSE)

## Links

- [GitHub Issues](https://github.com/aaronmarkham/claude-studio-producer/issues)
- [Architecture Docs](docs/)
