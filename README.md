# 🎬 Claude Studio Producer

> Budget-aware multi-agent video production with AI orchestration, vision-powered seed assets, and 5-tier audio pipeline

A production-grade AI system that manages competitive video production pilots, analyzes seed assets with Claude Vision, integrates synchronized audio, and reallocates budgets dynamically.

## 🌟 Features

### Multi-Agent Orchestration
- **🎯 Producer Agent**: Analyzes requests and budgets, creates multi-tier pilot strategies
- **🔍 Critic Agent**: Gap analysis and quality-based budget reallocation decisions
- **✍️ Script Writer Agent**: Breaks video concepts into detailed scene specifications with audio sync points
- **🎥 Video Generator Agent**: Generates video content using AI providers with cost tracking
- **🎵 Audio Generator Agent**: Produces voiceover, music, and SFX with time-synchronized audio (stub)
- **🖼️ Asset Analyzer Agent**: Uses Claude Vision to analyze seed assets and extract themes
- **✂️ Editor Agent**: Creates EDL candidates and final assembly from approved scenes (stub)

### Seed Asset Support
- **Vision-Powered Analysis**: Analyze images, sketches, storyboards, logos, and mood boards
- **Theme Extraction**: Automatically identify visual themes, color palettes, and style keywords
- **Brand Consistency**: Inform creative direction using extracted asset descriptions
- **Supported Types**: Sketches, storyboards, photos, logos, screenshots, mood boards, character designs

### Audio Pipeline
- **5-Tier Production**: NONE → MUSIC_ONLY → SIMPLE_OVERLAY → TIME_SYNCED → FULL_PRODUCTION
- **Synchronized Audio**: Frame-accurate sync points for audio-visual alignment
- **Voiceover Styles**: Professional, conversational, energetic, calm, dramatic
- **Music Integration**: Mood-based music (upbeat, corporate, emotional, ambient) with auto-ducking
- **Sound Effects**: Timestamped SFX cues with volume control

### Budget-Aware Production
- **Real-Time Cost Tracking**: Monitor video and audio costs across all production stages
- **Competitive Pilots**: Test 2-3 approaches in parallel, continue only the best performers
- **Dynamic Reallocation**: Cancel underperforming pilots and redirect budget to winners
- **Quality Feedback Loops**: Automated QA evaluation with vision analysis at every stage

### Provider Support
- **Video Providers**: Runway, Pika, Luma, Kling, Stability AI (stubs with cost models)
- **Audio Providers**: ElevenLabs, OpenAI TTS, Google TTS (stubs)
- **Music Providers**: Mubert, Suno (stubs)
- **Storage**: Local filesystem, AWS S3 (stubs)

## 🏗️ Architecture

The full production pipeline from request to final video:

```
┌─────────────────────────────────────────────────────────────────┐
│  User Request + Seed Assets                                     │
│  "Create a 60s product demo video"                              │
│  + logo.png, sketch.png, brand_colors.png                       │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Asset Analyzer (Claude Vision)                                 │
│  • Analyzes visual seed assets                                  │
│  • Extracts themes, colors, style keywords                      │
│  • Creates enriched SeedAssetCollection                         │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Producer Agent                                                  │
│  • Analyzes request + enriched seed assets                      │
│  • Estimates costs (video + audio tiers)                        │
│  • Creates 2-3 competitive pilot strategies                     │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Script Writer Agent                                            │
│  • Breaks concept into scenes (using seed asset refs)          │
│  • Adds voiceover text and sync points                         │
│  • Specifies music transitions and SFX cues                    │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Parallel Competitive Pilots                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Pilot 1      │  │ Pilot 2      │  │ Pilot 3      │         │
│  │ Motion+Audio │  │ Static+Music │  │ Animated+VO  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                 │
│         └──────────────────┴──────────────────┘                 │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Critic Agent                                                    │
│  • Evaluates test scenes (vision QA)                           │
│  • Cancels underperforming pilots                              │
│  • Reallocates budget to winners                               │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Full Production (Winners Only)                                 │
│  • VideoGenerator: Generates all scenes                        │
│  • AudioGenerator: Creates synced audio tracks                 │
│  • QAVerifier: Vision analysis of final quality                │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Editor Agent                                                    │
│  • Creates EDL candidates for each pilot                        │
│  • Human selects best final cut                                 │
│  • Exports final video with mixed audio                         │
└─────────────────────────────────────────────────────────────────┘
```

## 💵 Cost Models (2025 Pricing)

### Video Production Tiers

| Tier | Cost/Second | Use Case | Quality Ceiling |
|------|-------------|----------|-----------------|
| Static Images | $0.04 | Slideshows, presentations | 75/100 |
| Motion Graphics | $0.15 | Explainers, product demos | 85/100 |
| Animated | $0.25 | Storytelling, characters | 90/100 |
| Photorealistic | $0.50 | High-end commercials | 95/100 |

### Audio Production Tiers

| Tier | Cost/Minute | Description | Includes |
|------|-------------|-------------|----------|
| NONE | $0.00 | No audio | Silent video |
| MUSIC_ONLY | $0.50 | Background music | AI-generated music track |
| SIMPLE_OVERLAY | $2.00 | Basic voiceover | VO + music, loose sync |
| TIME_SYNCED | $5.00 | Synchronized audio | VO + music, frame-accurate sync |
| FULL_PRODUCTION | $15.00 | Professional mix | VO + music + SFX + mixing |

**Note**: TIME_SYNCED and FULL_PRODUCTION include $0.50 per scene sync overhead.

## 📦 Installation

### Prerequisites

- Python 3.9+
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Quick Install (Recommended)

```bash
# Install directly from GitHub
pip install git+https://github.com/aaronmarkham/claude-studio-producer.git

# Or install in editable mode for development
git clone https://github.com/aaronmarkham/claude-studio-producer.git
cd claude-studio-producer
pip install -e .
```

### Manual Setup

```bash
# Clone the repository
git clone https://github.com/aaronmarkham/claude-studio-producer.git
cd claude-studio-producer

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (Git Bash):
source .venv/Scripts/activate
# On macOS/Linux:
source .venv/bin/activate

# Install the package
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## ⚡ Quick Start

### Basic Production
```python
import asyncio
from core import StudioOrchestrator

async def main():
    # Create orchestrator
    orchestrator = StudioOrchestrator(num_variations=3)

    # Run production
    result = await orchestrator.produce_video(
        user_request="""
        Create a 60-second video: 'A day in the life of a developer
        using AI tools'. Show: standup, coding, debugging, deploying.
        """,
        total_budget=150.00
    )

    print(f"Status: {result.status}")
    print(f"Best pilot: {result.best_pilot.pilot_id}")
    print(f"Cost: ${result.budget_used:.2f}")

asyncio.run(main())
```

### With Seed Assets
```python
from core.models.seed_assets import SeedAsset, SeedAssetCollection, SeedAssetType, AssetRole
from agents import AssetAnalyzerAgent

async def main_with_assets():
    # Create seed asset collection
    seed_assets = SeedAssetCollection(
        assets=[
            SeedAsset(
                asset_id="logo_001",
                asset_type=SeedAssetType.LOGO,
                role=AssetRole.BRAND_GUIDE,
                file_path="assets/company_logo.png",
                description="Company logo with brand colors",
                usage_instructions="Include logo in intro and outro"
            ),
            SeedAsset(
                asset_id="sketch_001",
                asset_type=SeedAssetType.SKETCH,
                role=AssetRole.STYLE_REFERENCE,
                file_path="assets/ui_sketch.png",
                description="Hand-drawn UI mockup",
                usage_instructions="Match this sketch style for interface scenes"
            )
        ],
        global_instructions="Create modern, professional tech-focused video"
    )

    # Analyze assets with Claude Vision
    analyzer = AssetAnalyzerAgent()
    enriched_assets = await analyzer.analyze_collection(seed_assets)

    # View extracted themes
    print(f"Themes: {enriched_assets.extracted_themes}")
    print(f"Colors: {enriched_assets.extracted_color_palette}")
    print(f"Styles: {enriched_assets.extracted_style_keywords}")

    # Run production with analyzed assets
    orchestrator = StudioOrchestrator()
    result = await orchestrator.produce_video(
        user_request="Create 60s product demo",
        total_budget=200.00,
        seed_assets=enriched_assets  # Pass enriched assets
    )

asyncio.run(main_with_assets())
```

Or use the included examples:
```bash
python examples/full_production.py
python examples/test_asset_analyzer.py
```

## 📁 Project Structure

```
claude-studio-producer/
├── agents/                          # Agent implementations
│   ├── producer.py                  # Producer agent (implemented)
│   ├── critic.py                    # Critic agent (implemented)
│   ├── script_writer.py             # Script writer agent (implemented)
│   ├── video_generator.py           # Video generator agent (implemented)
│   ├── qa_verifier.py               # QA verifier agent (implemented)
│   ├── asset_analyzer.py            # Asset analyzer agent (stub)
│   ├── audio_generator.py           # Audio generator agent (stub)
│   └── editor.py                    # Editor agent (stub)
│
├── core/
│   ├── orchestrator.py              # Main pipeline coordinator
│   ├── claude_client.py             # Claude SDK wrapper with vision support
│   ├── budget.py                    # Cost models and tracking
│   │
│   ├── models/                      # Data models
│   │   ├── seed_assets.py           # Seed asset data structures
│   │   ├── audio.py                 # Audio production models
│   │   ├── video.py                 # Video production models
│   │   └── edl.py                   # Edit decision list models
│   │
│   └── providers/                   # Provider stubs
│       ├── video/                   # Video generation providers
│       │   ├── runway.py            # Runway ML (stub)
│       │   ├── pika.py              # Pika Labs (stub)
│       │   ├── luma.py              # Luma AI (stub)
│       │   ├── kling.py             # Kling AI (stub)
│       │   └── stability.py         # Stability AI (stub)
│       │
│       ├── audio/                   # Audio generation providers
│       │   ├── elevenlabs.py        # ElevenLabs (stub)
│       │   ├── openai_tts.py        # OpenAI TTS (stub)
│       │   └── google_tts.py        # Google TTS (stub)
│       │
│       ├── music/                   # Music generation providers
│       │   ├── mubert.py            # Mubert (stub)
│       │   └── suno.py              # Suno (stub)
│       │
│       └── storage/                 # Storage providers
│           ├── local.py             # Local filesystem (stub)
│           └── s3.py                # AWS S3 (stub)
│
├── workflows/                       # Production workflows
│   └── competitive_pilots.py        # Multi-pilot orchestration
│
├── docs/
│   └── specs/                       # Detailed specifications
│       ├── 01-architecture.md       # System architecture
│       ├── 02-agents.md             # Agent specifications
│       ├── 03-seed-assets.md        # Seed asset system
│       ├── 04-audio-pipeline.md     # Audio production pipeline
│       ├── 05-video-providers.md    # Video provider integrations
│       └── 06-budget-models.md      # Cost models and tracking
│
├── tests/
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
│
├── examples/                        # Usage examples
│   ├── full_production.py           # Complete production example
│   ├── test_producer.py             # Test producer agent
│   ├── test_critic.py               # Test critic agent
│   └── test_asset_analyzer.py       # Test asset analyzer
│
├── setup.py                         # Package setup
├── requirements.txt                 # Dependencies
└── README.md                        # This file
```

## 📚 Examples

### Test Individual Agents
```bash
# Test Producer
python examples/test_producer.py

# Test Critic
python examples/test_critic.py

# Full production pipeline
python examples/full_production.py
```

### Cost Estimation
```bash
# Estimate costs for different tiers
python scripts/estimate_costs.py
```

## 🔧 Configuration

Edit `.env`:
```bash
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional
DEFAULT_BUDGET=100.00
DEFAULT_VARIATIONS=3
```

## 🎯 Use Cases

- **Product Demos**: Automated demo video generation
- **Educational Content**: Tutorial and explainer videos
- **Marketing**: Social media content at scale
- **Documentation**: Visual documentation generation
- **Prototyping**: Rapid video concept testing

## 🤝 Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 🔧 Provider Support

| Category | Provider | Status | Cost Model | Notes |
|----------|----------|--------|------------|-------|
| **Video** | Runway ML | ✅ **Implemented** | ✅ | Gen-3 Alpha Turbo integration |
| | Pika Labs | Stub | ✅ | v1.0 pricing |
| | Luma AI | Stub | ✅ | Dream Machine pricing |
| | Kling AI | Stub | ✅ | v1.5 pricing |
| | Stability AI | Stub | ✅ | Stable Video pricing |
| **Audio** | ElevenLabs | Stub | ✅ | TTS pricing |
| | OpenAI TTS | Stub | ✅ | TTS-1 HD pricing |
| | Google TTS | Stub | ✅ | Cloud TTS pricing |
| **Music** | Mubert | Stub | ✅ | API pricing |
| | Suno | Stub | ✅ | v3 pricing |
| **Storage** | Local FS | Stub | ✅ | Free |
| | AWS S3 | Stub | ✅ | Standard storage |

**Implementation Status**:
- ✅ **Runway ML**: Fully implemented with async generation, polling, and download
- All other providers have interface definitions and cost models ready for integration

## 📊 Development Status

### Implemented Agents
- ✅ **Producer Agent**: Full implementation with multi-tier strategy creation
- ✅ **Critic Agent**: Gap analysis, pilot evaluation, budget reallocation
- ✅ **Script Writer Agent**: Scene breakdown with audio specifications
- ✅ **Video Generator Agent**: Multi-provider abstraction with mock mode
- ✅ **QA Verifier Agent**: Vision-based quality analysis with scoring

### Stub Agents (Interface + Tests)
- 🚧 **Asset Analyzer Agent**: Claude Vision integration (code complete, awaiting orchestrator integration)
- 🚧 **Audio Generator Agent**: 5-tier audio pipeline (models complete, generation pending)
- 🚧 **Editor Agent**: EDL generation and final assembly (planned)

### Core Systems
- ✅ Multi-agent orchestration
- ✅ Budget tracking and cost estimation
- ✅ Seed asset data models
- ✅ Audio production models (5 tiers)
- ✅ Competitive pilot workflow
- ✅ Claude Vision support in client
- ✅ Comprehensive test coverage (63 tests)

### Provider Integration
- ✅ **Runway ML video provider** (fully implemented)
- 🚧 Additional video providers (Pika, Luma, Kling, Stability - interface + cost models)
- 🚧 Audio providers (interface + cost models)
- 🚧 Music providers (interface + cost models)
- 🚧 Storage providers (interface + cost models)

## 📋 Roadmap

### Phase 1: Foundation (Complete)
- [x] Core Producer/Critic agents
- [x] Budget-aware orchestration
- [x] Multi-tier cost models
- [x] Script Writer agent
- [x] Video Generator agent (mock mode)
- [x] Video QA agent with vision analysis
- [x] Full agent integration in orchestrator
- [x] Seed asset models
- [x] Audio pipeline models

### Phase 2: Vision & Audio (Current)
- [x] Asset Analyzer with Claude Vision
- [x] Audio tier system (NONE → FULL_PRODUCTION)
- [ ] Audio Generator implementation
- [ ] Time-synchronized audio-video alignment
- [ ] Orchestrator integration for seed assets

### Phase 3: Provider Integration (In Progress)
- [x] **Runway ML integration** (Gen-3 Alpha Turbo)
- [ ] Pika Labs integration
- [ ] Luma AI integration
- [ ] ElevenLabs TTS integration
- [ ] Mubert music generation
- [ ] S3 storage integration

### Phase 4: Advanced Features (Future)
- [ ] Editor agent with EDL generation
- [ ] Web UI dashboard
- [ ] Prompt library & templates
- [ ] Performance benchmarks
- [ ] Multi-language support

## 📄 License

MIT-0 (MIT No Attribution) - see [LICENSE](LICENSE) for details

This project is released under the most permissive open source license. Use it freely without attribution requirements.

## 📖 Documentation

Detailed specifications are available in [docs/specs/](docs/specs/):

- [01-architecture.md](docs/specs/01-architecture.md) - System architecture and data flow
- [02-agents.md](docs/specs/02-agents.md) - Agent specifications and interfaces
- [03-seed-assets.md](docs/specs/03-seed-assets.md) - Seed asset system and vision analysis
- [04-audio-pipeline.md](docs/specs/04-audio-pipeline.md) - Audio production pipeline and sync system
- [05-video-providers.md](docs/specs/05-video-providers.md) - Video provider integrations
- [06-budget-models.md](docs/specs/06-budget-models.md) - Cost models and budget tracking

## 🙏 Acknowledgments

- Built on [Claude Agent SDK](https://docs.anthropic.com/agent-sdk)
- Inspired by real production workflows
- Cost models based on 2025 AI video generation pricing
- Claude Vision for seed asset analysis

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/aaronmarkham/claude-studio-producer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/aaronmarkham/claude-studio-producer/discussions)

---

**Note**: This is a production-ready framework for AI video orchestration. **Runway ML integration is fully implemented** and ready to use with an API key. Other video providers (Pika, Luma, Kling, Stability) have interfaces and cost models defined, with integration pending.
