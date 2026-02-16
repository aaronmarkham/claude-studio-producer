# Claude Studio Producer - CLI Reference

Claude Studio Producer provides a comprehensive command-line interface for AI video production with multi-agent orchestration.

## Quick Start

```bash
# Quick demo with mock providers
claude-studio produce -c "Logo reveal for TechCorp" -d 5 --mock

# Live production with Luma
claude-studio produce -c "Product demo" -b 15 -d 30 --live -p luma

# Generate video from transcript
claude-studio produce-video --script script.txt --live --kb my-project
```

## Command Overview

| Command | Purpose | Key Options |
|---------|---------|-------------|
| [produce](produce.md) | Run full video production pipeline | `--concept`, `--budget`, `--live`, `--provider` |
| [produce-video](produce-video.md) | Generate explainer videos from scripts | `--from-training`, `--script`, `--live`, `--kb-project` |
| [assemble](assemble.md) | Create rough cut video from production assets | `--output`, `--skip-existing` |
| [assets](assets.md) | Asset tracking and approval workflow | `list`, `approve`, `reject`, `build` |
| [resume](resume.md) | Resume interrupted productions | `--live`, `--skip-qa`, `--skip-critic` |
| [render](render.md) | Render EDLs and mix video+audio | `edl`, `mix` |
| [test-provider](utilities.md#test-provider) | Test individual providers | `--prompt`, `--live`, `--output` |
| [upload](upload.md) | Upload videos to platforms | `youtube`, `youtube-update`, `youtube-auth` |
| [status](utilities.md#status) | Show system status | `--json` |
| [providers](providers.md) | List and manage providers | `list`, `add`, `remove` |
| [kb](kb.md) | Knowledge base management | `create`, `ingest`, `list` |
| [document](document.md) | Document ingestion | `--pdf`, `--extract-figures` |
| [training](training.md) | Training pipeline | `run`, `list`, `clean` |
| [memory](utilities.md#memory) | Memory and learnings management | `show`, `clear` |
| [qa](utilities.md#qa) | QA inspection | `--run-id`, `--verbose` |
| [config](utilities.md#config) | Configuration management | `show`, `set`, `reset` |
| [secrets](utilities.md#secrets) | API key management | `set`, `get`, `list`, `delete` |
| [themes](utilities.md#themes) | Color themes | `list`, `set` |
| [agents](utilities.md#agents) | Agent management | `list`, `status` |

## Production Pipeline Overview

The production pipeline follows these stages:

1. **Planning** (Sequential)
   - ProducerAgent analyzes concept and creates pilot strategies
   - ScriptWriterAgent generates scene breakdown

2. **Asset Generation** (Parallel via Strands)
   - VideoGeneratorAgent creates videos using providers (Luma, Runway)
   - AudioGeneratorAgent generates voiceover and music

3. **Evaluation** (Sequential)
   - QAVerifierAgent analyzes video quality
   - CriticAgent scores and approves production
   - EditorAgent creates Edit Decision Lists (EDLs)

4. **Rendering**
   - FFmpegRenderer concatenates videos and adds transitions

## Provider Support

### Video Providers
- **Luma AI** (`luma`) - Text/image to video, 5-10s clips
- **Runway ML** (`runway`) - Image to video generation
- **Mock** (`mock`) - Development/testing mode

### Audio Providers  
- **OpenAI TTS** - Text-to-speech generation
- **ElevenLabs** - High-quality voice synthesis
- **Google TTS** - Text-to-speech

### Image Providers
- **DALL-E 3** - AI image generation
- **Wikimedia Commons** - Free image sourcing

## Key Features

### Multi-Agent Architecture
Uses sophisticated agent patterns including:
- Sequential planning stages (Producer → ScriptWriter)
- Parallel asset generation (Video + Audio via Strands)
- Quality evaluation pipeline (QA → Critic → Editor)

### Budget-Aware Production
- Multiple production tiers (micro, low, medium, high, full)
- Cost tracking and optimization
- Provider selection based on budget

### Memory & Learning
- Long-term memory of production patterns
- Provider-specific prompt optimization
- Quality score tracking and analysis

### Unified Production Architecture
- Structured script parsing and segmentation
- Content library with asset tracking
- Assembly manifest for precise timing

## Configuration

Set up API keys using the secrets command:

```bash
# Core providers
claude-studio secrets set ANTHROPIC_API_KEY your_key
claude-studio secrets set LUMA_API_KEY your_key
claude-studio secrets set OPENAI_API_KEY your_key

# Optional providers
claude-studio secrets set ELEVENLABS_API_KEY your_key
claude-studio secrets set RUNWAY_API_KEY your_key

# YouTube upload
claude-studio secrets set YOUTUBE_CLIENT_ID your_client_id
claude-studio secrets set YOUTUBE_CLIENT_SECRET your_client_secret
```

Check status:
```bash
claude-studio status
```

## Environment Variables

Alternative to secrets (lower priority):
- `ANTHROPIC_API_KEY` - Claude API access
- `LUMA_API_KEY` - Luma AI video generation  
- `RUNWAY_API_KEY` - Runway ML video generation
- `OPENAI_API_KEY` - GPT and DALL-E access
- `ELEVENLABS_API_KEY` - Voice synthesis
- `TTS_PROVIDER` - Force TTS provider (`openai` or `elevenlabs`)

## Common Workflows

### Basic Video Production
```bash
# 1. Create video concept
claude-studio produce -c "Product demo for mobile app" -b 20 -d 30 --live -p luma

# 2. Review and render
claude-studio render edl <run_id>

# 3. Upload to YouTube  
claude-studio upload youtube video.mp4 -t "Product Demo" --privacy unlisted
```

### Script-Based Production
```bash
# 1. Train on PDF documents
claude-studio training run --pdf document.pdf

# 2. Generate video from training
claude-studio produce-video --from-training latest --live --kb my-project

# 3. Assemble rough cut
claude-studio assemble <run_dir>
```

### Provider Testing
```bash
# Test video generation
claude-studio test-provider luma -p "A rocket launching" --live

# Test audio generation
claude-studio test-provider elevenlabs -t "Hello world" --voice lily --live
```

## Output Structure

Production runs create organized output directories:

```
artifacts/runs/<run_id>/
├── scenes/              # Scene specifications
├── videos/              # Generated video clips
├── audio/               # Generated audio files
├── edl/                 # Edit Decision Lists
├── renders/             # Final rendered videos
├── assembly/            # Rough cut assembly
├── metadata.json        # Run metadata
└── final_output.mp4     # Mixed final video
```

## Error Handling

Common issues and solutions:

### API Keys
```bash
# Check configuration
claude-studio status

# Set missing keys
claude-studio secrets set LUMA_API_KEY your_key
```

### FFmpeg Required
```bash
# Install FFmpeg for rendering
brew install ffmpeg  # macOS
sudo apt install ffmpeg  # Ubuntu
```

### Provider Limits
```bash
# Use mock mode for development
claude-studio produce -c "test" --mock

# Test individual providers
claude-studio test-provider luma -p "test" --live
```

## Version

Current version: **0.6.0**

For detailed command documentation, see the individual command pages linked in the table above.