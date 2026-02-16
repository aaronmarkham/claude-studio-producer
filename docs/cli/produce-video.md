# produce-video - Explainer Videos from Scripts

The `produce-video` command generates explainer videos from podcast scripts and documents using the Unified Production Architecture. This command creates transcript-led video production with figure synchronization and budget-aware asset generation.

## Synopsis

```bash
claude-studio produce-video [--from-training TRIAL_ID | --script PATH] [OPTIONS]
```

## Description

The produce-video command specializes in creating educational and explanatory videos from structured content. It supports:

- Training-based production from analyzed documents
- Direct script-to-video conversion
- Knowledge base figure integration
- Budget-aware asset allocation
- Multi-tier cost optimization

## Input Sources (Required)

Choose one input source:

### `--from-training TRIAL_ID`
Load content from a training trial.

Training trials are created by the `training run` command and contain:
- Aligned transcript segments
- Knowledge graphs with figure references  
- Style and structure profiles
- Pre-analyzed content hierarchy

**Examples:**
- `--from-training latest` - Use most recent training
- `--from-training 20260207_143022` - Specific trial ID

### `--script PATH`
Generate directly from a script file.

Script files should contain well-structured text with natural paragraph breaks (double newlines). This mode bypasses training requirements but provides less sophisticated content analysis.

**Examples:**
- `--script my_script.txt`
- `--script ./content/podcast_transcript.md`

## Options

### Core Options

#### `--output PATH`
Output directory path (default: `artifacts/video_production/<timestamp>`).

#### `--live`
Use live API providers (costs money!). 

When not specified, runs in mock mode with simulated assets.

#### `--style CHOICE`
Narrative style for video production.

**Choices:**
- `visual_storyboard` - Visual-focused narrative (default)
- `podcast` - Rich NotebookLM-style narration
- `educational` - Educational lecture format  
- `documentary` - Documentary style

### Knowledge Base Integration

#### `--kb-project TEXT`
Knowledge base project name for figure integration.

Enables automatic figure matching and seeding for video generation. The KB project should be created and populated using the `kb` commands.

**Example:**
```bash
# First create and populate KB
claude-studio kb create my-research
claude-studio kb ingest my-research --pdf research.pdf

# Then use in video production
claude-studio produce-video --script script.txt --kb-project my-research
```

### Budget Control

#### `--budget CHOICE`
Budget tier for asset generation.

**Choices:**
- `micro` - Text overlays and minimal images
- `low` - Basic DALL-E images, shared assets
- `medium` - Full DALL-E + some animations
- `high` - Premium generation with Luma animations  
- `full` - Maximum quality, all animations

**Budget Impact:**
- Higher tiers enable more DALL-E generations
- Animation allocation increases with budget
- Figure seeding optimizes across all tiers

#### `--show-tiers`
Display budget tier comparison table and exit.

Shows detailed cost breakdown for each tier based on script analysis.

### Content Filtering

#### `--scene-limit INTEGER`
Maximum number of scenes to process.

Useful for testing or partial generation. Processes scenes from `--scene-start` up to the limit.

#### `--scene-start INTEGER`
Starting scene index (default: 0).

Combined with `--scene-limit` allows processing specific scene ranges.

**Example:**
```bash
# Process scenes 10-19 only
claude-studio produce-video --script script.txt --scene-start 10 --scene-limit 10
```

### Audio Generation

#### `--generate-audio / --no-generate-audio`
Generate TTS audio for each segment (default: True).

Audio generation uses:
- ElevenLabs (preferred, if API key available)
- OpenAI TTS (fallback, HD quality)
- Segment-by-segment to avoid length limits

#### `--voice-id TEXT`
Voice ID for TTS generation (default: "pFZP5JQG7iQjIQuC4Bku" - Lily voice).

**ElevenLabs Voice IDs:**
- `pFZP5JQG7iQjIQuC4Bku` - Lily (warm, engaging)
- `21m00Tcm4TlvDq8ikWAM` - Rachel (clear, professional)
- `pNInz6obpgDQGcFmaJgB` - Adam (deep, authoritative)

**OpenAI Voices:**
- `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`

## Examples

### Basic Usage

```bash
# Generate from training data (mock mode)
claude-studio produce-video --from-training latest

# Generate from script file with live providers
claude-studio produce-video --script my_transcript.txt --live

# Use knowledge base figures
claude-studio produce-video --script script.txt --live --kb-project research-2024
```

### Budget Control

```bash
# Show cost estimates for different tiers
claude-studio produce-video --script script.txt --show-tiers

# Use specific budget tier
claude-studio produce-video --script script.txt --live --budget medium

# High-quality production with animations
claude-studio produce-video --script script.txt --live --budget high --kb-project figures
```

### Content Filtering

```bash
# Test with first 5 scenes only
claude-studio produce-video --script script.txt --scene-limit 5 --live

# Process specific range (scenes 10-19)
claude-studio produce-video --script script.txt --scene-start 10 --scene-limit 10 --live

# Different narrative styles
claude-studio produce-video --script script.txt --style podcast --live
claude-studio produce-video --script script.txt --style documentary --live
```

### Audio Options

```bash
# Skip audio generation (visual only)
claude-studio produce-video --script script.txt --no-generate-audio --live

# Use specific voice
claude-studio produce-video --script script.txt --voice-id "21m00Tcm4TlvDq8ikWAM" --live

# Custom output directory
claude-studio produce-video --script script.txt --output ./my_video_project/ --live
```

## Production Pipeline

### Phase 1: Content Analysis

1. **Script Parsing**
   - Segment text into meaningful chunks
   - Extract key concepts and technical terms
   - Identify figure references and visual opportunities

2. **Knowledge Base Integration** (if `--kb-project` specified)
   - Load available figures from KB project
   - Match figures to segments based on content similarity
   - Build figure-to-segment mapping for visual planning

### Phase 2: Visual Planning

1. **Budget Allocation**
   - Analyze script complexity and length
   - Distribute budget across scenes based on importance
   - Determine asset generation strategy per scene

2. **Asset Source Selection**
   - **KB Figures**: Use extracted PDF figures as seeds
   - **DALL-E Generation**: Create custom images for primary scenes
   - **Web Images**: Source from Wikimedia Commons
   - **Shared Assets**: Reuse images across similar scenes
   - **Text Overlays**: Pure text for transitional content

3. **Animation Planning**
   - Ken Burns effects for static images
   - Luma AI animations for dynamic content
   - Budget-conscious animation allocation

### Phase 3: Asset Generation

1. **Image Generation**
   - DALL-E 3 HD (1792x1024) for custom visuals
   - Wikimedia Commons for educational content
   - KB figure copying and processing

2. **Audio Generation** (if enabled)
   - Text-to-speech using ElevenLabs or OpenAI
   - Segment-by-segment processing for quality
   - Actual duration recording for timing sync

3. **Content Library Management**
   - Asset registration with metadata
   - Status tracking (draft → review → approved)
   - Reuse detection and optimization

### Phase 4: Assembly Preparation

1. **Timing Calculation**
   - Audio-driven segment durations
   - Figure sync point determination
   - Transition planning between segments

2. **Assembly Manifest Creation**
   - Detailed instructions for video assembly
   - Asset-to-segment mapping
   - Display mode specifications

## Budget Tiers Explained

### Micro Tier ($0-3)
- Text overlays with simple backgrounds
- Minimal image generation
- Shared assets across multiple segments
- Basic transitions

**Best for:** Short explanations, text-heavy content

### Low Tier ($3-8)
- Basic DALL-E images for key concepts
- Some web images from Wikimedia
- Shared assets for similar content
- Ken Burns effects on images

**Best for:** Educational content, documentation

### Medium Tier ($8-20)
- Full DALL-E generation for primary scenes
- KB figures integrated as seeds
- Some Luma AI animations
- Enhanced visual variety

**Best for:** Engaging tutorials, presentations

### High Tier ($20-50)
- Premium image generation
- Extensive Luma AI animations
- Multiple variations for quality
- Professional-grade visuals

**Best for:** Marketing content, high-production videos

### Full Tier ($50+)
- Maximum quality assets
- All scenes get premium treatment
- Extensive animation and effects
- Multiple generation attempts

**Best for:** Commercial productions, flagship content

## Knowledge Base Integration

### KB Project Setup

```bash
# Create KB project
claude-studio kb create my-project

# Ingest PDF documents
claude-studio kb ingest my-project --pdf document.pdf --extract-figures

# List available figures
claude-studio kb list my-project --figures
```

### Figure Matching

The system automatically matches KB figures to script segments based on:

1. **Keyword Matching**: Technical terms and concepts
2. **Context Analysis**: Semantic similarity
3. **Figure Captions**: Content from PDF extraction
4. **Manual References**: Explicit figure mentions in script

### Figure Usage

Matched figures are used as:
- **Seed Images**: For Luma AI video generation
- **Static Visuals**: With Ken Burns effects
- **Background Elements**: For text overlays

## Output Structure

```
artifacts/video_production/<timestamp>/
├── structured_script.json     # Parsed script segments
├── content_library.json       # Asset registry
├── assembly_manifest.json     # Assembly instructions
├── audio/                     # Generated audio files
│   ├── audio_001.mp3
│   ├── audio_002.mp3
│   └── ...
├── images/                    # Generated/sourced images  
│   ├── scene_001.png
│   ├── scene_002.png
│   └── ...
├── videos/                    # Generated video clips (if animated)
│   ├── scene_001_luma.mp4
│   └── ...
└── assembly/                  # Final assembly output
    ├── segments/              # Individual video segments
    ├── rough_cut.mp4         # Assembled video
    └── assembly_manifest.json
```

## Asset Sources Summary

Generated assets come from multiple sources:

### KB Figures (Free)
- Extracted from PDF documents
- High-quality academic/technical figures
- Perfect for educational content
- Used as seeds for animation

### DALL-E Images (~$0.08 each)
- Custom AI-generated images
- HD quality (1792x1024)
- Tailored to specific content
- Primary visual source

### Web Images (Free)
- Wikimedia Commons sourcing
- Educational and reference images
- Automatic license compliance
- Fallback for common concepts

### Shared Assets (Free)
- Reuse across similar segments
- Budget optimization strategy
- Maintains visual consistency
- Reduces generation costs

### Text Overlays (Free)
- Pure text on styled backgrounds
- Transitional content
- Quote presentations
- Zero-cost option

## Integration with Assembly

The produce-video command prepares content for the `assemble` command:

```bash
# 1. Generate assets
claude-studio produce-video --script script.txt --live --kb-project my-kb

# 2. Assemble rough cut
claude-studio assemble <output_directory>

# 3. Review and approve assets
claude-studio assets list <output_directory>
claude-studio assets approve <output_directory> --image all --audio all

# 4. Final assembly
claude-studio assets build <output_directory>
```

## Performance Tips

### Development
- Use mock mode for script testing
- Set `--scene-limit 3` for quick iterations
- Test different budget tiers with `--show-tiers`

### Production
- Create KB projects for figure reuse
- Use appropriate budget tiers for content type
- Generate audio in segments for better quality

### Optimization
- Reuse KB figures across multiple videos
- Share assets between similar segments
- Batch process multiple scripts with same KB

## Common Workflows

### Academic Content
```bash
# 1. Create KB from research papers
claude-studio kb create research-2024
claude-studio kb ingest research-2024 --pdf paper1.pdf paper2.pdf

# 2. Generate educational video
claude-studio produce-video --script lecture_script.txt \
  --kb-project research-2024 --style educational --budget medium --live

# 3. Assemble and refine
claude-studio assemble <output_dir>
```

### Podcast to Video
```bash
# 1. Use training pipeline for transcript analysis  
claude-studio training run --transcript podcast_transcript.txt

# 2. Generate with podcast style
claude-studio produce-video --from-training latest \
  --style podcast --budget high --live

# 3. Review and publish
claude-studio assets list <output_dir>
claude-studio upload youtube <output_dir>/assembly/rough_cut.mp4
```

### Technical Documentation
```bash
# 1. Process documentation
claude-studio produce-video --script tech_doc.md \
  --style visual_storyboard --budget low --live

# 2. Focus on key sections
claude-studio produce-video --script tech_doc.md \
  --scene-start 5 --scene-limit 10 --budget medium --live
```

## Error Handling

### Input Issues
```bash
# Training trial not found
Error: Trial not found: 20260207_999999
# Solution: Use claude-studio training list to see available trials

# Script file missing
Error: Script file not found: script.txt
# Solution: Verify file path and permissions
```

### API Configuration
```bash
# Missing TTS provider
Error: No TTS provider available - set ELEVENLABS_API_KEY or OPENAI_API_KEY
# Solution: Configure API keys via secrets command
```

### KB Integration
```bash
# KB project not found  
Error: KB project not found: my-project
# Solution: Create KB project first with claude-studio kb create
```

### Generation Failures
```bash
# DALL-E quota exceeded
Warning: DALL-E generation failed, using web image fallback
# Solution: Wait for quota reset or use lower budget tier
```

## Environment Variables

- `TTS_PROVIDER` - Force TTS provider (`openai` to skip ElevenLabs)
- `ELEVENLABS_API_KEY` - ElevenLabs voice synthesis
- `OPENAI_API_KEY` - OpenAI TTS and DALL-E
- `ANTHROPIC_API_KEY` - Claude for content analysis

## Version History

- **0.6.0**: Unified Production Architecture with content library
- **0.5.x**: Knowledge base integration and figure matching
- **0.4.x**: Basic transcript-to-video pipeline